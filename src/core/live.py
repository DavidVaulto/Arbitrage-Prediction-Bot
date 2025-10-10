"""Live trading mode implementation."""

from __future__ import annotations

import asyncio

from .config import settings
from .discovery import DiscoveryEngine
from .execution import ExecutionEngine
from .fees import create_default_fee_calculator
from .matcher import EventMatcher
from .portfolio import Portfolio
from .risk import RiskManager
from .sizing import PositionSizer
from .types import ArbOpportunity, Balance, Trade, Venue


class LiveTradingEngine:
    """Live trading engine that executes real trades."""

    def __init__(self):
        """Initialize live trading engine."""
        if not settings.is_live_trading_enabled():
            raise RuntimeError("Live trading is not enabled. Set CONFIRM_LIVE=true")

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

        # Live connectors
        self.connectors: dict[Venue, any] = {}
        self.execution_engine: ExecutionEngine | None = None

        # Trading state
        self._is_running = False
        self._last_opportunities: list[ArbOpportunity] = []
        self._last_balances: dict[str, Balance] = {}

    async def start(self, connectors: dict[Venue, any]) -> None:
        """Start live trading.
        
        Args:
            connectors: Dictionary mapping venues to their connectors
        """
        self.connectors = connectors
        self.execution_engine = ExecutionEngine(connectors)
        self._is_running = True

        print("Starting live trading engine...")
        print("WARNING: This will execute real trades with real money!")
        print(f"Initial balance: ${settings.starting_balance_usd:,.2f}")
        print(f"Min edge: {settings.min_edge_bps}bps")
        print(f"Min notional: ${settings.min_notional_usd}")

        # Verify balances
        await self._verify_balances()

        # Start discovery loop
        await self._discovery_loop()

    async def stop(self) -> None:
        """Stop live trading."""
        self._is_running = False
        print("Live trading engine stopped.")

    async def _verify_balances(self) -> None:
        """Verify account balances before starting."""
        print("Verifying account balances...")

        for venue, connector in self.connectors.items():
            try:
                balances = await connector.get_balance()
                self._last_balances.update(balances)

                for currency, balance in balances.items():
                    print(f"{venue.value} {currency}: ${balance.available:,.2f} available")

                if not balances:
                    print(f"WARNING: No balances found for {venue.value}")

            except Exception as e:
                print(f"ERROR: Failed to get balances from {venue.value}: {e}")
                raise

    async def _discovery_loop(self) -> None:
        """Main discovery and trading loop."""
        while self._is_running:
            try:
                # Update balances
                await self._update_balances()

                # Discover opportunities
                opportunities = await self.discovery_engine.discover_opportunities(
                    self.connectors,
                    refresh_contracts=False,  # Refresh every few iterations
                )

                self._last_opportunities = opportunities

                # Process opportunities
                await self._process_opportunities(opportunities)

                # Update portfolio
                await self._update_portfolio()

                # Print status
                self._print_status()

                # Wait before next iteration
                await asyncio.sleep(settings.discovery_interval)

            except Exception as e:
                print(f"Error in discovery loop: {e}")
                self.risk_manager.record_error(Venue.POLYMARKET, e)  # Log error
                await asyncio.sleep(5.0)  # Wait before retrying

    async def _update_balances(self) -> None:
        """Update account balances."""
        for venue, connector in self.connectors.items():
            try:
                balances = await connector.get_balance()
                self._last_balances.update(balances)
            except Exception as e:
                print(f"Failed to update balances from {venue.value}: {e}")
                self.risk_manager.record_error(venue, e)

    async def _process_opportunities(self, opportunities: list[ArbOpportunity]) -> None:
        """Process discovered opportunities."""
        for opportunity in opportunities:
            try:
                # Check risk limits
                current_positions = self._get_current_positions()
                balances = self._last_balances

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
                trade = await self._execute_live_trade(opportunity, position_size)

                if trade:
                    # Record trade
                    self.portfolio.add_trade(trade)
                    self.risk_manager.record_trade(trade)

                    print(f"Executed live trade: {trade.trade_id}")
                    print(f"  Event: {trade.event_id}")
                    print(f"  Size: {trade.qty}")
                    print(f"  Edge: {trade.edge_bps:.1f}bps")
                    print(f"  PnL: ${trade.pnl:.2f}")

                    # Send alert if configured
                    await self._send_trade_alert(trade)

            except Exception as e:
                print(f"Error processing opportunity: {e}")
                self.risk_manager.record_error(Venue.POLYMARKET, e)

    async def _execute_live_trade(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> Trade | None:
        """Execute a live trade."""
        if not self.execution_engine:
            return None

        # Execute the trade
        trade = await self.execution_engine.execute_opportunity(
            opportunity,
            position_size,
        )

        return trade

    async def _send_trade_alert(self, trade: Trade) -> None:
        """Send trade alert if webhook is configured."""
        if not settings.alert_webhook:
            return

        # This would send an HTTP request to the webhook
        # For now, just print the alert
        print(f"ALERT: Trade executed - {trade.trade_id}")

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

    async def _update_portfolio(self) -> None:
        """Update portfolio with latest quotes."""
        # Get latest quotes from all venues
        for venue, connector in self.connectors.items():
            try:
                # Get contracts for this venue
                contracts = await connector.list_contracts()
                contract_ids = [c.contract_id for c in contracts]

                # Get quotes
                quotes = await connector.get_quotes(contract_ids)

                # Update portfolio
                self.portfolio.update_quotes(quotes)

            except Exception as e:
                print(f"Failed to update quotes from {venue.value}: {e}")
                self.risk_manager.record_error(venue, e)

    def _print_status(self) -> None:
        """Print current status."""
        summary = self.portfolio.get_portfolio_summary()
        risk_summary = self.risk_manager.get_risk_summary()

        print("\n--- Live Trading Status ---")
        print(f"Balance: ${summary['current_balance']:,.2f}")
        print(f"Total PnL: ${summary['total_pnl']:,.2f}")
        print(f"Total Return: {summary['total_return_pct']:.2f}%")
        print(f"Active Positions: {summary['active_positions']}")
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Win Rate: {summary['win_rate']:.1f}%")
        print(f"Opportunities: {len(self._last_opportunities)}")

        # Print balances
        print("Account Balances:")
        for currency, balance in self._last_balances.items():
            print(f"  {balance.venue.value} {currency}: ${balance.available:,.2f}")

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
            "balances": self._last_balances,
            "is_running": self._is_running,
        }

    def get_opportunities(self) -> list[ArbOpportunity]:
        """Get last discovered opportunities."""
        return self._last_opportunities.copy()

    def get_trade_history(self) -> list[Trade]:
        """Get trade history."""
        return self.portfolio.get_trade_history()

    def get_balances(self) -> dict[str, Balance]:
        """Get current balances."""
        return self._last_balances.copy()




