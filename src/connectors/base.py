"""Base connector protocol for exchange integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from ..core.types import Balance, Contract, Fill, OrderRequest, Quote, Venue


class VenueClient(Protocol):
    """Protocol for venue-specific trading clients."""

    @property
    def venue(self) -> Venue:
        """Get the venue this client connects to."""
        ...

    async def list_contracts(self) -> list[Contract]:
        """List all available contracts.
        
        Returns:
            List of available contracts
        """
        ...

    async def get_quotes(self, contract_ids: list[str]) -> list[Quote]:
        """Get current quotes for specified contracts.
        
        Args:
            contract_ids: List of contract IDs to get quotes for
            
        Returns:
            List of current quotes
        """
        ...

    async def place_order(self, req: OrderRequest) -> Fill | None:
        """Place an order.
        
        Args:
            req: Order request
            
        Returns:
            Fill information if order was executed, None otherwise
        """
        ...

    async def cancel_order(self, venue_order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            venue_order_id: Venue-specific order ID
            
        Returns:
            True if order was cancelled, False otherwise
        """
        ...

    async def get_balance(self) -> dict[str, Balance]:
        """Get account balances.
        
        Returns:
            Dictionary mapping currency to balance
        """
        ...

    async def healthcheck(self) -> bool:
        """Check if the venue is healthy and accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        ...


class BaseConnector(ABC):
    """Base class for venue connectors."""

    def __init__(self, venue: Venue, credentials: dict[str, str]):
        """Initialize connector.
        
        Args:
            venue: Trading venue
            credentials: API credentials
        """
        self.venue = venue
        self.credentials = credentials
        self._is_connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the venue."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the venue."""
        pass

    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._is_connected

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


class MockConnector(BaseConnector):
    """Mock connector for testing and development."""

    def __init__(self, venue: Venue, credentials: dict[str, str]):
        """Initialize mock connector."""
        super().__init__(venue, credentials)
        self._contracts: list[Contract] = []
        self._quotes: dict[str, Quote] = {}
        self._balances: dict[str, Balance] = {}
        self._orders: dict[str, OrderRequest] = {}

    async def connect(self) -> None:
        """Mock connection."""
        self._is_connected = True

    async def disconnect(self) -> None:
        """Mock disconnection."""
        self._is_connected = False

    async def list_contracts(self) -> list[Contract]:
        """Return mock contracts."""
        return self._contracts.copy()

    async def get_quotes(self, contract_ids: list[str]) -> list[Quote]:
        """Return mock quotes."""
        quotes = []
        for contract_id in contract_ids:
            if contract_id in self._quotes:
                quotes.append(self._quotes[contract_id])
        return quotes

    async def place_order(self, req: OrderRequest) -> Fill | None:
        """Mock order placement."""
        # Store the order
        self._orders[req.client_order_id or "mock_id"] = req

        # Create a mock fill
        fill = Fill(
            venue=self.venue,
            contract_id=req.contract_id,
            side=req.side,
            avg_price=req.price,
            qty=req.qty,
            fee_paid=0.0,
            ts=req.ts if hasattr(req, 'ts') else None,
            client_order_id=req.client_order_id,
        )
        return fill

    async def cancel_order(self, venue_order_id: str) -> bool:
        """Mock order cancellation."""
        return venue_order_id in self._orders

    async def get_balance(self) -> dict[str, Balance]:
        """Return mock balances."""
        return self._balances.copy()

    async def healthcheck(self) -> bool:
        """Mock health check."""
        return self._is_connected

    def add_mock_contract(self, contract: Contract) -> None:
        """Add a mock contract."""
        self._contracts.append(contract)

    def add_mock_quote(self, quote: Quote) -> None:
        """Add a mock quote."""
        self._quotes[quote.contract_id] = quote

    def add_mock_balance(self, balance: Balance) -> None:
        """Add a mock balance."""
        self._balances[balance.currency] = balance

    def set_mock_quotes(self, quotes: dict[str, Quote]) -> None:
        """Set mock quotes."""
        self._quotes = quotes.copy()

    def set_mock_balances(self, balances: dict[str, Balance]) -> None:
        """Set mock balances."""
        self._balances = balances.copy()


