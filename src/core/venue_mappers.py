"""Venue-specific market mappers for canonical event identification.

These mappers extract canonical event features from venue-specific market data
and map them to deterministic event IDs in the registry.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .event_registry import CanonicalEvent, EventRegistry, EventScope, EventType, VenueMapping


class BaseVenueMapper:
    """Base class for venue-specific mappers."""
    
    def __init__(self, registry: EventRegistry):
        """Initialize mapper.
        
        Args:
            registry: Event registry for lookups and storage
        """
        self.registry = registry
        self.venue_name = "base"
    
    def map_to_event_id(
        self,
        market_id: str,
        title: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Map venue market to canonical event ID.
        
        Args:
            market_id: Venue's market ID
            title: Market title
            description: Market description
            metadata: Additional metadata
            
        Returns:
            Canonical event ID or None if mapping fails
        """
        raise NotImplementedError
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for parsing."""
        if not text:
            return ""
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', text.strip())
        
        # Remove special characters but keep alphanumeric, spaces, and basic punctuation
        normalized = re.sub(r'[^\w\s\-:.,?!]', '', normalized)
        
        return normalized
    
    def _extract_date_from_text(self, text: str) -> datetime | None:
        """Extract date from text using common patterns."""
        if not text:
            return None
        
        # Common date patterns
        patterns = [
            r'20\d{2}',  # Year (2024, 2025, etc.)
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? 20\d{2}',  # Month DD, YYYY
            r'\d{1,2}/\d{1,2}/20\d{2}',  # MM/DD/YYYY
            r'20\d{2}-\d{2}-\d{2}',  # YYYY-MM-DD
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(0)
                try:
                    # Try to parse the date
                    for fmt in ['%Y', '%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%Y-%m-%d']:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        return None
    
    def _create_manual_override(
        self,
        market_id: str,
        event_id: str,
        title: str,
        description: str = "",
    ) -> None:
        """Create a manual override mapping."""
        mapping = VenueMapping(
            venue=self.venue_name,
            market_id=market_id,
            event_id=event_id,
            title_raw=title,
            description_raw=description,
            outcomes=["YES", "NO"],
            confidence=1.0,
            mapping_method="manual_override",
        )
        self.registry.add_mapping(mapping)


class PolymarketMapper(BaseVenueMapper):
    """Mapper for Polymarket markets."""
    
    def __init__(self, registry: EventRegistry):
        """Initialize Polymarket mapper."""
        super().__init__(registry)
        self.venue_name = "polymarket"
    
    def map_to_event_id(
        self,
        market_id: str,
        title: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Map Polymarket market to canonical event ID.
        
        Polymarket format examples:
        - "Will Trump win the 2028 Presidential Election?"
        - "Will Bitcoin reach $150,000 by end of 2025?"
        - "Will Emma Stone win Best Actress at the 2026 Oscars?"
        
        Args:
            market_id: Polymarket's market ID
            title: Market question/title
            description: Market description
            metadata: Additional metadata (close_time, etc.)
            
        Returns:
            Canonical event ID or None if cannot map
        """
        # First check if already mapped
        existing = self.registry.get_mapping(self.venue_name, market_id)
        if existing:
            return existing.event_id
        
        # Normalize title
        norm_title = self._normalize_text(title).upper()
        norm_desc = self._normalize_text(description).upper()
        combined = f"{norm_title} {norm_desc}"
        
        # Try to parse different event types
        event_id = None
        mapping_method = "abstain"
        confidence = 0.0
        
        # ELECTION patterns
        if any(word in norm_title for word in ["ELECTION", "PRESIDENT", "PRESIDENTIAL", "WIN"]):
            event_id = self._parse_election_event(combined, metadata)
            if event_id:
                mapping_method = "deterministic"
                confidence = 0.95
        
        # CRYPTO patterns
        elif any(word in norm_title for word in ["BITCOIN", "BTC", "ETH", "ETHEREUM", "CRYPTO"]):
            event_id = self._parse_crypto_event(combined, metadata)
            if event_id:
                mapping_method = "deterministic"
                confidence = 0.95
        
        # AWARDS patterns
        elif any(word in norm_title for word in ["OSCAR", "EMMY", "GRAMMY", "AWARD"]):
            event_id = self._parse_awards_event(combined, metadata)
            if event_id:
                mapping_method = "deterministic"
                confidence = 0.90
        
        # SPORTS patterns
        elif any(word in norm_title for word in ["SUPER BOWL", "WORLD CUP", "NBA", "NFL", "MLB"]):
            event_id = self._parse_sports_event(combined, metadata)
            if event_id:
                mapping_method = "deterministic"
                confidence = 0.90
        
        # If we found a mapping, store it
        if event_id and confidence >= 0.85:
            # Check if event exists in registry, if not create it
            if not self.registry.get_event(event_id):
                # Extract close date
                close_date = self._extract_close_date(metadata)
                if not close_date:
                    close_date = datetime(2099, 12, 31)  # Default far future
                
                event = CanonicalEvent(
                    event_id=event_id,
                    event_type=self._infer_event_type(event_id),
                    scope=self._infer_scope(event_id),
                    date_open=None,
                    date_close=close_date,
                    canonical_units="YES/NO",
                    display_title=title,
                    resolution_source="polymarket",
                )
                self.registry.add_event(event)
            
            # Create mapping
            mapping = VenueMapping(
                venue=self.venue_name,
                market_id=market_id,
                event_id=event_id,
                title_raw=title,
                description_raw=description,
                outcomes=["YES", "NO"],
                confidence=confidence,
                mapping_method=mapping_method,
                metadata=metadata or {},
            )
            self.registry.add_mapping(mapping)
            
            return event_id
        
        # Abstain if confidence too low or no pattern matched
        return None
    
    def _parse_election_event(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse election event from text."""
        # Pattern: ELECTION:{POSITION}:{YEAR}:{SCOPE}:{CANDIDATE}
        
        # Extract candidate name
        candidates = {
            "TRUMP": ["TRUMP", "DONALD TRUMP"],
            "BIDEN": ["BIDEN", "JOE BIDEN"],
            "HARRIS": ["HARRIS", "KAMALA HARRIS"],
            "DESANTIS": ["DESANTIS", "RON DESANTIS"],
            "NEWSOM": ["NEWSOM", "GAVIN NEWSOM"],
        }
        
        candidate = None
        for canonical_name, aliases in candidates.items():
            if any(alias in text for alias in aliases):
                candidate = canonical_name
                break
        
        if not candidate:
            return None
        
        # Extract year
        year_match = re.search(r'20(24|25|26|27|28|29|30)', text)
        if not year_match:
            return None
        year = year_match.group(0)
        
        # Determine position
        position = "PRESIDENT" if "PRESIDENT" in text else "ELECTION"
        
        # Determine scope
        scope = "US" if any(word in text for word in ["US", "USA", "UNITED STATES", "AMERICAN"]) else "GLOBAL"
        
        return CanonicalEvent.build_event_id("ELECTION", scope, position, year, candidate)
    
    def _parse_crypto_event(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse crypto price target event from text."""
        # Pattern: CRYPTO:{ASSET}:TARGET:{PRICE}:{DATE}
        
        # Extract asset
        asset = None
        if "BITCOIN" in text or "BTC" in text:
            asset = "BTC"
        elif "ETHEREUM" in text or "ETH" in text:
            asset = "ETH"
        else:
            return None
        
        # Extract price target
        price_patterns = [
            r'\$?([\d,]+)K',  # $150K format
            r'\$?([\d,]+),000',  # $150,000 format
            r'\$?([\d,]+)',  # $150000 format
        ]
        
        price = None
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                price_str = match.group(1).replace(',', '')
                if 'K' in text:
                    price = int(price_str) * 1000
                else:
                    price = int(price_str)
                break
        
        if not price:
            return None
        
        # Extract date
        date = self._extract_date_from_text(text)
        if not date:
            return None
        
        date_str = date.strftime("%Y-%m-%d")
        
        return CanonicalEvent.build_event_id("CRYPTO", "GLOBAL", f"{asset}_TARGET", str(price), date_str)
    
    def _parse_awards_event(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse awards event from text."""
        # Pattern: AWARDS:{CEREMONY}:{CATEGORY}:{YEAR}:{NOMINEE}
        
        # Extract ceremony
        ceremony = None
        if "OSCAR" in text:
            ceremony = "OSCARS"
        elif "EMMY" in text:
            ceremony = "EMMYS"
        elif "GRAMMY" in text:
            ceremony = "GRAMMYS"
        else:
            return None
        
        # Extract year
        year_match = re.search(r'20\d{2}', text)
        if not year_match:
            return None
        year = year_match.group(0)
        
        # Extract category
        category = "BEST_PICTURE"
        if "ACTRESS" in text:
            category = "BEST_ACTRESS"
        elif "ACTOR" in text:
            category = "BEST_ACTOR"
        elif "DIRECTOR" in text:
            category = "BEST_DIRECTOR"
        
        # Extract nominee (simplified - look for proper nouns)
        words = text.split()
        nominee_candidates = []
        for i, word in enumerate(words):
            if word.istitle() and len(word) > 2:
                # Check if next word is also capitalized (likely a full name)
                if i + 1 < len(words) and words[i + 1].istitle():
                    nominee_candidates.append(f"{word}_{words[i + 1]}")
        
        if not nominee_candidates:
            return None
        
        nominee = nominee_candidates[0].replace(" ", "_")
        
        return CanonicalEvent.build_event_id("AWARDS", "GLOBAL", ceremony, category, year, nominee)
    
    def _parse_sports_event(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse sports event from text."""
        # Pattern: SPORTS:{LEAGUE}:{EVENT}:{YEAR}:{TEAM/PLAYER}
        
        # For now, return None (can be extended)
        return None
    
    def _extract_close_date(self, metadata: dict[str, Any] | None) -> datetime | None:
        """Extract close date from metadata."""
        if not metadata:
            return None
        
        close_time = metadata.get('close_time') or metadata.get('end_date')
        if close_time:
            if isinstance(close_time, datetime):
                return close_time
            if isinstance(close_time, str):
                try:
                    return datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except Exception:
                    pass
        
        return None
    
    def _infer_event_type(self, event_id: str) -> EventType:
        """Infer event type from event ID."""
        if event_id.startswith("ELECTION:"):
            return EventType.ELECTION
        elif event_id.startswith("CRYPTO:"):
            return EventType.CRYPTO
        elif event_id.startswith("AWARDS:"):
            return EventType.AWARDS
        elif event_id.startswith("SPORTS:"):
            return EventType.SPORTS
        else:
            return EventType.OTHER
    
    def _infer_scope(self, event_id: str) -> EventScope:
        """Infer scope from event ID."""
        if ":US:" in event_id:
            return EventScope.US
        elif ":GLOBAL:" in event_id:
            return EventScope.GLOBAL
        else:
            return EventScope.OTHER


class KalshiMapper(BaseVenueMapper):
    """Mapper for Kalshi markets."""
    
    def __init__(self, registry: EventRegistry):
        """Initialize Kalshi mapper."""
        super().__init__(registry)
        self.venue_name = "kalshi"
    
    def map_to_event_id(
        self,
        market_id: str,
        title: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Map Kalshi market to canonical event ID.
        
        Kalshi format examples:
        - "PRES-2028-TRUMP" (ticker format)
        - "Will Donald Trump win the 2028 Presidential Election?"
        
        Args:
            market_id: Kalshi's market ticker/ID
            title: Market title
            description: Market description
            metadata: Additional metadata
            
        Returns:
            Canonical event ID or None if cannot map
        """
        # First check if already mapped
        existing = self.registry.get_mapping(self.venue_name, market_id)
        if existing:
            return existing.event_id
        
        # Try to parse ticker format first
        event_id = self._parse_ticker_format(market_id, title, metadata)
        
        # If ticker parsing fails, try title parsing
        if not event_id:
            norm_title = self._normalize_text(title).upper()
            norm_desc = self._normalize_text(description).upper()
            combined = f"{norm_title} {norm_desc}"
            
            if any(word in norm_title for word in ["ELECTION", "PRESIDENT", "PRESIDENTIAL"]):
                event_id = self._parse_election_from_title(combined, metadata)
            elif any(word in norm_title for word in ["BITCOIN", "BTC", "ETH", "CRYPTO"]):
                event_id = self._parse_crypto_from_title(combined, metadata)
        
        # If we found a mapping, store it
        if event_id:
            # Check if event exists in registry
            if not self.registry.get_event(event_id):
                close_date = self._extract_close_date(metadata)
                if not close_date:
                    close_date = datetime(2099, 12, 31)
                
                event = CanonicalEvent(
                    event_id=event_id,
                    event_type=self._infer_event_type(event_id),
                    scope=self._infer_scope(event_id),
                    date_open=None,
                    date_close=close_date,
                    canonical_units="YES/NO",
                    display_title=title,
                    resolution_source="kalshi",
                )
                self.registry.add_event(event)
            
            # Create mapping
            mapping = VenueMapping(
                venue=self.venue_name,
                market_id=market_id,
                event_id=event_id,
                title_raw=title,
                description_raw=description,
                outcomes=["YES", "NO"],
                confidence=0.95,
                mapping_method="deterministic",
                metadata=metadata or {},
            )
            self.registry.add_mapping(mapping)
            
            return event_id
        
        return None
    
    def _parse_ticker_format(
        self,
        ticker: str,
        title: str,
        metadata: dict[str, Any] | None,
    ) -> str | None:
        """Parse Kalshi ticker format.
        
        Examples:
            PRES-2028-TRUMP -> ELECTION:US:PRESIDENT:2028:TRUMP
            BTC-150K-2025 -> CRYPTO:GLOBAL:BTC_TARGET:150000:2025-12-31
        """
        parts = ticker.upper().split('-')
        
        if len(parts) < 2:
            return None
        
        # Election ticker
        if parts[0] == "PRES" or parts[0] == "PRESIDENT":
            if len(parts) >= 3:
                year = parts[1]
                candidate = parts[2]
                return CanonicalEvent.build_event_id("ELECTION", "US", "PRESIDENT", year, candidate)
        
        # Crypto ticker
        elif parts[0] in ["BTC", "ETH", "BITCOIN", "ETHEREUM"]:
            asset = "BTC" if parts[0] in ["BTC", "BITCOIN"] else "ETH"
            if len(parts) >= 3:
                # Parse price target
                price_str = parts[1].replace('K', '000')
                try:
                    price = int(price_str)
                    year = parts[2]
                    return CanonicalEvent.build_event_id(
                        "CRYPTO", "GLOBAL", f"{asset}_TARGET", str(price), f"{year}-12-31"
                    )
                except ValueError:
                    pass
        
        return None
    
    def _parse_election_from_title(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse election event from title (similar to Polymarket)."""
        # Reuse Polymarket logic
        pm_mapper = PolymarketMapper(self.registry)
        return pm_mapper._parse_election_event(text, metadata)
    
    def _parse_crypto_from_title(self, text: str, metadata: dict[str, Any] | None) -> str | None:
        """Parse crypto event from title (similar to Polymarket)."""
        pm_mapper = PolymarketMapper(self.registry)
        return pm_mapper._parse_crypto_event(text, metadata)
    
    def _extract_close_date(self, metadata: dict[str, Any] | None) -> datetime | None:
        """Extract close date from metadata."""
        if not metadata:
            return None
        
        close_time = metadata.get('close_time') or metadata.get('end_date')
        if close_time:
            if isinstance(close_time, datetime):
                return close_time
            if isinstance(close_time, str):
                try:
                    return datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                except Exception:
                    pass
        
        return None
    
    def _infer_event_type(self, event_id: str) -> EventType:
        """Infer event type from event ID."""
        if event_id.startswith("ELECTION:"):
            return EventType.ELECTION
        elif event_id.startswith("CRYPTO:"):
            return EventType.CRYPTO
        elif event_id.startswith("AWARDS:"):
            return EventType.AWARDS
        elif event_id.startswith("SPORTS:"):
            return EventType.SPORTS
        else:
            return EventType.OTHER
    
    def _infer_scope(self, event_id: str) -> EventScope:
        """Infer scope from event ID."""
        if ":US:" in event_id:
            return EventScope.US
        elif ":GLOBAL:" in event_id:
            return EventScope.GLOBAL
        else:
            return EventScope.OTHER

