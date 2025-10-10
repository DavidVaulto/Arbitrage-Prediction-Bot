"""Position sizing algorithms for arbitrage trades."""

from __future__ import annotations

from .types import ArbOpportunity, Balance, RiskLimits, Venue


class PositionSizer:
    """Calculates optimal position sizes for arbitrage trades."""

    def __init__(
        self,
        risk_limits: RiskLimits,
        kelly_fraction: float = 0.25,
        bankroll: float = 10000.0,
    ):
        """Initialize position sizer.
        
        Args:
            risk_limits: Risk management limits
            kelly_fraction: Kelly fraction multiplier
            bankroll: Available bankroll
        """
        self.risk_limits = risk_limits
        self.kelly_fraction = kelly_fraction
        self.bankroll = bankroll

    def calculate_position_size(
        self,
        opportunity: ArbOpportunity,
        balances: dict[str, Balance],
        existing_positions: dict[str, float],
    ) -> float:
        """Calculate optimal position size for an opportunity.
        
        Args:
            opportunity: Arbitrage opportunity
            balances: Available balances by currency
            existing_positions: Existing positions by event ID
            
        Returns:
            Recommended position size
        """
        # Start with Kelly-based sizing
        kelly_size = self._calculate_kelly_size(opportunity)

        # Apply risk limits
        risk_limited_size = self._apply_risk_limits(
            kelly_size,
            opportunity,
            existing_positions,
        )

        # Apply balance constraints
        balance_limited_size = self._apply_balance_constraints(
            risk_limited_size,
            opportunity,
            balances,
        )

        # Round to venue tick sizes
        final_size = self._round_to_venue_ticks(
            balance_limited_size,
            opportunity,
        )

        return max(0.0, final_size)

    def _calculate_kelly_size(self, opportunity: ArbOpportunity) -> float:
        """Calculate Kelly-optimal position size."""
        # Convert edge to Kelly fraction
        edge_decimal = opportunity.edge_bps / 10000.0

        # Kelly formula: f = (bp - q) / b
        # For arbitrage: b = 1 (1:1 payout), p = 0.5 (risk-neutral), q = 0.5
        # f = (1 * 0.5 - 0.5) / 1 = 0 (no edge in risk-neutral case)
        # But we have a guaranteed edge, so use the edge directly
        kelly_fraction = min(edge_decimal, 0.25)  # Cap at 25%

        # Apply Kelly fraction multiplier
        adjusted_fraction = kelly_fraction * self.kelly_fraction

        # Calculate size
        size = self.bankroll * adjusted_fraction / opportunity.notional

        return size

    def _apply_risk_limits(
        self,
        size: float,
        opportunity: ArbOpportunity,
        existing_positions: dict[str, float],
    ) -> float:
        """Apply risk management limits."""
        # Calculate notional for this size
        notional = size * opportunity.notional

        # Apply per-trade limit
        max_per_trade = self.risk_limits.max_per_trade_usd
        if notional > max_per_trade:
            size = max_per_trade / opportunity.notional

        # Apply per-event limit
        event_id = opportunity.event_id
        existing_event_exposure = existing_positions.get(event_id, 0.0)
        max_per_event = self.risk_limits.max_position_per_event_usd

        if existing_event_exposure + notional > max_per_event:
            remaining_capacity = max_per_event - existing_event_exposure
            if remaining_capacity > 0:
                size = remaining_capacity / opportunity.notional
            else:
                size = 0.0

        # Apply total open risk limit
        total_exposure = sum(existing_positions.values()) + notional
        max_total_risk = self.risk_limits.max_open_risk_usd

        if total_exposure > max_total_risk:
            remaining_capacity = max_total_risk - sum(existing_positions.values())
            if remaining_capacity > 0:
                size = remaining_capacity / opportunity.notional
            else:
                size = 0.0

        return size

    def _apply_balance_constraints(
        self,
        size: float,
        opportunity: ArbOpportunity,
        balances: dict[str, Balance],
    ) -> float:
        """Apply balance constraints."""
        # Calculate required capital for both legs
        leg_a_cost = size * opportunity.leg_a.price
        leg_b_cost = size * opportunity.leg_b.price
        total_cost = leg_a_cost + leg_b_cost

        # Check available balances
        venue_a_balance = self._get_venue_balance(
            opportunity.leg_a.venue,
            balances,
        )
        venue_b_balance = self._get_venue_balance(
            opportunity.leg_b.venue,
            balances,
        )

        # Limit by available balances
        if venue_a_balance and leg_a_cost > venue_a_balance.available:
            size = venue_a_balance.available / opportunity.leg_a.price

        if venue_b_balance and leg_b_cost > venue_b_balance.available:
            size = min(size, venue_b_balance.available / opportunity.leg_b.price)

        return size

    def _get_venue_balance(
        self,
        venue: Venue,
        balances: dict[str, Balance],
    ) -> Balance | None:
        """Get balance for a specific venue."""
        for balance in balances.values():
            if balance.venue == venue:
                return balance
        return None

    def _round_to_venue_ticks(
        self,
        size: float,
        opportunity: ArbOpportunity,
    ) -> float:
        """Round size to venue tick sizes."""
        # For now, assume minimum size of 1.0
        # In practice, this would use contract-specific tick sizes
        return max(1.0, round(size))

    def update_bankroll(self, new_bankroll: float) -> None:
        """Update available bankroll."""
        self.bankroll = new_bankroll

    def get_sizing_summary(
        self,
        opportunity: ArbOpportunity,
        balances: dict[str, Balance],
        existing_positions: dict[str, float],
    ) -> dict[str, float]:
        """Get detailed sizing summary."""
        kelly_size = self._calculate_kelly_size(opportunity)
        risk_limited_size = self._apply_risk_limits(
            kelly_size,
            opportunity,
            existing_positions,
        )
        balance_limited_size = self._apply_balance_constraints(
            risk_limited_size,
            opportunity,
            balances,
        )
        final_size = self._round_to_venue_ticks(
            balance_limited_size,
            opportunity,
        )

        return {
            "kelly_size": kelly_size,
            "risk_limited_size": risk_limited_size,
            "balance_limited_size": balance_limited_size,
            "final_size": final_size,
            "notional": final_size * opportunity.notional,
            "edge_bps": opportunity.edge_bps,
            "expected_pnl": final_size * opportunity.notional * (opportunity.edge_bps / 10000.0),
        }


class FixedSizeSizer(PositionSizer):
    """Fixed position size sizer."""

    def __init__(self, fixed_size: float = 100.0):
        """Initialize with fixed size.
        
        Args:
            fixed_size: Fixed position size
        """
        super().__init__(RiskLimits(0, 0, 0, 0, 0, 0), 0, 0)
        self.fixed_size = fixed_size

    def calculate_position_size(
        self,
        opportunity: ArbOpportunity,
        balances: dict[str, Balance],
        existing_positions: dict[str, float],
    ) -> float:
        """Return fixed size."""
        return self.fixed_size


class PercentageSizer(PositionSizer):
    """Percentage-based position sizer."""

    def __init__(self, percentage: float = 0.01):
        """Initialize with percentage of bankroll.
        
        Args:
            percentage: Percentage of bankroll to use
        """
        super().__init__(RiskLimits(0, 0, 0, 0, 0, 0), 0, 0)
        self.percentage = percentage

    def calculate_position_size(
        self,
        opportunity: ArbOpportunity,
        balances: dict[str, Balance],
        existing_positions: dict[str, float],
    ) -> float:
        """Calculate size as percentage of bankroll."""
        target_notional = self.bankroll * self.percentage
        size = target_notional / opportunity.notional
        return max(1.0, round(size))


