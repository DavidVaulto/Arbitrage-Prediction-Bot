"""Exact search and matching for PM→Kalshi pairs."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from .canonical_exact import MarketLite, build_canonical_key, keys_match_exactly


@dataclass
class ExactPair:
    """Exact market pair."""
    canonical_key: str
    pm_market_id: str
    kalshi_market_id: str
    pm_title: str
    kalshi_title: str
    expires_pm: Optional[datetime]
    expires_kalshi: Optional[datetime]
    source: str = "auto"  # auto or override


@dataclass
class KalshiMarketLite:
    """Lightweight Kalshi market."""
    market_id: str
    ticker: str
    title: str
    subtitle: str = ""
    close_time: Optional[datetime] = None
    liquidity: float = 0.0
    meta: Dict = None


async def kalshi_search_candidates(
    pm_market: MarketLite,
    http_client: httpx.AsyncClient,
    base_url: str = "https://api.elections.kalshi.com/trade-api/v2",
    limit: int = 100
) -> List[KalshiMarketLite]:
    """
    Search Kalshi for candidate markets based on PM market features.
    
    Args:
        pm_market: Polymarket market
        http_client: Shared async HTTP client
        base_url: Kalshi API base URL
        limit: Max candidates
        
    Returns:
        List of Kalshi candidate markets
    """
    try:
        # Fetch open markets from Kalshi
        response = await http_client.get(
            f"{base_url}/markets",
            params={"limit": limit, "status": "open"}
        )
        response.raise_for_status()
        data = response.json()
        
        candidates = []
        markets = data.get("markets", [])
        
        for market in markets:
            try:
                ticker = market.get("ticker")
                if not ticker:
                    continue
                
                # Parse close time
                close_time_str = market.get("close_time")
                close_time = None
                if close_time_str:
                    try:
                        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                candidate = KalshiMarketLite(
                    market_id=ticker,
                    ticker=ticker,
                    title=market.get("title", ticker),
                    subtitle=market.get("subtitle", ""),
                    close_time=close_time,
                    liquidity=float(market.get("volume", 0)),
                    meta=market
                )
                candidates.append(candidate)
                
            except (KeyError, ValueError, TypeError):
                continue
        
        return candidates
        
    except httpx.HTTPError as e:
        print(f"Kalshi API error: {e}")
        return []
    except Exception as e:
        print(f"Candidate search error: {e}")
        return []


def kalshi_search_candidates_sync(
    pm_market: MarketLite,
    kalshi_markets_cache: List[Dict]
) -> List[KalshiMarketLite]:
    """
    Search from cached Kalshi markets (sync version).
    
    Args:
        pm_market: Polymarket market
        kalshi_markets_cache: List of Kalshi market dicts
        
    Returns:
        List of Kalshi candidate markets
    """
    candidates = []
    
    for market in kalshi_markets_cache:
        try:
            ticker = market.get("ticker") or market.get("contract_id")
            if not ticker:
                continue
            
            # Parse close time
            close_time = market.get("expires_at") or market.get("close_time")
            if isinstance(close_time, str):
                try:
                    close_time = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    close_time = None
            
            candidate = KalshiMarketLite(
                market_id=ticker,
                ticker=ticker,
                title=market.get("title", ticker),
                subtitle="",
                close_time=close_time,
                liquidity=0.0,
                meta=market
            )
            candidates.append(candidate)
            
        except (KeyError, ValueError, TypeError):
            continue
    
    return candidates


def find_exact_pair_for_pm(
    pm_market: MarketLite,
    pm_market_id: str,
    kalshi_candidates: List[KalshiMarketLite],
    overrides: Dict[str, Dict] = None
) -> Optional[ExactPair]:
    """
    Find exact Kalshi match for PM market.
    
    Args:
        pm_market: Polymarket market
        pm_market_id: PM market ID
        kalshi_candidates: List of Kalshi candidates to check
        overrides: Dict of manual overrides {pm_market_id: {...}}
        
    Returns:
        ExactPair if found, None otherwise
    """
    # Check overrides first
    if overrides and pm_market_id in overrides:
        override = overrides[pm_market_id]
        return ExactPair(
            canonical_key=override.get("canonical_key", "OVERRIDE"),
            pm_market_id=pm_market_id,
            kalshi_market_id=override["kalshi_market_id"],
            pm_title=pm_market.title,
            kalshi_title=override.get("kalshi_title", ""),
            expires_pm=pm_market.expires_at,
            expires_kalshi=None,
            source="override"
        )
    
    # Build canonical key for PM market
    pm_key = build_canonical_key(pm_market)
    
    if pm_key is None:
        # Cannot canonicalize - needs review
        return None
    
    # Find matching Kalshi markets
    matches = []
    
    for kalshi_market in kalshi_candidates:
        # Build Kalshi market representation
        kalshi_lite = MarketLite(
            title=kalshi_market.title,
            description=kalshi_market.subtitle,
            expires_at=kalshi_market.close_time,
            meta=kalshi_market.meta
        )
        
        kalshi_key = build_canonical_key(kalshi_lite)
        
        if keys_match_exactly(pm_key, kalshi_key):
            matches.append(kalshi_market)
    
    if len(matches) == 0:
        # No match
        return None
    
    if len(matches) == 1:
        # Exact single match
        kalshi = matches[0]
        return ExactPair(
            canonical_key=pm_key,
            pm_market_id=pm_market_id,
            kalshi_market_id=kalshi.market_id,
            pm_title=pm_market.title,
            kalshi_title=kalshi.title,
            expires_pm=pm_market.expires_at,
            expires_kalshi=kalshi.close_time,
            source="auto"
        )
    
    # Multiple matches - use tie-breaker
    # Prefer: same expiry date, then highest liquidity
    best_match = None
    best_score = -1
    
    for kalshi in matches:
        score = 0
        
        # Same expiry date
        if pm_market.expires_at and kalshi.close_time:
            if pm_market.expires_at.date() == kalshi.close_time.date():
                score += 1000
        
        # Liquidity proxy
        score += kalshi.liquidity
        
        if score > best_score:
            best_score = score
            best_match = kalshi
    
    if best_match:
        return ExactPair(
            canonical_key=pm_key,
            pm_market_id=pm_market_id,
            kalshi_market_id=best_match.market_id,
            pm_title=pm_market.title,
            kalshi_title=best_match.title,
            expires_pm=pm_market.expires_at,
            expires_kalshi=best_match.close_time,
            source="auto"
        )
    
    return None

