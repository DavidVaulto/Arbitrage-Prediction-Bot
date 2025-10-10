"""Portfolio management and PnL tracking."""

from __future__ import annotations

from .types import ContractSide, Position, Quote, Trade, Venue


class Portfolio:
    """Manages portfolio positions and PnL."""

    def __init__(self, initial_balance: float = 10000.0):
        """Initialize portfolio.
        
        Args:
            initial_balance: Initial portfolio balance
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # Track positions by event ID and venue
        self._positions: dict[str, dict[Venue, Position]] = {}
        self._trades: list[Trade] = []
        self._quotes: dict[str, Quote] = {}

    def add_trade(self, trade: Trade) -> None:
        """Add a completed trade to the portfolio."""
        self._trades.append(trade)

        # Update positions
        self._update_positions_from_trade(trade)

        # Update balance
        self.current_balance += trade.pnl

    def _update_positions_from_trade(self, trade: Trade) -> None:
        """Update positions based on a trade."""
        event_id = trade.event_id

        # Initialize event positions if needed
        if event_id not in self._positions:
            self._positions[event_id] = {}

        # Update venue A position
        venue_a = trade.venue_a
        if venue_a not in self._positions[event_id]:
            self._positions[event_id][venue_a] = Position(
                venue=venue_a,
                contract_id=trade.contract_a,
                normalized_event_id=event_id,
                side=ContractSide.YES,  # Default, would need to determine from trade
                qty=0.0,
                avg_price=0.0,
            )

        pos_a = self._positions[event_id][venue_a]
        if trade.side_a.value == "BUY":
            # Add to position
            new_qty = pos_a.qty + trade.qty
            if new_qty > 0:
                pos_a.avg_price = (
                    (pos_a.qty * pos_a.avg_price + trade.qty * trade.price_a) / new_qty
                )
                pos_a.qty = new_qty
            else:
                pos_a.qty = 0.0
                pos_a.avg_price = 0.0
        else:
            # Subtract from position
            pos_a.qty -= trade.qty
            if pos_a.qty <= 0:
                pos_a.qty = 0.0
                pos_a.avg_price = 0.0

        # Update venue B position
        venue_b = trade.venue_b
        if venue_b not in self._positions[event_id]:
            self._positions[event_id][venue_b] = Position(
                venue=venue_b,
                contract_id=trade.contract_b,
                normalized_event_id=event_id,
                side=ContractSide.NO,  # Default, would need to determine from trade
                qty=0.0,
                avg_price=0.0,
            )

        pos_b = self._positions[event_id][venue_b]
        if trade.side_b.value == "BUY":
            # Add to position
            new_qty = pos_b.qty + trade.qty
            if new_qty > 0:
                pos_b.avg_price = (
                    (pos_b.qty * pos_b.avg_price + trade.qty * trade.price_b) / new_qty
                )
                pos_b.qty = new_qty
            else:
                pos_b.qty = 0.0
                pos_b.avg_price = 0.0
        else:
            # Subtract from position
            pos_b.qty -= trade.qty
            if pos_b.qty <= 0:
                pos_b.qty = 0.0
                pos_b.avg_price = 0.0

    def update_quotes(self, quotes: list[Quote]) -> None:
        """Update market quotes for mark-to-market."""
        for quote in quotes:
            self._quotes[quote.contract_id] = quote

    def mark_to_market(self) -> dict[str, float]:
        """Calculate mark-to-market PnL for all positions."""
        total_unrealized_pnl = 0.0
        position_pnl = {}

        for event_id, venue_positions in self._positions.items():
            event_pnl = 0.0

            for venue, position in venue_positions.items():
                if position.qty == 0:
                    continue

                # Get current quote
                quote = self._quotes.get(position.contract_id)
                if not quote:
                    continue

                # Calculate unrealized PnL
                current_price = quote.mid_price or ((quote.best_bid + quote.best_ask) / 2)

                if position.side == ContractSide.YES:
                    # YES position: profit if price goes up
                    unrealized_pnl = position.qty * (current_price - position.avg_price)
                else:
                    # NO position: profit if price goes down
                    unrealized_pnl = position.qty * (position.avg_price - current_price)

                position.unrealized_pnl = unrealized_pnl
                event_pnl += unrealized_pnl
                total_unrealized_pnl += unrealized_pnl

            position_pnl[event_id] = event_pnl

        return {
            "total_unrealized_pnl": total_unrealized_pnl,
            "position_pnl": position_pnl,
        }

    def get_positions(self) -> dict[str, dict[Venue, Position]]:
        """Get all positions."""
        return self._positions.copy()

    def get_position(self, event_id: str, venue: Venue) -> Position | None:
        """Get position for a specific event and venue."""
        if event_id in self._positions and venue in self._positions[event_id]:
            return self._positions[event_id][venue]
        return None

    def get_total_exposure(self) -> float:
        """Get total exposure across all positions."""
        total_exposure = 0.0

        for venue_positions in self._positions.values():
            for position in venue_positions.values():
                if position.qty > 0:
                    # Estimate exposure as notional value
                    quote = self._quotes.get(position.contract_id)
                    if quote:
                        current_price = quote.mid_price or ((quote.best_bid + quote.best_ask) / 2)
                        total_exposure += position.qty * current_price

        return total_exposure

    def get_portfolio_summary(self) -> dict[str, any]:
        """Get comprehensive portfolio summary."""
        # Calculate realized PnL
        realized_pnl = sum(trade.pnl for trade in self._trades)

        # Calculate mark-to-market
        mtm = self.mark_to_market()
        unrealized_pnl = mtm["total_unrealized_pnl"]

        # Calculate total PnL
        total_pnl = realized_pnl + unrealized_pnl

        # Calculate returns
        total_return = (total_pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0.0

        # Count positions
        total_positions = sum(
            len(venue_positions) for venue_positions in self._positions.values()
        )
        active_positions = sum(
            sum(1 for pos in venue_positions.values() if pos.qty > 0)
            for venue_positions in self._positions.values()
        )

        # Count trades
        total_trades = len(self._trades)
        successful_trades = sum(1 for trade in self._trades if trade.pnl > 0)
        win_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.current_balance,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": total_pnl,
            "total_return_pct": total_return,
            "total_exposure": self.get_total_exposure(),
            "total_positions": total_positions,
            "active_positions": active_positions,
            "total_trades": total_trades,
            "successful_trades": successful_trades,
            "win_rate": win_rate,
            "position_breakdown": mtm["position_pnl"],
        }

    def get_trade_history(self) -> list[Trade]:
        """Get trade history."""
        return self._trades.copy()

    def get_recent_trades(self, limit: int = 10) -> list[Trade]:
        """Get recent trades."""
        return self._trades[-limit:] if self._trades else []

    def get_positions_by_venue(self, venue: Venue) -> list[Position]:
        """Get all positions for a specific venue."""
        positions = []
        for venue_positions in self._positions.values():
            if venue in venue_positions:
                positions.append(venue_positions[venue])
        return positions

    def get_positions_by_event(self, event_id: str) -> dict[Venue, Position]:
        """Get all positions for a specific event."""
        return self._positions.get(event_id, {}).copy()

    def close_position(self, event_id: str, venue: Venue) -> Trade | None:
        """Close a position (placeholder for future implementation)."""
        # This would require creating closing trades
        # For now, just return None
        return None

    def reset_portfolio(self) -> None:
        """Reset portfolio to initial state."""
        self.current_balance = self.initial_balance
        self._positions.clear()
        self._trades.clear()
        self._quotes.clear()


