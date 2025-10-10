"""Polymarket connector implementation."""

from __future__ import annotations

from datetime import datetime

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


class PolymarketConnector(BaseConnector):
    """Connector for Polymarket exchange."""

    def __init__(self, credentials: dict[str, str]):
        """Initialize Polymarket connector.
        
        Args:
            credentials: Dictionary with 'api_key' and 'private_key'
        """
        super().__init__(Venue.POLYMARKET, credentials)
        self.api_key = credentials.get("api_key")
        self.private_key = credentials.get("private_key")
        self.base_url = "https://gamma-api.polymarket.com"
        self.client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Establish connection to Polymarket."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._is_connected = True

    async def disconnect(self) -> None:
        """Close connection to Polymarket."""
        if self.client:
            await self.client.aclose()
            self.client = None
        self._is_connected = False

    async def list_contracts(self) -> list[Contract]:
        """List all available contracts."""
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            response = await self.client.get("/markets")
            response.raise_for_status()
            data = response.json()

            contracts = []
            for market in data.get("data", []):
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
            raise RuntimeError("Not connected to Polymarket")

        quotes = []
        for contract_id in contract_ids:
            try:
                response = await self.client.get(f"/markets/{contract_id}/book")
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
            raise RuntimeError("Not connected to Polymarket")

        # Convert to Polymarket order format
        order_data = {
            "market": req.contract_id,
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
            raise RuntimeError("Not connected to Polymarket")

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
            raise RuntimeError("Not connected to Polymarket")

        try:
            response = await self.client.get("/balances")
            response.raise_for_status()
            data = response.json()

            balances = {}
            for balance_data in data.get("data", []):
                balance = self._parse_balance(balance_data)
                if balance:
                    balances[balance.currency] = balance

            return balances

        except httpx.HTTPError as e:
            raise RuntimeError(f"Failed to fetch balances: {e}")

    async def healthcheck(self) -> bool:
        """Check if Polymarket is healthy."""
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
            end_date = market_data.get("end_date")
            expires_at = datetime.fromisoformat(end_date.replace("Z", "+00:00")) if end_date else datetime.utcnow()

            # Create fee model
            fees = FeeModel(
                maker_bps=0.0,
                taker_bps=25.0,
                gas_estimate_usd=0.50,
            )

            return Contract(
                venue=Venue.POLYMARKET,
                contract_id=contract_id,
                event_key=market_data.get("question", ""),
                normalized_event_id=market_id,
                side=side,
                tick_size=0.01,
                settlement_ccy="USDC",
                expires_at=expires_at,
                fees=fees,
                min_size=1.0,
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse contract: {e}")
            return None

    def _parse_quote(self, contract_id: str, book_data: dict) -> Quote | None:
        """Parse order book data into Quote object."""
        try:
            bids = book_data.get("bids", [])
            asks = book_data.get("asks", [])

            best_bid = float(bids[0][0]) if bids else 0.0
            best_bid_size = float(bids[0][1]) if bids else 0.0
            best_ask = float(asks[0][0]) if asks else 1.0
            best_ask_size = float(asks[0][1]) if asks else 0.0

            return Quote(
                venue=Venue.POLYMARKET,
                contract_id=contract_id,
                best_bid=best_bid,
                best_ask=best_ask,
                best_bid_size=best_bid_size,
                best_ask_size=best_ask_size,
                ts=datetime.utcnow(),
            )

        except (KeyError, ValueError, IndexError) as e:
            print(f"Failed to parse quote: {e}")
            return None

    def _parse_fill(self, order_data: dict) -> Fill | None:
        """Parse order data into Fill object."""
        try:
            return Fill(
                venue=Venue.POLYMARKET,
                contract_id=order_data.get("market", ""),
                side=OrderSide(order_data.get("side", "").upper()),
                avg_price=float(order_data.get("price", 0)),
                qty=float(order_data.get("size", 0)),
                fee_paid=float(order_data.get("fee", 0)),
                ts=datetime.utcnow(),
                venue_order_id=order_data.get("id"),
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse fill: {e}")
            return None

    def _parse_balance(self, balance_data: dict) -> Balance | None:
        """Parse balance data into Balance object."""
        try:
            return Balance(
                venue=Venue.POLYMARKET,
                currency=balance_data.get("token", "USDC"),
                available=float(balance_data.get("available", 0)),
                total=float(balance_data.get("total", 0)),
            )

        except (KeyError, ValueError) as e:
            print(f"Failed to parse balance: {e}")
            return None

