"""Kalshi connector implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..core.types import (
    Balance,
    Contract,
    ContractSide,
    FeeModel,
    Fill,
    OrderRequest,
    OrderSide,
    Quote,
    Venue,
)
from .base import BaseConnector


class KalshiConnector(BaseConnector):
    """Connector for Kalshi exchange."""

    def __init__(self, credentials: dict[str, str], use_public: bool = True, public_base_url: str | None = None):
        """Initialize Kalshi connector.
        
        Args:
            credentials: Dictionary with 'api_key' and 'api_secret'
            use_public: If True, use public endpoints (no auth required)
            public_base_url: Base URL for public API
        """
        super().__init__(Venue.KALSHI, credentials)
        self.api_key = credentials.get("api_key")
        self.api_secret = credentials.get("api_secret")
        self.use_public = use_public
        self.base_url = public_base_url or "https://api.elections.kalshi.com/trade-api/v2"
        self.auth_base_url = "https://trading-api.kalshi.com"
        self.client: httpx.AsyncClient | None = None
        self.public_client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Establish connection to Kalshi."""
        if self.use_public:
            # Public API - no auth required
            self.public_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        else:
            # Authenticated API
            self.client = httpx.AsyncClient(
                base_url=self.auth_base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        self._is_connected = True

    async def disconnect(self) -> None:
        """Close connection to Kalshi."""
        if self.client:
            await self.client.aclose()
            self.client = None
        if self.public_client:
            await self.public_client.aclose()
            self.public_client = None
        self._is_connected = False
    
    async def list_markets_public(self, limit: int = 100) -> list[dict[str, Any]]:
        """List markets using public API.
        
        Args:
            limit: Maximum number of markets to return
            
        Returns:
            List of market dictionaries
        """
        if not self.public_client:
            raise RuntimeError("Public client not connected")
        
        try:
            response = await self.public_client.get(
                "/markets",
                params={"limit": limit, "status": "open"}
            )
            response.raise_for_status()
            data = response.json()
            
            markets = data.get("markets", [])
            return markets
            
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch public markets: {e}")
    
    async def get_quotes_public(self, tickers: list[str] | None = None) -> list[Quote]:
        """Get quotes using public API.
        
        Args:
            tickers: Optional list of ticker symbols to fetch
            
        Returns:
            List of Quote objects
        """
        if not self.public_client:
            raise RuntimeError("Public client not connected")
        
        quotes = []
        
        try:
            # If no tickers specified, fetch active markets
            if not tickers:
                markets = await self.list_markets_public(limit=50)
            else:
                # Fetch specific markets
                markets = []
                for ticker in tickers:
                    try:
                        response = await self.public_client.get(f"/markets/{ticker}")
                        response.raise_for_status()
                        data = response.json()
                        if data.get("market"):
                            markets.append(data["market"])
                    except httpx.HTTPError as e:
                        print(f"Failed to fetch market {ticker}: {e}")
                        continue
            
            # Parse quotes from markets
            for market in markets:
                quote = self._parse_public_quote(market)
                if quote:
                    quotes.append(quote)
            
            return quotes
            
        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch public quotes: {e}")

    async def list_contracts(self) -> list[Contract]:
        """List all available contracts."""
        if not self.client:
            raise RuntimeError("Not connected to Kalshi")

        try:
            response = await self.client.get("/markets")
            response.raise_for_status()
            data = response.json()

            contracts = []
            for market in data.get("markets", []):
                # Extract YES contract
                yes_contract = self._parse_contract(market, ContractSide.YES)
                if yes_contract:
                    contracts.append(yes_contract)

                # Extract NO contract
                no_contract = self._parse_contract(market, ContractSide.NO)
                if no_contract:
                    contracts.append(no_contract)

            return contracts

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch contracts: {e}")

    async def get_quotes(self, contract_ids: list[str]) -> list[Quote]:
        """Get current quotes for specified contracts."""
        if not self.client:
            raise RuntimeError("Not connected to Kalshi")

        quotes = []
        for contract_id in contract_ids:
            try:
                response = await self.client.get(f"/markets/{contract_id}")
                response.raise_for_status()
                data = response.json()

                quote = self._parse_quote(contract_id, data)
                if quote:
                    quotes.append(quote)

            except httpx.HTTPError as e:
                # Log error but continue with other contracts
                print(f"Failed to fetch quote for {contract_id}: {e}")

        return quotes

    async def place_order(self, req: OrderRequest) -> Fill | None:
        """Place an order."""
        if not self.client:
            raise RuntimeError("Not connected to Kalshi")

        # Convert to Kalshi order format
        order_data = {
            "market_id": req.contract_id,
            "side": req.side.value.lower(),
            "price": req.price,
            "size": req.qty,
            "time_in_force": req.tif.value,
        }

        try:
            response = await self.client.post("/orders", json=order_data)
            response.raise_for_status()
            data = response.json()

            # Parse fill information
            fill = self._parse_fill(data)
            return fill

        except httpx.HTTPError as e:
            print(f"Failed to place order: {e}")
            return None

    async def cancel_order(self, venue_order_id: str) -> bool:
        """Cancel an order."""
        if not self.client:
            raise RuntimeError("Not connected to Kalshi")

        try:
            response = await self.client.delete(f"/orders/{venue_order_id}")
            response.raise_for_status()
            return True

        except httpx.HTTPError as e:
            print(f"Failed to cancel order {venue_order_id}: {e}")
            return False

    async def get_balance(self) -> dict[str, Balance]:
        """Get account balances."""
        if not self.client:
            raise RuntimeError("Not connected to Kalshi")

        try:
            response = await self.client.get("/portfolio")
            response.raise_for_status()
            data = response.json()

            balances = {}
            balance_data = data.get("portfolio", {})

            # Kalshi typically has USD balance
            usd_balance = Balance(
                venue=Venue.KALSHI,
                currency="USD",
                available=float(balance_data.get("available_balance", 0)),
                total=float(balance_data.get("total_balance", 0)),
            )
            balances["USD"] = usd_balance

            return balances

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch balances: {e}")

    async def healthcheck(self) -> bool:
        """Check if Kalshi is healthy."""
        if not self.client:
            return False

        try:
            response = await self.client.get("/health")
            response.raise_for_status()
            return True

        except httpx.HTTPError:
            return False

    def _parse_contract(self, market_data: dict, side: ContractSide) -> Contract | None:
        """Parse market data into Contract object."""
        try:
            market_id = market_data.get("id")
            if not market_id:
                return None

            # Create contract ID with side suffix
            contract_id = f"{market_id}_{side.value}"

            # Parse expiry
            end_date = market_data.get("close_time")
            expires_at = datetime.fromisoformat(end_date.replace("Z", "+00:00")) if end_date else datetime.now(timezone.utc)

            # Create fee model
            fees = FeeModel(
                maker_bps=0.0,
                taker_bps=30.0,
            )

            return Contract(
                venue=Venue.KALSHI,
                contract_id=contract_id,
                event_key=market_data.get("title", ""),
                normalized_event_id=market_id,
                side=side,
                tick_size=0.01,
                settlement_ccy="USD",
                expires_at=expires_at,
                fees=fees,
                min_size=1.0,
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse contract: {e}")
            return None

    def _parse_quote(self, contract_id: str, market_data: dict) -> Quote | None:
        """Parse market data into Quote object."""
        try:
            # Extract bid/ask from market data
            yes_bid = market_data.get("yes_bid", 0)
            yes_ask = market_data.get("yes_ask", 1)
            no_bid = market_data.get("no_bid", 0)
            no_ask = market_data.get("no_ask", 1)

            # Determine which side this contract represents
            if contract_id.endswith("_YES"):
                best_bid = float(yes_bid)
                best_ask = float(yes_ask)
            else:
                best_bid = float(no_bid)
                best_ask = float(no_ask)

            return Quote(
                venue=Venue.KALSHI,
                contract_id=contract_id,
                best_bid=best_bid,
                best_ask=best_ask,
                best_bid_size=100.0,  # Default size
                best_ask_size=100.0,  # Default size
                ts=datetime.now(timezone.utc),
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse quote: {e}")
            return None

    def _parse_fill(self, order_data: dict) -> Fill | None:
        """Parse order data into Fill object."""
        try:
            return Fill(
                venue=Venue.KALSHI,
                contract_id=order_data.get("market_id", ""),
                side=OrderSide(order_data.get("side", "").upper()),
                avg_price=float(order_data.get("price", 0)),
                qty=float(order_data.get("size", 0)),
                fee_paid=float(order_data.get("fee", 0)),
                ts=datetime.now(timezone.utc),
                venue_order_id=order_data.get("id"),
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse fill: {e}")
            return None
    
    def _parse_public_quote(self, market_data: dict) -> Quote | None:
        """Parse public market data into Quote object.
        
        Args:
            market_data: Market data from public API
            
        Returns:
            Quote object or None if parsing fails
        """
        try:
            ticker = market_data.get("ticker")
            if not ticker:
                return None
            
            # Get orderbook data
            yes_bid = market_data.get("yes_bid", 0)
            yes_ask = market_data.get("yes_ask", 100)
            
            # Kalshi prices are in cents (0-100), normalize to [0,1]
            best_bid = float(yes_bid) / 100.0
            best_ask = float(yes_ask) / 100.0
            
            # Get sizes if available
            best_bid_size = float(market_data.get("yes_bid_size", 0))
            best_ask_size = float(market_data.get("yes_ask_size", 0))
            
            # If sizes are 0, use default
            if best_bid_size == 0:
                best_bid_size = 100.0
            if best_ask_size == 0:
                best_ask_size = 100.0
            
            # Get event info for matching
            event_key = market_data.get("title", ticker)
            
            # Parse expiry time
            close_time = market_data.get("close_time")
            if close_time:
                try:
                    # Handle ISO format with Z
                    expires_at = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    expires_at = datetime.now(timezone.utc)
            else:
                expires_at = datetime.now(timezone.utc)
            
            return Quote(
                venue=Venue.KALSHI,
                contract_id=ticker,
                best_bid=best_bid,
                best_ask=best_ask,
                best_bid_size=best_bid_size,
                best_ask_size=best_ask_size,
                ts=datetime.now(timezone.utc),
            )
            
        except (KeyError, ValueError, TypeError) as e:
            print(f"Failed to parse public quote: {e}, data: {market_data}")
            return None


