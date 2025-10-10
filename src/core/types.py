"""Core data models for the arbitrage system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Venue(str, Enum):
    """Supported trading venues."""

    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


class TradingMode(str, Enum):
    """Trading execution modes."""

    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class OrderSide(str, Enum):
    """Order side enumeration."""

    BUY = "BUY"
    SELL = "SELL"


class OrderTIF(str, Enum):
    """Time in force for orders."""

    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTC = "GTC"  # Good Till Cancel


class ContractSide(str, Enum):
    """Binary contract sides."""

    YES = "YES"
    NO = "NO"


class EventId(BaseModel):
    """Normalized event identifier."""

    raw_event_id: str = Field(..., description="Raw venue event ID")
    normalized_id: str = Field(..., description="Normalized event identifier")
    title: str = Field(..., description="Event title")
    expiry: datetime = Field(..., description="Event expiry time")
    resolution_source: str | None = Field(None, description="Resolution source")


@dataclass
class FeeModel:
    """Fee structure for a venue."""

    maker_bps: float = 0.0
    taker_bps: float = 0.0
    withdrawal_fee: float | None = None
    gas_estimate_usd: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Contract:
    """Binary prediction market contract."""

    venue: Venue
    contract_id: str
    event_key: str
    normalized_event_id: str
    side: ContractSide
    tick_size: float
    settlement_ccy: str
    expires_at: datetime
    fees: FeeModel
    min_size: float = 1.0
    max_size: float | None = None


@dataclass
class Quote:
    """Market quote for a contract."""

    venue: Venue
    contract_id: str
    best_bid: float
    best_ask: float
    best_bid_size: float
    best_ask_size: float
    ts: datetime
    mid_price: float | None = None

    def __post_init__(self) -> None:
        """Calculate mid price after initialization."""
        if self.mid_price is None:
            self.mid_price = (self.best_bid + self.best_ask) / 2


@dataclass
class OrderRequest:
    """Order placement request."""

    venue: Venue
    contract_id: str
    side: OrderSide
    price: float
    qty: float
    tif: OrderTIF = OrderTIF.IOC
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        """Generate client order ID if not provided."""
        if self.client_order_id is None:
            self.client_order_id = str(uuid.uuid4())


@dataclass
class Fill:
    """Order fill information."""

    venue: Venue
    contract_id: str
    side: OrderSide
    avg_price: float
    qty: float
    fee_paid: float
    ts: datetime
    venue_order_id: str | None = None
    client_order_id: str | None = None


@dataclass
class ArbOpportunity:
    """Arbitrage opportunity between two venues."""

    event_id: str
    leg_a: OrderRequest
    leg_b: OrderRequest
    edge_bps: float
    notional: float
    expiry: datetime
    rationale: str
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Position in a contract."""

    venue: Venue
    contract_id: str
    normalized_event_id: str
    side: ContractSide
    qty: float
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Balance:
    """Account balance for a venue."""

    venue: Venue
    currency: str
    available: float
    total: float
    ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Trade:
    """Completed trade record."""

    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str = ""
    venue_a: Venue = Venue.POLYMARKET
    venue_b: Venue = Venue.KALSHI
    contract_a: str = ""
    contract_b: str = ""
    side_a: OrderSide = OrderSide.BUY
    side_b: OrderSide = OrderSide.BUY
    qty: float = 0.0
    price_a: float = 0.0
    price_b: float = 0.0
    fee_a: float = 0.0
    fee_b: float = 0.0
    edge_bps: float = 0.0
    pnl: float = 0.0
    status: Literal["pending", "partial", "filled", "failed", "hedged"] = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None


@dataclass
class MatchedPair:
    """Matched contract pair across venues."""

    event_id: str
    contract_a: Contract
    contract_b: Contract
    confidence_score: float
    match_reason: str


@dataclass
class RiskLimits:
    """Risk management limits."""

    max_open_risk_usd: float
    max_per_trade_usd: float
    max_position_per_event_usd: float
    max_drawdown_pct: float
    min_edge_bps: float
    max_slippage_bps: float


@dataclass
class HealthStatus:
    """System health status."""

    venue: Venue
    is_healthy: bool
    latency_ms: float
    error_rate: float
    last_update: datetime
    message: str = ""


@dataclass
class BacktestResult:
    """Backtest execution results."""

    start_date: datetime
    end_date: datetime
    total_trades: int
    successful_trades: int
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    avg_edge_bps: float
    total_fees: float


