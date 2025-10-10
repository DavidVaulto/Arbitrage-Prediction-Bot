"""Live trading script - executes real trades with real money."""

import asyncio
import sys

from ..connectors.kalshi import KalshiConnector
from ..connectors.polymarket import PolymarketConnector
from ..core.config import settings
from ..core.live import LiveTradingEngine
from ..core.types import Venue


async def main():
    """Main live trading function."""
    print("Starting live trading engine...")
    print("WARNING: This will execute real trades with real money!")

    # Confirm live trading
    if not settings.is_live_trading_enabled():
        print("ERROR: Live trading is not enabled.")
        print("Set CONFIRM_LIVE=true in your environment variables.")
        sys.exit(1)

    print(f"Mode: {settings.mode}")
    print(f"Initial balance: ${settings.starting_balance_usd:,.2f}")
    print(f"Min edge: {settings.min_edge_bps}bps")
    print(f"Min notional: ${settings.min_notional_usd}")
    print(f"Kelly fraction: {settings.kelly_fraction}")

    # Final confirmation
    print("\n" + "="*50)
    print("FINAL CONFIRMATION REQUIRED")
    print("="*50)
    print("This will execute REAL TRADES with REAL MONEY!")
    print("Make sure you have:")
    print("1. Sufficient balances on both venues")
    print("2. Proper API credentials configured")
    print("3. Risk limits set appropriately")
    print("4. Tested thoroughly in paper mode")
    print("="*50)

    confirm = input("Type 'CONFIRM' to proceed: ")
    if confirm != "CONFIRM":
        print("Live trading cancelled.")
        sys.exit(0)

    # Initialize connectors
    connectors = await _initialize_connectors()

    # Initialize live trading engine
    live_engine = LiveTradingEngine()

    try:
        # Start live trading
        await live_engine.start(connectors)

    except KeyboardInterrupt:
        print("\nLive trading stopped by user.")
    except Exception as e:
        print(f"Error in live trading: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        await _cleanup_connectors(connectors)
        await live_engine.stop()


async def _initialize_connectors() -> dict[Venue, any]:
    """Initialize connectors for all venues."""
    connectors = {}

    # Initialize Polymarket connector
    try:
        polymarket_creds = settings.get_venue_credentials(Venue.POLYMARKET)
        if not polymarket_creds.get("api_key"):
            raise ValueError("Polymarket API key not configured")

        polymarket_connector = PolymarketConnector(polymarket_creds)
        await polymarket_connector.connect()
        connectors[Venue.POLYMARKET] = polymarket_connector
        print(f"Connected to {Venue.POLYMARKET.value}")
    except Exception as e:
        print(f"Failed to connect to {Venue.POLYMARKET.value}: {e}")
        sys.exit(1)

    # Initialize Kalshi connector
    try:
        kalshi_creds = settings.get_venue_credentials(Venue.KALSHI)
        if not kalshi_creds.get("api_key"):
            raise ValueError("Kalshi API key not configured")

        kalshi_connector = KalshiConnector(kalshi_creds)
        await kalshi_connector.connect()
        connectors[Venue.KALSHI] = kalshi_connector
        print(f"Connected to {Venue.KALSHI.value}")
    except Exception as e:
        print(f"Failed to connect to {Venue.KALSHI.value}: {e}")
        sys.exit(1)

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




