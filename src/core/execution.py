"""Order execution engine with atomic trading."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from .types import ArbOpportunity, Fill, OrderRequest, OrderSide, OrderTIF, Trade, Venue


class ExecutionEngine:
    """Executes arbitrage trades with atomic-like behavior."""

    def __init__(
        self,
        connectors: dict[Venue, any],  # VenueClient protocol
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ):
        """Initialize execution engine.
        
        Args:
            connectors: Dictionary mapping venues to their connectors
            max_retries: Maximum number of retries for failed orders
            retry_delay: Delay between retries in seconds
        """
        self.connectors = connectors
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Track active trades
        self._active_trades: dict[str, Trade] = {}
        self._trade_history: list[Trade] = []

    async def execute_opportunity(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> Trade | None:
        """Execute an arbitrage opportunity.
        
        Args:
            opportunity: Arbitrage opportunity to execute
            position_size: Position size to trade
            
        Returns:
            Trade record if successful, None otherwise
        """
        trade_id = str(uuid.uuid4())

        # Create trade record
        trade = Trade(
            trade_id=trade_id,
            event_id=opportunity.event_id,
            venue_a=opportunity.leg_a.venue,
            venue_b=opportunity.leg_b.venue,
            contract_a=opportunity.leg_a.contract_id,
            contract_b=opportunity.leg_b.contract_id,
            side_a=opportunity.leg_a.side,
            side_b=opportunity.leg_b.side,
            qty=position_size,
            price_a=opportunity.leg_a.price,
            price_b=opportunity.leg_b.price,
            edge_bps=opportunity.edge_bps,
            status="pending",
        )

        self._active_trades[trade_id] = trade

        try:
            # Execute both legs
            fills = await self._execute_both_legs(opportunity, position_size)

            if fills:
                # Update trade with fill information
                trade.fee_a = fills[0].fee_paid if fills[0] else 0.0
                trade.fee_b = fills[1].fee_paid if fills[1] else 0.0
                trade.status = "filled"
                trade.filled_at = datetime.utcnow()

                # Calculate PnL
                trade.pnl = self._calculate_trade_pnl(trade, fills)

                # Move to history
                self._trade_history.append(trade)
                del self._active_trades[trade_id]

                return trade
            else:
                # Failed execution
                trade.status = "failed"
                self._trade_history.append(trade)
                del self._active_trades[trade_id]

                return None

        except Exception as e:
            # Handle execution errors
            trade.status = "failed"
            trade.extra = {"error": str(e)}
            self._trade_history.append(trade)
            del self._active_trades[trade_id]

            print(f"Trade execution failed: {e}")
            return None

    async def _execute_both_legs(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> list[Fill | None] | None:
        """Execute both legs of the arbitrage trade."""
        # Determine execution order (place less liquid leg first)
        leg_a_liquidity = self._estimate_liquidity(opportunity.leg_a)
        leg_b_liquidity = self._estimate_liquidity(opportunity.leg_b)

        if leg_a_liquidity < leg_b_liquidity:
            # Execute leg A first, then leg B
            fill_a = await self._execute_leg(opportunity.leg_a, position_size)
            if fill_a:
                fill_b = await self._execute_leg(opportunity.leg_b, position_size)
                return [fill_a, fill_b]
            else:
                return None
        else:
            # Execute leg B first, then leg A
            fill_b = await self._execute_leg(opportunity.leg_b, position_size)
            if fill_b:
                fill_a = await self._execute_leg(opportunity.leg_a, position_size)
                return [fill_a, fill_b]
            else:
                return None

    async def _execute_leg(
        self,
        order_request: OrderRequest,
        position_size: float,
    ) -> Fill | None:
        """Execute a single leg of the trade."""
        # Update order request with position size
        order_request.qty = position_size

        connector = self.connectors.get(order_request.venue)
        if not connector:
            raise ValueError(f"No connector for venue {order_request.venue}")

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                fill = await connector.place_order(order_request)
                if fill:
                    return fill

                # If no fill, wait and retry
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)

            except Exception as e:
                print(f"Leg execution attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    raise

        return None

    def _estimate_liquidity(self, order_request: OrderRequest) -> float:
        """Estimate liquidity for an order request."""
        # This is a simplified estimation
        # In practice, you would use real-time order book data
        return 1000.0  # Default liquidity score

    def _calculate_trade_pnl(self, trade: Trade, fills: list[Fill | None]) -> float:
        """Calculate PnL for a completed trade."""
        if not fills[0] or not fills[1]:
            return 0.0

        # For arbitrage, PnL is the guaranteed edge
        edge_decimal = trade.edge_bps / 10000.0
        pnl = trade.qty * edge_decimal

        # Subtract fees
        total_fees = trade.fee_a + trade.fee_b
        pnl -= total_fees

        return pnl

    async def hedge_partial_fill(
        self,
        trade: Trade,
        partial_fill: Fill,
    ) -> Trade | None:
        """Hedge a partial fill to minimize risk."""
        # Determine which leg was filled
        if partial_fill.venue == trade.venue_a:
            # Leg A was filled, need to hedge on venue B
            hedge_venue = trade.venue_b
            hedge_contract = trade.contract_b
            hedge_side = self._get_opposite_side(trade.side_b)
        else:
            # Leg B was filled, need to hedge on venue A
            hedge_venue = trade.venue_a
            hedge_contract = trade.contract_a
            hedge_side = self._get_opposite_side(trade.side_a)

        # Create hedge order
        hedge_order = OrderRequest(
            venue=hedge_venue,
            contract_id=hedge_contract,
            side=hedge_side,
            price=0.0,  # Market order
            qty=partial_fill.qty,
            tif=OrderTIF.IOC,
        )

        # Execute hedge
        connector = self.connectors.get(hedge_venue)
        if connector:
            hedge_fill = await connector.place_order(hedge_order)
            if hedge_fill:
                # Update trade status
                trade.status = "hedged"
                trade.extra = {"hedge_fill": hedge_fill}
                return trade

        return None

    def _get_opposite_side(self, side: OrderSide) -> OrderSide:
        """Get the opposite side of an order."""
        return OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY

    async def cancel_trade(self, trade_id: str) -> bool:
        """Cancel an active trade."""
        trade = self._active_trades.get(trade_id)
        if not trade:
            return False

        # Cancel both legs
        cancelled_a = await self._cancel_leg(trade.venue_a, trade.contract_a)
        cancelled_b = await self._cancel_leg(trade.venue_b, trade.contract_b)

        if cancelled_a or cancelled_b:
            trade.status = "cancelled"
            self._trade_history.append(trade)
            del self._active_trades[trade_id]
            return True

        return False

    async def _cancel_leg(self, venue: Venue, contract_id: str) -> bool:
        """Cancel a single leg."""
        connector = self.connectors.get(venue)
        if not connector:
            return False

        # In practice, you would need to track order IDs
        # For now, return False as we don't have order tracking
        return False

    def get_active_trades(self) -> list[Trade]:
        """Get list of active trades."""
        return list(self._active_trades.values())

    def get_trade_history(self) -> list[Trade]:
        """Get trade history."""
        return self._trade_history.copy()

    def get_execution_stats(self) -> dict[str, any]:
        """Get execution statistics."""
        total_trades = len(self._trade_history)
        successful_trades = sum(1 for t in self._trade_history if t.status == "filled")
        failed_trades = sum(1 for t in self._trade_history if t.status == "failed")
        hedged_trades = sum(1 for t in self._trade_history if t.status == "hedged")

        total_pnl = sum(trade.pnl for trade in self._trade_history)
        total_fees = sum(trade.fee_a + trade.fee_b for trade in self._trade_history)

        success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "successful_trades": successful_trades,
            "failed_trades": failed_trades,
            "hedged_trades": hedged_trades,
            "success_rate": success_rate,
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "active_trades": len(self._active_trades),
        }


