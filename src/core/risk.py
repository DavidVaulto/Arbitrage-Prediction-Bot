"""Risk management and circuit breakers."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from .types import RiskLimits, Trade, Venue


class RiskManager:
    """Manages risk controls and circuit breakers."""

    def __init__(
        self,
        risk_limits: RiskLimits,
        max_drawdown_pct: float = 10.0,
        circuit_breaker_error_rate: float = 0.1,
        circuit_breaker_latency_ms: float = 5000.0,
    ):
        """Initialize risk manager.
        
        Args:
            risk_limits: Risk management limits
            max_drawdown_pct: Maximum drawdown percentage
            circuit_breaker_error_rate: Error rate threshold for circuit breaker
            circuit_breaker_latency_ms: Latency threshold for circuit breaker
        """
        self.risk_limits = risk_limits
        self.max_drawdown_pct = max_drawdown_pct
        self.circuit_breaker_error_rate = circuit_breaker_error_rate
        self.circuit_breaker_latency_ms = circuit_breaker_latency_ms

        # Track metrics for circuit breakers
        self._error_counts: dict[Venue, deque] = {
            venue: deque(maxlen=100) for venue in Venue
        }
        self._latency_measurements: dict[Venue, deque] = {
            venue: deque(maxlen=100) for venue in Venue
        }
        self._pnl_history: deque = deque(maxlen=1000)
        self._trades_history: list[Trade] = []

        # Circuit breaker states
        self._circuit_breakers: dict[Venue, bool] = dict.fromkeys(Venue, False)
        self._circuit_breaker_timestamps: dict[Venue, datetime] = {}

    def check_trade_risk(
        self,
        opportunity: any,  # ArbOpportunity
        current_positions: dict[str, float],
        balances: dict[str, any],  # Balance
    ) -> tuple[bool, str]:
        """Check if a trade meets risk criteria.
        
        Args:
            opportunity: Arbitrage opportunity
            current_positions: Current positions by event ID
            balances: Available balances
            
        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check circuit breakers
        if self._is_circuit_breaker_active(opportunity.leg_a.venue):
            return False, f"Circuit breaker active for {opportunity.leg_a.venue}"

        if self._is_circuit_breaker_active(opportunity.leg_b.venue):
            return False, f"Circuit breaker active for {opportunity.leg_b.venue}"

        # Check drawdown
        if self._check_drawdown():
            return False, "Maximum drawdown exceeded"

        # Check position limits
        event_id = opportunity.event_id
        current_exposure = current_positions.get(event_id, 0.0)
        new_exposure = current_exposure + opportunity.notional

        if new_exposure > self.risk_limits.max_position_per_event_usd:
            return False, f"Position limit exceeded for event {event_id}"

        # Check total risk
        total_exposure = sum(current_positions.values()) + opportunity.notional
        if total_exposure > self.risk_limits.max_open_risk_usd:
            return False, "Total risk limit exceeded"

        # Check edge threshold
        if opportunity.edge_bps < self.risk_limits.min_edge_bps:
            return False, f"Edge too small: {opportunity.edge_bps}bps"

        return True, "Risk check passed"

    def record_trade(self, trade: Trade) -> None:
        """Record a completed trade."""
        self._trades_history.append(trade)

        # Update PnL history
        if trade.pnl != 0:
            self._pnl_history.append(trade.pnl)

    def record_error(self, venue: Venue, error: Exception) -> None:
        """Record an error for circuit breaker."""
        self._error_counts[venue].append({
            "timestamp": datetime.utcnow(),
            "error": str(error),
        })

        # Check if circuit breaker should trigger
        if self._should_trigger_circuit_breaker(venue):
            self._trigger_circuit_breaker(venue)

    def record_latency(self, venue: Venue, latency_ms: float) -> None:
        """Record latency measurement."""
        self._latency_measurements[venue].append({
            "timestamp": datetime.utcnow(),
            "latency_ms": latency_ms,
        })

        # Check if circuit breaker should trigger
        if self._should_trigger_circuit_breaker(venue):
            self._trigger_circuit_breaker(venue)

    def _is_circuit_breaker_active(self, venue: Venue) -> bool:
        """Check if circuit breaker is active for a venue."""
        if not self._circuit_breakers[venue]:
            return False

        # Check if circuit breaker should reset
        if venue in self._circuit_breaker_timestamps:
            reset_time = self._circuit_breaker_timestamps[venue] + timedelta(minutes=5)
            if datetime.utcnow() > reset_time:
                self._circuit_breakers[venue] = False
                del self._circuit_breaker_timestamps[venue]
                return False

        return True

    def _should_trigger_circuit_breaker(self, venue: Venue) -> bool:
        """Check if circuit breaker should trigger."""
        # Check error rate
        recent_errors = self._get_recent_errors(venue, minutes=5)
        if len(recent_errors) >= 10:  # At least 10 errors in 5 minutes
            error_rate = len(recent_errors) / 100  # Assuming 100 total requests
            if error_rate > self.circuit_breaker_error_rate:
                return True

        # Check latency
        recent_latencies = self._get_recent_latencies(venue, minutes=5)
        if recent_latencies:
            avg_latency = sum(l["latency_ms"] for l in recent_latencies) / len(recent_latencies)
            if avg_latency > self.circuit_breaker_latency_ms:
                return True

        return False

    def _trigger_circuit_breaker(self, venue: Venue) -> None:
        """Trigger circuit breaker for a venue."""
        self._circuit_breakers[venue] = True
        self._circuit_breaker_timestamps[venue] = datetime.utcnow()
        print(f"Circuit breaker triggered for {venue}")

    def _get_recent_errors(self, venue: Venue, minutes: int) -> list[dict]:
        """Get recent errors for a venue."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [
            error for error in self._error_counts[venue]
            if error["timestamp"] > cutoff
        ]

    def _get_recent_latencies(self, venue: Venue, minutes: int) -> list[dict]:
        """Get recent latencies for a venue."""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return [
            latency for latency in self._latency_measurements[venue]
            if latency["timestamp"] > cutoff
        ]

    def _check_drawdown(self) -> bool:
        """Check if maximum drawdown has been exceeded."""
        if not self._pnl_history:
            return False

        # Calculate running PnL
        running_pnl = 0.0
        peak_pnl = 0.0
        max_drawdown = 0.0

        for pnl in self._pnl_history:
            running_pnl += pnl
            peak_pnl = max(peak_pnl, running_pnl)
            drawdown = peak_pnl - running_pnl
            max_drawdown = max(max_drawdown, drawdown)

        # Check if drawdown exceeds limit
        if peak_pnl > 0:
            drawdown_pct = (max_drawdown / peak_pnl) * 100
            return drawdown_pct > self.max_drawdown_pct

        return False

    def get_risk_summary(self) -> dict[str, any]:
        """Get risk management summary."""
        # Calculate current PnL
        total_pnl = sum(trade.pnl for trade in self._trades_history)

        # Calculate drawdown
        running_pnl = 0.0
        peak_pnl = 0.0
        max_drawdown = 0.0

        for pnl in self._pnl_history:
            running_pnl += pnl
            peak_pnl = max(peak_pnl, running_pnl)
            drawdown = peak_pnl - running_pnl
            max_drawdown = max(max_drawdown, drawdown)

        drawdown_pct = (max_drawdown / peak_pnl * 100) if peak_pnl > 0 else 0.0

        # Circuit breaker status
        active_circuit_breakers = [
            venue for venue, active in self._circuit_breakers.items()
            if active
        ]

        return {
            "total_pnl": total_pnl,
            "max_drawdown": max_drawdown,
            "drawdown_pct": drawdown_pct,
            "max_drawdown_limit": self.max_drawdown_pct,
            "active_circuit_breakers": active_circuit_breakers,
            "total_trades": len(self._trades_history),
            "recent_errors": {
                venue.value: len(self._get_recent_errors(venue, 5))
                for venue in Venue
            },
            "recent_latencies": {
                venue.value: self._get_recent_latencies(venue, 5)
                for venue in Venue
            },
        }

    def reset_circuit_breaker(self, venue: Venue) -> None:
        """Manually reset circuit breaker for a venue."""
        self._circuit_breakers[venue] = False
        if venue in self._circuit_breaker_timestamps:
            del self._circuit_breaker_timestamps[venue]
        print(f"Circuit breaker reset for {venue}")

    def update_risk_limits(self, new_limits: RiskLimits) -> None:
        """Update risk limits."""
        self.risk_limits = new_limits


