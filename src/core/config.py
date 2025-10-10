"""Configuration management using pydantic-settings."""

from __future__ import annotations

from typing import Any

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .types import FeeModel, RiskLimits, TradingMode, Venue


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Trading Configuration
    mode: TradingMode = TradingMode.PAPER
    base_ccy: str = "USD"
    starting_balance_usd: float = 10000.0

    # Position Sizing
    size_policy: str = "kelly_fraction"
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)

    # Risk Management
    min_edge_bps: float = Field(default=80.0, ge=0.0)
    max_slippage_bps: float = Field(default=25.0, ge=0.0)
    max_open_risk_usd: float = Field(default=3000.0, ge=0.0)
    max_per_trade_usd: float = Field(default=1000.0, ge=0.0)
    max_position_per_event_usd: float = Field(default=5000.0, ge=0.0)
    min_notional_usd: float = Field(default=100.0, ge=0.0)
    max_drawdown_pct: float = Field(default=10.0, ge=0.0, le=100.0)

    # Circuit Breakers
    circuit_breaker_error_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    circuit_breaker_latency_ms: float = Field(default=5000.0, ge=0.0)

    # Safety Guards
    confirm_live: bool = False
    use_stubs: bool = Field(default=False, description="Use stub connectors for offline testing")

    # Data Refresh Intervals (seconds)
    discovery_interval: float = Field(default=2.0, ge=0.1)
    quote_refresh_interval: float = Field(default=1.0, ge=0.1)

    # API Credentials
    polymarket_api_key: str | None = None
    polymarket_private_key: str | None = None
    kalshi_api_key: str | None = None
    kalshi_api_secret: str | None = None
    
    # Kalshi Public API
    kalshi_public_base: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_use_public: bool = Field(default=True, description="Use Kalshi public endpoints (no auth required)")

    # Database
    database_url: str = "sqlite:///./pm_arb.db"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Health & Metrics
    health_check_port: int = Field(default=8080, ge=1024, le=65535)
    metrics_port: int = Field(default=9090, ge=1024, le=65535)

    # Alerting
    alert_webhook: str | None = None

    # Fee Overrides (basis points)
    polymarket_maker_bps: float = Field(default=0.0, ge=0.0)
    polymarket_taker_bps: float = Field(default=25.0, ge=0.0)
    polymarket_gas_estimate_usd: float = Field(default=0.50, ge=0.0)

    kalshi_maker_bps: float = Field(default=0.0, ge=0.0)
    kalshi_taker_bps: float = Field(default=30.0, ge=0.0)

    @validator("mode")
    def validate_mode(cls, v: str) -> TradingMode:
        """Validate trading mode."""
        try:
            return TradingMode(v.lower())
        except ValueError:
            raise ValueError(f"Invalid trading mode: {v}")

    @validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @validator("log_format")
    def validate_log_format(cls, v: str) -> str:
        """Validate log format."""
        valid_formats = {"json", "text"}
        if v.lower() not in valid_formats:
            raise ValueError(f"Invalid log format: {v}")
        return v.lower()

    def get_risk_limits(self) -> RiskLimits:
        """Get risk limits configuration."""
        return RiskLimits(
            max_open_risk_usd=self.max_open_risk_usd,
            max_per_trade_usd=self.max_per_trade_usd,
            max_position_per_event_usd=self.max_position_per_event_usd,
            max_drawdown_pct=self.max_drawdown_pct,
            min_edge_bps=self.min_edge_bps,
            max_slippage_bps=self.max_slippage_bps,
        )

    def get_venue_fees(self, venue: Venue) -> FeeModel:
        """Get fee model for a venue."""
        if venue == Venue.POLYMARKET:
            return FeeModel(
                maker_bps=self.polymarket_maker_bps,
                taker_bps=self.polymarket_taker_bps,
                gas_estimate_usd=self.polymarket_gas_estimate_usd,
            )
        elif venue == Venue.KALSHI:
            return FeeModel(
                maker_bps=self.kalshi_maker_bps,
                taker_bps=self.kalshi_taker_bps,
            )
        else:
            raise ValueError(f"Unknown venue: {venue}")

    def is_live_trading_enabled(self) -> bool:
        """Check if live trading is enabled and confirmed."""
        return self.mode == TradingMode.LIVE and self.confirm_live

    def get_venue_credentials(self, venue: Venue) -> dict[str, Any]:
        """Get API credentials for a venue."""
        if venue == Venue.POLYMARKET:
            return {
                "api_key": self.polymarket_api_key,
                "private_key": self.polymarket_private_key,
            }
        elif venue == Venue.KALSHI:
            return {
                "api_key": self.kalshi_api_key,
                "api_secret": self.kalshi_api_secret,
            }
        else:
            raise ValueError(f"Unknown venue: {venue}")


# Global settings instance
settings = Settings()
