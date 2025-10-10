"""Paper trading mode implementation."""

from __future__ import annotations

import asyncio
from datetime import datetime

from .config import settings
from .discovery import DiscoveryEngine
from .execution import ExecutionEngine
from .fees import create_default_fee_calculator
from .matcher import EventMatcher
from .portfolio import Portfolio
from .risk import RiskManager
from .sizing import PositionSizer
from .types import ArbOpportunity, Balance, Trade, Venue


class PaperTradingEngine:
    """Paper trading engine that simulates trades without real money."""

    def __init__(self):
        """Initialize paper trading engine."""
        self.fee_calculator = create_default_fee_calculator()
        self.event_matcher = EventMatcher()
        self.discovery_engine = DiscoveryEngine(
            fee_calculator=self.fee_calculator,
            event_matcher=self.event_matcher,
            min_edge_bps=settings.min_edge_bps,
            min_notional_usd=settings.min_notional_usd,
            max_slippage_bps=settings.max_slippage_bps,
        )
        self.risk_manager = RiskManager(
            risk_limits=settings.get_risk_limits(),
            max_drawdown_pct=settings.max_drawdown_pct,
            circuit_breaker_error_rate=settings.circuit_breaker_error_rate,
            circuit_breaker_latency_ms=settings.circuit_breaker_latency_ms,
        )
        self.position_sizer = PositionSizer(
            risk_limits=settings.get_risk_limits(),
            kelly_fraction=settings.kelly_fraction,
            bankroll=settings.starting_balance_usd,
        )
        self.portfolio = Portfolio(initial_balance=settings.starting_balance_usd)

        # Mock connectors for paper trading
        self.connectors: dict[Venue, any] = {}
        self.execution_engine: ExecutionEngine | None = None

        # Trading state
        self._is_running = False
        self._last_opportunities: list[ArbOpportunity] = []

    async def start(self, connectors: dict[Venue, any]) -> None:
        """Start paper trading.
        
        Args:
            connectors: Dictionary mapping venues to their connectors
        """
        self.connectors = connectors
        self.execution_engine = ExecutionEngine(connectors)
        self._is_running = True

        print("Starting paper trading engine...")
        print(f"Initial balance: ${settings.starting_balance_usd:,.2f}")
        print(f"Min edge: {settings.min_edge_bps}bps")
        print(f"Min notional: ${settings.min_notional_usd}")

        # Start discovery loop
        await self._discovery_loop()

    async def stop(self) -> None:
        """Stop paper trading."""
        self._is_running = False
        print("Paper trading engine stopped.")

    async def _discovery_loop(self) -> None:
        """Main discovery and trading loop."""
        while self._is_running:
            try:
                # Discover opportunities
                opportunities = await self.discovery_engine.discover_opportunities(
                    self.connectors,
                    refresh_contracts=False,  # Refresh every few iterations
                )

                self._last_opportunities = opportunities

                # Process opportunities
                await self._process_opportunities(opportunities)

                # Update portfolio
                self._update_portfolio()

                # Print status
                self._print_status()

                # Wait before next iteration
                await asyncio.sleep(settings.discovery_interval)

            except Exception as e:
                print(f"Error in discovery loop: {e}")
                await asyncio.sleep(5.0)  # Wait before retrying

    async def _process_opportunities(self, opportunities: list[ArbOpportunity]) -> None:
        """Process discovered opportunities."""
        for opportunity in opportunities:
            try:
                # Check risk limits
                current_positions = self._get_current_positions()
                balances = self._get_current_balances()

                is_allowed, reason = self.risk_manager.check_trade_risk(
                    opportunity,
                    current_positions,
                    balances,
                )

                if not is_allowed:
                    print(f"Skipping opportunity: {reason}")
                    continue

                # Calculate position size
                position_size = self.position_sizer.calculate_position_size(
                    opportunity,
                    balances,
                    current_positions,
                )

                if position_size <= 0:
                    print(f"Position size too small: {position_size}")
                    continue

                # Execute trade
                trade = await self._execute_paper_trade(opportunity, position_size)

                if trade:
                    # Record trade
                    self.portfolio.add_trade(trade)
                    self.risk_manager.record_trade(trade)

                    print(f"Executed paper trade: {trade.trade_id}")
                    print(f"  Event: {trade.event_id}")
                    print(f"  Size: {trade.qty}")
                    print(f"  Edge: {trade.edge_bps:.1f}bps")
                    print(f"  PnL: ${trade.pnl:.2f}")

            except Exception as e:
                print(f"Error processing opportunity: {e}")

    async def _execute_paper_trade(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> Trade | None:
        """Execute a paper trade."""
        # Simulate trade execution
        trade = Trade(
            trade_id=f"paper_{datetime.utcnow().timestamp()}",
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
            fee_a=self._simulate_fee(opportunity.leg_a.venue, position_size),
            fee_b=self._simulate_fee(opportunity.leg_b.venue, position_size),
            edge_bps=opportunity.edge_bps,
            pnl=self._calculate_paper_pnl(opportunity, position_size),
            status="filled",
            created_at=datetime.utcnow(),
            filled_at=datetime.utcnow(),
        )

        return trade

    def _simulate_fee(self, venue: Venue, qty: float) -> float:
        """Simulate trading fees."""
        fee_model = settings.get_venue_fees(venue)
        return qty * (fee_model.taker_bps / 10000.0)

    def _calculate_paper_pnl(self, opportunity: ArbOpportunity, qty: float) -> float:
        """Calculate PnL for paper trade."""
        edge_decimal = opportunity.edge_bps / 10000.0
        gross_pnl = qty * edge_decimal

        # Subtract estimated fees
        fee_a = self._simulate_fee(opportunity.leg_a.venue, qty)
        fee_b = self._simulate_fee(opportunity.leg_b.venue, qty)

        net_pnl = gross_pnl - fee_a - fee_b
        return net_pnl

    def _get_current_positions(self) -> dict[str, float]:
        """Get current positions for risk management."""
        positions = {}
        for event_id, venue_positions in self.portfolio.get_positions().items():
            total_exposure = 0.0
            for position in venue_positions.values():
                if position.qty > 0:
                    total_exposure += position.qty * position.avg_price
            positions[event_id] = total_exposure
        return positions

    def _get_current_balances(self) -> dict[str, Balance]:
        """Get current balances."""
        # For paper trading, return mock balances
        balances = {}
        for venue in Venue:
            balance = Balance(
                venue=venue,
                currency="USD" if venue == Venue.KALSHI else "USDC",
                available=self.portfolio.current_balance / len(Venue),
                total=self.portfolio.current_balance / len(Venue),
            )
            balances[f"{venue.value}_USD"] = balance
        return balances

    def _update_portfolio(self) -> None:
        """Update portfolio with latest quotes."""
        # In paper trading, we don't have real-time quotes
        # This is a placeholder for future implementation
        pass

    def _print_status(self) -> None:
        """Print current status."""
        summary = self.portfolio.get_portfolio_summary()
        risk_summary = self.risk_manager.get_risk_summary()

        print("\n--- Paper Trading Status ---")
        print(f"Balance: ${summary['current_balance']:,.2f}")
        print(f"Total PnL: ${summary['total_pnl']:,.2f}")
        print(f"Total Return: {summary['total_return_pct']:.2f}%")
        print(f"Active Positions: {summary['active_positions']}")
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Win Rate: {summary['win_rate']:.1f}%")
        print(f"Opportunities: {len(self._last_opportunities)}")

        if risk_summary['active_circuit_breakers']:
            print(f"Circuit Breakers: {risk_summary['active_circuit_breakers']}")

        print("--- End Status ---\n")

    def get_status(self) -> dict[str, any]:
        """Get current status."""
        portfolio_summary = self.portfolio.get_portfolio_summary()
        risk_summary = self.risk_manager.get_risk_summary()

        return {
            "portfolio": portfolio_summary,
            "risk": risk_summary,
            "opportunities": len(self._last_opportunities),
            "is_running": self._is_running,
        }

    def get_opportunities(self) -> list[ArbOpportunity]:
        """Get last discovered opportunities."""
        return self._last_opportunities.copy()

    def get_trade_history(self) -> list[Trade]:
        """Get trade history."""
        return self.portfolio.get_trade_history()




