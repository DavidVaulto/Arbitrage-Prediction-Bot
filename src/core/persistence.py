"""Data persistence using SQLModel."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .types import (
    Balance,
    ContractSide,
    OrderSide,
    Position,
    Quote,
    Trade,
    Venue,
)


# SQLModel classes for database persistence
class TradeRecord(SQLModel, table=True):
    """Trade record for database storage."""

    __tablename__ = "trades"

    id: int | None = Field(default=None, primary_key=True)
    trade_id: str = Field(unique=True, index=True)
    event_id: str = Field(index=True)
    venue_a: str
    venue_b: str
    contract_a: str
    contract_b: str
    side_a: str
    side_b: str
    qty: float
    price_a: float
    price_b: float
    fee_a: float
    fee_b: float
    edge_bps: float
    pnl: float
    status: str
    created_at: datetime
    filled_at: datetime | None = None
    extra: str | None = None  # JSON string


class PositionRecord(SQLModel, table=True):
    """Position record for database storage."""

    __tablename__ = "positions"

    id: int | None = Field(default=None, primary_key=True)
    venue: str
    contract_id: str = Field(index=True)
    normalized_event_id: str = Field(index=True)
    side: str
    qty: float
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    created_at: datetime
    updated_at: datetime


class QuoteRecord(SQLModel, table=True):
    """Quote record for database storage."""

    __tablename__ = "quotes"

    id: int | None = Field(default=None, primary_key=True)
    venue: str
    contract_id: str = Field(index=True)
    best_bid: float
    best_ask: float
    best_bid_size: float
    best_ask_size: float
    mid_price: float | None = None
    ts: datetime


class BalanceRecord(SQLModel, table=True):
    """Balance record for database storage."""

    __tablename__ = "balances"

    id: int | None = Field(default=None, primary_key=True)
    venue: str
    currency: str
    available: float
    total: float
    ts: datetime


class PersistenceManager:
    """Manages data persistence to database."""

    def __init__(self, database_url: str):
        """Initialize persistence manager.
        
        Args:
            database_url: Database connection URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)

        # Create tables
        SQLModel.metadata.create_all(self.engine)

    def save_trade(self, trade: Trade) -> None:
        """Save trade to database."""
        trade_record = TradeRecord(
            trade_id=trade.trade_id,
            event_id=trade.event_id,
            venue_a=trade.venue_a.value,
            venue_b=trade.venue_b.value,
            contract_a=trade.contract_a,
            contract_b=trade.contract_b,
            side_a=trade.side_a.value,
            side_b=trade.side_b.value,
            qty=trade.qty,
            price_a=trade.price_a,
            price_b=trade.price_b,
            fee_a=trade.fee_a,
            fee_b=trade.fee_b,
            edge_bps=trade.edge_bps,
            pnl=trade.pnl,
            status=trade.status,
            created_at=trade.created_at,
            filled_at=trade.filled_at,
            extra=trade.extra if isinstance(trade.extra, str) else None,
        )

        with Session(self.engine) as session:
            session.add(trade_record)
            session.commit()

    def save_position(self, position: Position) -> None:
        """Save position to database."""
        position_record = PositionRecord(
            venue=position.venue.value,
            contract_id=position.contract_id,
            normalized_event_id=position.normalized_event_id,
            side=position.side.value,
            qty=position.qty,
            avg_price=position.avg_price,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            created_at=position.created_at,
            updated_at=position.updated_at,
        )

        with Session(self.engine) as session:
            # Check if position already exists
            existing = session.exec(
                select(PositionRecord).where(
                    PositionRecord.venue == position.venue.value,
                    PositionRecord.contract_id == position.contract_id,
                )
            ).first()

            if existing:
                # Update existing position
                existing.qty = position.qty
                existing.avg_price = position.avg_price
                existing.unrealized_pnl = position.unrealized_pnl
                existing.realized_pnl = position.realized_pnl
                existing.updated_at = position.updated_at
                session.add(existing)
            else:
                # Create new position
                session.add(position_record)

            session.commit()

    def save_quote(self, quote: Quote) -> None:
        """Save quote to database."""
        quote_record = QuoteRecord(
            venue=quote.venue.value,
            contract_id=quote.contract_id,
            best_bid=quote.best_bid,
            best_ask=quote.best_ask,
            best_bid_size=quote.best_bid_size,
            best_ask_size=quote.best_ask_size,
            mid_price=quote.mid_price,
            ts=quote.ts,
        )

        with Session(self.engine) as session:
            session.add(quote_record)
            session.commit()

    def save_balance(self, balance: Balance) -> None:
        """Save balance to database."""
        balance_record = BalanceRecord(
            venue=balance.venue.value,
            currency=balance.currency,
            available=balance.available,
            total=balance.total,
            ts=balance.ts,
        )

        with Session(self.engine) as session:
            session.add(balance_record)
            session.commit()

    def get_trades(
        self,
        event_id: str | None = None,
        venue: Venue | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Trade]:
        """Get trades from database."""
        with Session(self.engine) as session:
            query = select(TradeRecord)

            if event_id:
                query = query.where(TradeRecord.event_id == event_id)

            if venue:
                query = query.where(
                    (TradeRecord.venue_a == venue.value) |
                    (TradeRecord.venue_b == venue.value)
                )

            if status:
                query = query.where(TradeRecord.status == status)

            query = query.order_by(TradeRecord.created_at.desc()).limit(limit)

            records = session.exec(query).all()

            trades = []
            for record in records:
                trade = Trade(
                    trade_id=record.trade_id,
                    event_id=record.event_id,
                    venue_a=Venue(record.venue_a),
                    venue_b=Venue(record.venue_b),
                    contract_a=record.contract_a,
                    contract_b=record.contract_b,
                    side_a=OrderSide(record.side_a),
                    side_b=OrderSide(record.side_b),
                    qty=record.qty,
                    price_a=record.price_a,
                    price_b=record.price_b,
                    fee_a=record.fee_a,
                    fee_b=record.fee_b,
                    edge_bps=record.edge_bps,
                    pnl=record.pnl,
                    status=record.status,
                    created_at=record.created_at,
                    filled_at=record.filled_at,
                )
                trades.append(trade)

            return trades

    def get_positions(
        self,
        event_id: str | None = None,
        venue: Venue | None = None,
    ) -> list[Position]:
        """Get positions from database."""
        with Session(self.engine) as session:
            query = select(PositionRecord)

            if event_id:
                query = query.where(PositionRecord.normalized_event_id == event_id)

            if venue:
                query = query.where(PositionRecord.venue == venue.value)

            records = session.exec(query).all()

            positions = []
            for record in records:
                position = Position(
                    venue=Venue(record.venue),
                    contract_id=record.contract_id,
                    normalized_event_id=record.normalized_event_id,
                    side=ContractSide(record.side),
                    qty=record.qty,
                    avg_price=record.avg_price,
                    unrealized_pnl=record.unrealized_pnl,
                    realized_pnl=record.realized_pnl,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                positions.append(position)

            return positions

    def get_quotes(
        self,
        contract_id: str | None = None,
        venue: Venue | None = None,
        limit: int = 100,
    ) -> list[Quote]:
        """Get quotes from database."""
        with Session(self.engine) as session:
            query = select(QuoteRecord)

            if contract_id:
                query = query.where(QuoteRecord.contract_id == contract_id)

            if venue:
                query = query.where(QuoteRecord.venue == venue.value)

            query = query.order_by(QuoteRecord.ts.desc()).limit(limit)

            records = session.exec(query).all()

            quotes = []
            for record in records:
                quote = Quote(
                    venue=Venue(record.venue),
                    contract_id=record.contract_id,
                    best_bid=record.best_bid,
                    best_ask=record.best_ask,
                    best_bid_size=record.best_bid_size,
                    best_ask_size=record.best_ask_size,
                    ts=record.ts,
                    mid_price=record.mid_price,
                )
                quotes.append(quote)

            return quotes

    def get_balances(self, venue: Venue | None = None) -> list[Balance]:
        """Get balances from database."""
        with Session(self.engine) as session:
            query = select(BalanceRecord)

            if venue:
                query = query.where(BalanceRecord.venue == venue.value)

            query = query.order_by(BalanceRecord.ts.desc())

            records = session.exec(query).all()

            balances = []
            for record in records:
                balance = Balance(
                    venue=Venue(record.venue),
                    currency=record.currency,
                    available=record.available,
                    total=record.total,
                    ts=record.ts,
                )
                balances.append(balance)

            return balances

    def get_portfolio_summary(self) -> dict[str, any]:
        """Get portfolio summary from database."""
        with Session(self.engine) as session:
            # Get total trades
            total_trades = len(session.exec(select(TradeRecord)).all())

            # Get total PnL
            trades = session.exec(select(TradeRecord)).all()
            total_pnl = sum(trade.pnl for trade in trades)

            # Get active positions
            positions = session.exec(select(PositionRecord)).all()
            active_positions = sum(1 for pos in positions if pos.qty > 0)

            # Get total exposure
            total_exposure = sum(pos.qty * pos.avg_price for pos in positions if pos.qty > 0)

            return {
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "active_positions": active_positions,
                "total_exposure": total_exposure,
            }

    def cleanup_old_data(self, days_to_keep: int = 30) -> None:
        """Clean up old data from database."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        with Session(self.engine) as session:
            # Clean up old quotes
            old_quotes = session.exec(
                select(QuoteRecord).where(QuoteRecord.ts < cutoff_date)
            ).all()

            for quote in old_quotes:
                session.delete(quote)

            session.commit()

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, 'engine'):
            self.engine.dispose()
