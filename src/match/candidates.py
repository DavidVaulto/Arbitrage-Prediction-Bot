"""Candidate generation for market matching."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import httpx


@dataclass
class KalshiMarketLite:
    """Lightweight Kalshi market representation."""
    ticker: str
    title: str
    market_id: str
    close_time: Optional[datetime]
    meta: Dict[str, any]


async def kalshi_candidates_from_pm(
    pm_features: Dict[str, any],
    http_client: httpx.AsyncClient,
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2",
    limit: int = 50
) -> List[KalshiMarketLite]:
    """
    Generate Kalshi candidate markets based on Polymarket features.
    
    Args:
        pm_features: Extracted features from Polymarket market
        http_client: Shared async HTTP client
        base_url: Kalshi API base URL
        limit: Maximum candidates to return
        
    Returns:
        List of candidate Kalshi markets
    """
    try:
        # Build query based on features
        params = {"limit": limit, "status": "open"}
        
        # Add series filter if we can infer it from market type
        # This is a simplified approach - in production you'd use more sophisticated querying
        
        response = await http_client.get(f"{base_url}/markets", params=params)
        response.raise_for_status()
        data = response.json()
        
        candidates = []
        markets = data.get("markets", [])
        
        for market in markets:
            try:
                ticker = market.get("ticker")
                if not ticker:
                    continue
                
                close_time_str = market.get("close_time")
                close_time = None
                if close_time_str:
                    try:
                        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                candidate = KalshiMarketLite(
                    ticker=ticker,
                    title=market.get("title", ticker),
                    market_id=ticker,  # Use ticker as ID for simplicity
                    close_time=close_time,
                    meta={
                        'subtitle': market.get("subtitle", ""),
                        'category': market.get("category", ""),
                        'yes_bid': market.get("yes_bid", 0),
                        'yes_ask': market.get("yes_ask", 100),
                    }
                )
                candidates.append(candidate)
                
            except (KeyError, ValueError, TypeError):
                continue
        
        return candidates[:limit]
        
    except httpx.HTTPError as e:
        print(f"Kalshi API error in candidate generation: {e}")
        return []
    except Exception as e:
        print(f"Candidate generation error: {e}")
        return []


def kalshi_candidates_from_cache(
    pm_features: Dict[str, any],
    kalshi_markets: List[Dict[str, any]],
    limit: int = 50
) -> List[KalshiMarketLite]:
    """
    Generate candidates from a cached list of Kalshi markets.
    Useful when you already have market data loaded.
    
    Args:
        pm_features: Extracted features from Polymarket market
        kalshi_markets: List of Kalshi market dicts
        limit: Maximum candidates to return
        
    Returns:
        List of candidate Kalshi markets
    """
    candidates = []
    
    for market in kalshi_markets[:limit]:
        try:
            ticker = market.get("ticker") or market.get("contract_id")
            if not ticker:
                continue
            
            close_time = market.get("expires_at")
            if isinstance(close_time, str):
                try:
                    close_time = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    close_time = None
            
            candidate = KalshiMarketLite(
                ticker=ticker,
                title=market.get("title", ticker),
                market_id=ticker,
                close_time=close_time,
                meta=market
            )
            candidates.append(candidate)
            
        except (KeyError, ValueError, TypeError):
            continue
    
    return candidates

