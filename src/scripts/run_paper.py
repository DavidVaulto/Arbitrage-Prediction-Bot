"""Paper trading script - simulates trades without real money."""

import asyncio
import sys
from typing import Any

from ..connectors.base import MockConnector
from ..connectors.kalshi import KalshiConnector
from ..connectors.polymarket import PolymarketConnector
from ..core.config import settings
from ..core.paper import PaperTradingEngine
from ..core.types import Venue


async def main():
    """Main paper trading function."""
    print("Starting paper trading engine...")
    print(f"Mode: {settings.mode}")
    print(f"Initial balance: ${settings.starting_balance_usd:,.2f}")
    print(f"Min edge: {settings.min_edge_bps}bps")
    print(f"Min notional: ${settings.min_notional_usd}")
    print(f"Kelly fraction: {settings.kelly_fraction}")

    # Initialize connectors
    connectors = await _initialize_connectors()

    # Initialize paper trading engine
    paper_engine = PaperTradingEngine()

    try:
        # Start paper trading
        await paper_engine.start(connectors)

    except KeyboardInterrupt:
        print("\nPaper trading stopped by user.")
    except Exception as e:
        print(f"Error in paper trading: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        await _cleanup_connectors(connectors)
        await paper_engine.stop()


async def _initialize_connectors() -> dict[Venue, any]:
    """Initialize connectors for all venues."""
    connectors = {}

    # Initialize Polymarket connector
    try:
        if settings.polymarket_api_key:
            polymarket_creds = settings.get_venue_credentials(Venue.POLYMARKET)
            polymarket_connector = PolymarketConnector(polymarket_creds)
            await polymarket_connector.connect()
            connectors[Venue.POLYMARKET] = polymarket_connector
            print(f"Connected to {Venue.POLYMARKET.value}")
        else:
            # Use mock connector
            mock_connector = MockConnector(Venue.POLYMARKET, {})
            await mock_connector.connect()
            connectors[Venue.POLYMARKET] = mock_connector
            print(f"Using mock connector for {Venue.POLYMARKET.value}")
    except Exception as e:
        print(f"Failed to connect to {Venue.POLYMARKET.value}: {e}")
        # Use mock connector as fallback
        mock_connector = MockConnector(Venue.POLYMARKET, {})
        await mock_connector.connect()
        connectors[Venue.POLYMARKET] = mock_connector

    # Initialize Kalshi connector
    try:
        if settings.kalshi_api_key:
            kalshi_creds = settings.get_venue_credentials(Venue.KALSHI)
            kalshi_connector = KalshiConnector(kalshi_creds)
            await kalshi_connector.connect()
            connectors[Venue.KALSHI] = kalshi_connector
            print(f"Connected to {Venue.KALSHI.value}")
        else:
            # Use mock connector
            mock_connector = MockConnector(Venue.KALSHI, {})
            await mock_connector.connect()
            connectors[Venue.KALSHI] = mock_connector
            print(f"Using mock connector for {Venue.KALSHI.value}")
    except Exception as e:
        print(f"Failed to connect to {Venue.KALSHI.value}: {e}")
        # Use mock connector as fallback
        mock_connector = MockConnector(Venue.KALSHI, {})
        await mock_connector.connect()
        connectors[Venue.KALSHI] = mock_connector

    return connectors


async def _cleanup_connectors(connectors: dict[Venue, Any]) -> None:
    """Cleanup connectors."""
    for venue, connector in connectors.items():
        try:
            await connector.disconnect()
            print(f"Disconnected from {venue.value}")
        except Exception as e:
            print(f"Error disconnecting from {venue.value}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
