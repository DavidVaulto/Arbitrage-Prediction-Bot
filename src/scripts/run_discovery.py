"""Discovery script - finds arbitrage opportunities without trading."""

import asyncio
import sys
from datetime import datetime

from ..connectors.base import MockConnector
from ..connectors.kalshi import KalshiConnector
from ..connectors.polymarket import PolymarketConnector
from ..core.config import settings
from ..core.discovery import DiscoveryEngine
from ..core.fees import create_default_fee_calculator
from ..core.matcher import EventMatcher
from ..core.types import Venue


async def main():
    """Main discovery function."""
    print("Starting arbitrage opportunity discovery...")
    print(f"Mode: {settings.mode}")
    print(f"Min edge: {settings.min_edge_bps}bps")
    print(f"Min notional: ${settings.min_notional_usd}")

    # Initialize connectors
    connectors = await _initialize_connectors()

    # Initialize discovery engine
    fee_calculator = create_default_fee_calculator()
    event_matcher = EventMatcher()
    discovery_engine = DiscoveryEngine(
        fee_calculator=fee_calculator,
        event_matcher=event_matcher,
        min_edge_bps=settings.min_edge_bps,
        min_notional_usd=settings.min_notional_usd,
        max_slippage_bps=settings.max_slippage_bps,
    )

    try:
        # Run discovery loop
        while True:
            print(f"\n--- Discovery Run at {datetime.utcnow()} ---")

            # Discover opportunities
            opportunities = await discovery_engine.discover_opportunities(
                connectors,
                refresh_contracts=True,  # Refresh contracts each time
            )

            if opportunities:
                print(f"Found {len(opportunities)} opportunities:")
                for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
                    print(f"  {i}. {opp.event_id}")
                    print(f"     Edge: {opp.edge_bps:.1f}bps")
                    print(f"     Notional: ${opp.notional:.2f}")
                    print(f"     Rationale: {opp.rationale}")
                    print(f"     Expiry: {opp.expiry}")
                    print()
            else:
                print("No opportunities found.")

            # Print discovery stats
            stats = discovery_engine.get_discovery_stats()
            print("Discovery Stats:")
            print(f"  Total contracts: {stats['total_contracts']}")
            print(f"  Total quotes: {stats['total_quotes']}")
            print(f"  Venues connected: {stats['venues_connected']}")

            # Wait before next discovery
            await asyncio.sleep(settings.discovery_interval)

    except KeyboardInterrupt:
        print("\nDiscovery stopped by user.")
    except Exception as e:
        print(f"Error in discovery: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        await _cleanup_connectors(connectors)


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


async def _cleanup_connectors(connectors: dict[Venue, any]) -> None:
    """Cleanup connectors."""
    for venue, connector in connectors.items():
        try:
            await connector.disconnect()
            print(f"Disconnected from {venue.value}")
        except Exception as e:
            print(f"Error disconnecting from {venue.value}: {e}")


if __name__ == "__main__":
    asyncio.run(main())




