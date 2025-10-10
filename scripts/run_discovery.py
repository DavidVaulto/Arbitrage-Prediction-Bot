#!/usr/bin/env python3
"""Discovery script for PM Arbitrage Bot - Fully async version."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


class Quote:
    """Simple quote data structure."""
    def __init__(self, **kwargs):
        self.ts = kwargs.get('ts', datetime.now(timezone.utc))
        self.venue = kwargs['venue']
        self.contract_id = kwargs['contract_id']
        self.title = kwargs.get('title', '')
        self.best_bid_yes = kwargs.get('best_bid_yes', 0.0)
        self.best_ask_yes = kwargs.get('best_ask_yes', 0.0)
        self.best_bid_no = kwargs.get('best_bid_no', 0.0)
        self.best_ask_no = kwargs.get('best_ask_no', 0.0)
        self.best_bid_size = kwargs.get('best_bid_size', 0.0)
        self.best_ask_size = kwargs.get('best_ask_size', 0.0)
        self.expires_at = kwargs.get('expires_at')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for recording."""
        return {
            'timestamp': self.ts,
            'venue': self.venue,
            'contract_id': self.contract_id,
            'title': self.title,
            'best_bid_yes': self.best_bid_yes,
            'best_ask_yes': self.best_ask_yes,
            'best_bid_no': self.best_bid_no,
            'best_ask_no': self.best_ask_no,
            'best_bid_size': self.best_bid_size,
            'best_ask_size': self.best_ask_size,
            'expires_at': self.expires_at,
            'mid_price': (self.best_bid_yes + self.best_ask_yes) / 2 if self.best_ask_yes > 0 else 0.0,
            'spread_bps': ((self.best_ask_yes - self.best_bid_yes) / ((self.best_bid_yes + self.best_ask_yes) / 2) * 10000) 
                          if (self.best_bid_yes + self.best_ask_yes) > 0 else 0.0
        }


class KalshiClient:
    """Kalshi public API client."""
    
    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://api.elections.kalshi.com/trade-api/v2"):
        self.http = http
        self.base_url = base_url
    
    async def fetch_quotes(self, limit: int = 50) -> List[Quote]:
        """Fetch quotes from Kalshi public API."""
        try:
            response = await self.http.get(
                f"{self.base_url}/markets",
                params={"limit": limit, "status": "open"}
            )
            response.raise_for_status()
            data = response.json()
            
            quotes = []
            markets = data.get("markets", [])
            
            for market in markets:
                try:
                    ticker = market.get("ticker")
                    if not ticker:
                        continue
                    
                    # Kalshi prices are in cents (0-100), normalize to [0,1]
                    yes_bid = float(market.get("yes_bid", 0)) / 100.0
                    yes_ask = float(market.get("yes_ask", 100)) / 100.0
                    
                    # NO prices are implied: NO = 1 - YES
                    no_bid = 1.0 - yes_ask
                    no_ask = 1.0 - yes_bid
                    
                    # Parse expiry
                    close_time = market.get("close_time")
                    if close_time:
                        try:
                            expires_at = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            expires_at = None
                    else:
                        expires_at = None
                    
                    quote = Quote(
                        venue="kalshi",
                        contract_id=ticker,
                        title=market.get("title", ticker),
                        best_bid_yes=yes_bid,
                        best_ask_yes=yes_ask,
                        best_bid_no=no_bid,
                        best_ask_no=no_ask,
                        best_bid_size=float(market.get("yes_bid_size", 0)),
                        best_ask_size=float(market.get("yes_ask_size", 0)),
                        expires_at=expires_at
                    )
                    quotes.append(quote)
                    
                except (KeyError, ValueError, TypeError) as e:
                    # Skip malformed quotes
                    continue
            
            return quotes
            
        except httpx.HTTPError as e:
            print(f"Kalshi API error: {e}")
            return []
        except Exception as e:
            print(f"Kalshi fetch error: {e}")
            return []


class PolymarketClient:
    """Polymarket public API client."""
    
    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://gamma-api.polymarket.com"):
        self.http = http
        self.base_url = base_url
    
    async def fetch_quotes(self, limit: int = 50) -> List[Quote]:
        """Fetch quotes from Polymarket public API."""
        try:
            # Fetch active markets from Polymarket's public API
            response = await self.http.get(
                f"{self.base_url}/markets",
                params={"limit": limit, "active": "true", "closed": "false"}
            )
            response.raise_for_status()
            markets = response.json()
            
            quotes = []
            
            for market in markets:
                try:
                    market_id = market.get("id", "")
                    question = market.get("question", "")
                    
                    if not market_id or not question:
                        continue
                    
                    # Get orderbook data from market
                    best_bid = float(market.get("bestBid", 0))
                    best_ask = float(market.get("bestAsk", 1))
                    
                    # Polymarket prices should be in [0,1] already
                    # But sometimes they're in cents, so normalize
                    if best_bid > 1:
                        best_bid = best_bid / 100.0
                    if best_ask > 1:
                        best_ask = best_ask / 100.0
                    
                    # Get volume/liquidity as proxy for size
                    volume = float(market.get("volume24hr", 0))
                    liquidity = float(market.get("liquidityNum", 0))
                    
                    # Use liquidity as size proxy (divide by 2 for bid/ask)
                    size = max(liquidity / 2, 100.0)
                    
                    # Parse expiry
                    end_date = market.get("endDate") or market.get("endDateIso")
                    if end_date:
                        try:
                            expires_at = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            expires_at = None
                    else:
                        expires_at = None
                    
                    # Create quote for YES side (Polymarket markets are binary)
                    # NO prices are implied: NO = 1 - YES
                    quote = Quote(
                        venue="polymarket",
                        contract_id=f"pm_{market_id}",
                        title=question,
                        best_bid_yes=best_bid,
                        best_ask_yes=best_ask,
                        best_bid_no=1.0 - best_ask,
                        best_ask_no=1.0 - best_bid,
                        best_bid_size=size,
                        best_ask_size=size,
                        expires_at=expires_at
                    )
                    quotes.append(quote)
                
                except (KeyError, ValueError, TypeError) as e:
                    # Skip malformed quotes
                    continue
            
            return quotes
            
        except httpx.HTTPError as e:
            print(f"Polymarket API error: {e}")
            return []
        except Exception as e:
            print(f"Polymarket fetch error: {e}")
            return []


class Recorder:
    """Records quotes to Parquet or CSV."""
    
    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path
        self.initialized = False
        
        if file_path:
            # Create parent directory
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize empty file with headers
            self._initialize_file()
    
    def _initialize_file(self):
        """Initialize the data file with headers."""
        if not self.file_path:
            return
        
        try:
            import pandas as pd
            
            # Create empty DataFrame with schema
            schema = {
                'timestamp': pd.Series(dtype='datetime64[ns, UTC]'),
                'venue': pd.Series(dtype='string'),
                'contract_id': pd.Series(dtype='string'),
                'title': pd.Series(dtype='string'),
                'best_bid_yes': pd.Series(dtype='float64'),
                'best_ask_yes': pd.Series(dtype='float64'),
                'best_bid_no': pd.Series(dtype='float64'),
                'best_ask_no': pd.Series(dtype='float64'),
                'best_bid_size': pd.Series(dtype='float64'),
                'best_ask_size': pd.Series(dtype='float64'),
                'expires_at': pd.Series(dtype='datetime64[ns, UTC]'),
                'mid_price': pd.Series(dtype='float64'),
                'spread_bps': pd.Series(dtype='float64'),
            }
            
            df = pd.DataFrame(schema)
            
            if self.file_path.suffix == '.parquet':
                df.to_parquet(self.file_path, index=False)
            else:
                df.to_csv(self.file_path, index=False)
            
            self.initialized = True
            print(f"Initialized data file: {self.file_path}")
            
        except ImportError:
            print("Warning: pandas not available, skipping file initialization")
    
    def append(self, quotes: List[Quote]):
        """Append quotes to the data file."""
        if not self.file_path or not quotes:
            return
        
        try:
            import pandas as pd
            
            # Convert quotes to records
            records = [q.to_dict() for q in quotes]
            df = pd.DataFrame(records)
            
            if self.file_path.suffix == '.parquet':
                # Append to parquet
                if self.file_path.exists():
                    existing_df = pd.read_parquet(self.file_path)
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    combined_df.to_parquet(self.file_path, index=False)
                else:
                    df.to_parquet(self.file_path, index=False)
            else:
                # Append to CSV
                df.to_csv(self.file_path, mode='a', header=not self.file_path.exists(), index=False)
            
        except Exception as e:
            print(f"Failed to record data: {e}")


async def run_poll_loop(
    kalshi: KalshiClient,
    poly: PolymarketClient,
    recorder: Recorder,
    poll_ms: int
):
    """Run the polling loop."""
    poll_seconds = poll_ms / 1000.0
    
    print(f"Starting poll loop with {poll_ms}ms interval...")
    
    while True:
        try:
            # Fetch from both venues concurrently
            results = await asyncio.gather(
                kalshi.fetch_quotes(),
                poly.fetch_quotes(),
                return_exceptions=True
            )
            
            # Handle results
            kalshi_quotes = []
            poly_quotes = []
            
            if isinstance(results[0], Exception):
                print(f"Kalshi error: {results[0]}")
            else:
                kalshi_quotes = results[0]
            
            if isinstance(results[1], Exception):
                print(f"Polymarket error: {results[1]}")
            else:
                poly_quotes = results[1]
            
            # Combine quotes
            all_quotes = kalshi_quotes + poly_quotes
            
            # Log heartbeat
            heartbeat = {
                "msg": "discovery_heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "poll_ms": poll_ms,
                "fetched_kalshi": len(kalshi_quotes),
                "fetched_polymarket": len(poly_quotes),
                "total_quotes": len(all_quotes)
            }
            print(json.dumps(heartbeat))
            
            # Record data
            if all_quotes:
                recorder.append(all_quotes)
                print(json.dumps({
                    "msg": "data_recorded",
                    "saved_rows": len(all_quotes)
                }))
            
            # Wait for next poll
            await asyncio.sleep(poll_seconds)
            
        except asyncio.CancelledError:
            print(json.dumps({
                "msg": "discovery_stopped",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "cancelled"
            }))
            raise
        except Exception as e:
            print(json.dumps({
                "msg": "poll_error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            # Continue polling even on error
            await asyncio.sleep(poll_seconds)


async def async_main(poll_ms: int, record_path: Optional[str] = None):
    """Async main function."""
    # Create recorder
    recorder = Recorder(Path(record_path) if record_path else None)
    
    # Create shared HTTP client
    async with httpx.AsyncClient(http2=True, timeout=15.0) as http:
        # Create venue clients
        kalshi = KalshiClient(http=http)
        poly = PolymarketClient(http=http)
        
        print("Using real discovery with public APIs")
        print(f"Recording to: {record_path or 'none'}")
        
        # Run poll loop
        try:
            await run_poll_loop(kalshi, poly, recorder, poll_ms)
        except asyncio.CancelledError:
            print("Gracefully shutting down...")
        except KeyboardInterrupt:
            print("Interrupted by user")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PM Arbitrage Bot Discovery - Async")
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=1500,
        help="Polling interval in milliseconds (default: 1500)"
    )
    parser.add_argument(
        "--record",
        type=str,
        help="Path to record market data (Parquet or CSV)"
    )
    
    args = parser.parse_args()
    
    # Run async main (only once!)
    try:
        asyncio.run(async_main(args.poll_ms, args.record))
    except KeyboardInterrupt:
        print("\nShutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    main()
