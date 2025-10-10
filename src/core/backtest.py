"""Backtesting engine for historical data analysis."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from .config import settings
from .discovery import DiscoveryEngine
from .fees import create_default_fee_calculator
from .matcher import EventMatcher
from .portfolio import Portfolio
from .risk import RiskManager
from .sizing import PositionSizer
from .types import (
    ArbOpportunity,
    BacktestResult,
    Balance,
    Contract,
    ContractSide,
    Quote,
    Trade,
    Venue,
)


class BacktestEngine:
    """Backtesting engine for historical data analysis."""

    def __init__(self):
        """Initialize backtest engine."""
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

        # Historical data
        self._historical_data: dict[str, pd.DataFrame] = {}
        self._current_time: datetime | None = None
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None

    def load_historical_data(
        self,
        data_file: str,
        start_date: datetime,
        end_date: datetime,
    ) -> None:
        """Load historical data from file.
        
        Args:
            data_file: Path to historical data file (CSV/Parquet)
            start_date: Start date for backtest
            end_date: End date for backtest
        """
        self._start_time = start_date
        self._end_time = end_date

        # Load data
        if data_file.endswith('.parquet'):
            df = pd.read_parquet(data_file)
        else:
            df = pd.read_csv(data_file)

        # Parse timestamps
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Filter by date range
        df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]

        # Group by venue
        for venue in Venue:
            venue_data = df[df['venue'] == venue.value].copy()
            if not venue_data.empty:
                self._historical_data[venue.value] = venue_data

        print(f"Loaded historical data: {len(df)} records")
        print(f"Date range: {start_date} to {end_date}")
        print(f"Venues: {list(self._historical_data.keys())}")

    def run_backtest(self) -> BacktestResult:
        """Run the backtest."""
        if not self._historical_data:
            raise ValueError("No historical data loaded")

        print("Starting backtest...")

        # Get all unique timestamps
        all_timestamps = set()
        for df in self._historical_data.values():
            all_timestamps.update(df['timestamp'].dt.to_pydatetime())

        timestamps = sorted(all_timestamps)

        # Run simulation
        for timestamp in timestamps:
            self._current_time = timestamp

            # Get data for this timestamp
            current_data = self._get_data_at_timestamp(timestamp)

            if not current_data:
                continue

            # Discover opportunities
            opportunities = self._discover_opportunities_at_timestamp(current_data)

            # Process opportunities
            self._process_opportunities(opportunities)

            # Update portfolio
            self._update_portfolio_at_timestamp(current_data)

        # Calculate results
        result = self._calculate_backtest_results()

        print("Backtest completed!")
        print(f"Total trades: {result.total_trades}")
        print(f"Successful trades: {result.successful_trades}")
        print(f"Total PnL: ${result.total_pnl:.2f}")
        print(f"Max drawdown: ${result.max_drawdown:.2f}")
        print(f"Sharpe ratio: {result.sharpe_ratio:.2f}")
        print(f"Win rate: {result.win_rate:.1f}%")

        return result

    def _get_data_at_timestamp(self, timestamp: datetime) -> dict[str, pd.DataFrame]:
        """Get data for a specific timestamp."""
        current_data = {}

        for venue, df in self._historical_data.items():
            # Get data within 1 minute of timestamp
            time_window = timedelta(minutes=1)
            venue_data = df[
                (df['timestamp'] >= timestamp - time_window) &
                (df['timestamp'] <= timestamp + time_window)
            ].copy()

            if not venue_data.empty:
                current_data[venue] = venue_data

        return current_data

    def _discover_opportunities_at_timestamp(
        self,
        current_data: dict[str, pd.DataFrame],
    ) -> list[ArbOpportunity]:
        """Discover opportunities at a specific timestamp."""
        # Convert data to contracts and quotes
        contracts = self._data_to_contracts(current_data)
        quotes = self._data_to_quotes(current_data)

        # Update discovery engine with current data
        self.discovery_engine._contracts_cache = contracts
        self.discovery_engine._quotes_cache = quotes

        # Get matched pairs
        matched_pairs = self.discovery_engine._get_matched_pairs()

        # Find opportunities
        opportunities = []
        for pair in matched_pairs:
            pair_opportunities = self.discovery_engine._find_pair_opportunities(pair)
            opportunities.extend(pair_opportunities)

        return opportunities

    def _data_to_contracts(self, current_data: dict[str, pd.DataFrame]) -> dict[Venue, list[Contract]]:
        """Convert historical data to contracts."""
        contracts = {}

        for venue_name, df in current_data.items():
            venue = Venue(venue_name)
            venue_contracts = []

            for _, row in df.iterrows():
                # Create YES contract
                yes_contract = Contract(
                    venue=venue,
                    contract_id=f"{row['contract_id']}_YES",
                    event_key=row.get('event_key', ''),
                    normalized_event_id=row['contract_id'],
                    side=ContractSide.YES,
                    tick_size=0.01,
                    settlement_ccy=row.get('settlement_ccy', 'USD'),
                    expires_at=row.get('expires_at', datetime.utcnow()),
                    fees=settings.get_venue_fees(venue),
                )
                venue_contracts.append(yes_contract)

                # Create NO contract
                no_contract = Contract(
                    venue=venue,
                    contract_id=f"{row['contract_id']}_NO",
                    event_key=row.get('event_key', ''),
                    normalized_event_id=row['contract_id'],
                    side=ContractSide.NO,
                    tick_size=0.01,
                    settlement_ccy=row.get('settlement_ccy', 'USD'),
                    expires_at=row.get('expires_at', datetime.utcnow()),
                    fees=settings.get_venue_fees(venue),
                )
                venue_contracts.append(no_contract)

            contracts[venue] = venue_contracts

        return contracts

    def _data_to_quotes(self, current_data: dict[str, pd.DataFrame]) -> dict[str, Quote]:
        """Convert historical data to quotes."""
        quotes = {}

        for venue_name, df in current_data.items():
            venue = Venue(venue_name)

            for _, row in df.iterrows():
                # Create YES quote
                yes_quote = Quote(
                    venue=venue,
                    contract_id=f"{row['contract_id']}_YES",
                    best_bid=row.get('yes_bid', 0.0),
                    best_ask=row.get('yes_ask', 1.0),
                    best_bid_size=row.get('yes_bid_size', 100.0),
                    best_ask_size=row.get('yes_ask_size', 100.0),
                    ts=self._current_time,
                )
                quotes[yes_quote.contract_id] = yes_quote

                # Create NO quote
                no_quote = Quote(
                    venue=venue,
                    contract_id=f"{row['contract_id']}_NO",
                    best_bid=row.get('no_bid', 0.0),
                    best_ask=row.get('no_ask', 1.0),
                    best_bid_size=row.get('no_bid_size', 100.0),
                    best_ask_size=row.get('no_ask_size', 100.0),
                    ts=self._current_time,
                )
                quotes[no_quote.contract_id] = no_quote

        return quotes

    def _process_opportunities(self, opportunities: list[ArbOpportunity]) -> None:
        """Process opportunities at current timestamp."""
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
                    continue

                # Calculate position size
                position_size = self.position_sizer.calculate_position_size(
                    opportunity,
                    balances,
                    current_positions,
                )

                if position_size <= 0:
                    continue

                # Execute trade
                trade = self._execute_backtest_trade(opportunity, position_size)

                if trade:
                    # Record trade
                    self.portfolio.add_trade(trade)
                    self.risk_manager.record_trade(trade)

            except Exception as e:
                print(f"Error processing opportunity: {e}")

    def _execute_backtest_trade(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> Trade | None:
        """Execute a backtest trade."""
        # Simulate trade execution
        trade = Trade(
            trade_id=f"backtest_{self._current_time.timestamp()}",
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
            pnl=self._calculate_backtest_pnl(opportunity, position_size),
            status="filled",
            created_at=self._current_time,
            filled_at=self._current_time,
        )

        return trade

    def _simulate_fee(self, venue: Venue, qty: float) -> float:
        """Simulate trading fees."""
        fee_model = settings.get_venue_fees(venue)
        return qty * (fee_model.taker_bps / 10000.0)

    def _calculate_backtest_pnl(self, opportunity: ArbOpportunity, qty: float) -> float:
        """Calculate PnL for backtest trade."""
        edge_decimal = opportunity.edge_bps / 10000.0
        gross_pnl = qty * edge_decimal

        # Subtract estimated fees
        fee_a = self._simulate_fee(opportunity.leg_a.venue, qty)
        fee_b = self._simulate_fee(opportunity.leg_b.venue, qty)

        net_pnl = gross_pnl - fee_a - fee_b
        return net_pnl

    def _update_portfolio_at_timestamp(self, current_data: dict[str, pd.DataFrame]) -> None:
        """Update portfolio at current timestamp."""
        # Convert data to quotes
        quotes = self._data_to_quotes(current_data)

        # Update portfolio
        self.portfolio.update_quotes(list(quotes.values()))

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
        # For backtesting, return mock balances
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

    def _calculate_backtest_results(self) -> BacktestResult:
        """Calculate backtest results."""
        trades = self.portfolio.get_trade_history()

        if not trades:
            return BacktestResult(
                start_date=self._start_time or datetime.utcnow(),
                end_date=self._end_time or datetime.utcnow(),
                total_trades=0,
                successful_trades=0,
                total_pnl=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                win_rate=0.0,
                avg_edge_bps=0.0,
                total_fees=0.0,
            )

        # Basic statistics
        total_trades = len(trades)
        successful_trades = sum(1 for t in trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in trades)
        total_fees = sum(t.fee_a + t.fee_b for t in trades)
        win_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0.0
        avg_edge_bps = sum(t.edge_bps for t in trades) / total_trades if total_trades > 0 else 0.0

        # Calculate drawdown
        running_pnl = 0.0
        peak_pnl = 0.0
        max_drawdown = 0.0

        for trade in trades:
            running_pnl += trade.pnl
            peak_pnl = max(peak_pnl, running_pnl)
            drawdown = peak_pnl - running_pnl
            max_drawdown = max(max_drawdown, drawdown)

        # Calculate Sharpe ratio
        if total_trades > 1:
            pnl_values = [t.pnl for t in trades]
            mean_pnl = sum(pnl_values) / len(pnl_values)
            variance = sum((x - mean_pnl) ** 2 for x in pnl_values) / (len(pnl_values) - 1)
            std_dev = variance ** 0.5

            sharpe_ratio = mean_pnl / std_dev if std_dev > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        return BacktestResult(
            start_date=self._start_time or datetime.utcnow(),
            end_date=self._end_time or datetime.utcnow(),
            total_trades=total_trades,
            successful_trades=successful_trades,
            total_pnl=total_pnl,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            avg_edge_bps=avg_edge_bps,
            total_fees=total_fees,
        )




