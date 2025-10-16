"""Event Registry for canonical event identification.

This module implements a deterministic event registry system similar to betfairmappings,
mapping venue-specific market IDs to canonical event IDs for cross-venue arbitrage.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(str, Enum):
    """Canonical event type categories."""
    
    ELECTION = "ELECTION"
    CRYPTO = "CRYPTO"
    AWARDS = "AWARDS"
    SPORTS = "SPORTS"
    FINANCE = "FINANCE"
    POLITICS = "POLITICS"
    OTHER = "OTHER"


class EventScope(str, Enum):
    """Geographical or contextual scope."""
    
    US = "US"
    GLOBAL = "GLOBAL"
    EU = "EU"
    ASIA = "ASIA"
    OTHER = "OTHER"


@dataclass
class CanonicalEvent:
    """Canonical event with deterministic ID.
    
    The event_id is constructed deterministically from core attributes:
    {TYPE}:{SCOPE}:{DESCRIPTOR}:{DATE}:{OUTCOME}
    
    Examples:
        ELECTION:PRESIDENT:2028:US:TRUMP
        CRYPTO:BTC_TARGET:150000:2025-12-31
        AWARDS:OSCARS:BEST_ACTRESS:2026:EMMA_STONE
    """
    
    event_id: str
    event_type: EventType
    scope: EventScope
    date_open: datetime | None
    date_close: datetime
    canonical_units: str  # e.g., "YES/NO", "DOLLARS", "CELSIUS"
    parameters: dict[str, Any] = field(default_factory=dict)
    display_title: str = ""
    resolution_source: str = ""
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def build_event_id(
        cls,
        event_type: EventType | str,
        scope: EventScope | str,
        *components: str,
    ) -> str:
        """Build deterministic event ID from components.
        
        Args:
            event_type: Type of event
            scope: Geographical/contextual scope
            *components: Additional descriptor components
            
        Returns:
            Canonical event ID string
            
        Examples:
            >>> build_event_id("ELECTION", "US", "PRESIDENT", "2028", "TRUMP")
            'ELECTION:US:PRESIDENT:2028:TRUMP'
        """
        if isinstance(event_type, EventType):
            event_type = event_type.value
        if isinstance(scope, EventScope):
            scope = scope.value
            
        # Normalize components
        normalized = [str(c).upper().strip() for c in components]
        
        # Build ID
        event_id = f"{event_type}:{scope}:{':'.join(normalized)}"
        
        return event_id
    
    def add_alias(self, alias: str) -> None:
        """Add an alias for this event."""
        if alias and alias not in self.aliases:
            self.aliases.append(alias)


@dataclass
class VenueMapping:
    """Mapping from venue-specific market to canonical event."""
    
    venue: str  # e.g., "polymarket", "kalshi"
    market_id: str  # Venue's native market ID
    event_id: str  # Canonical event ID
    title_raw: str  # Original market title from venue
    description_raw: str = ""  # Original description
    outcomes: list[str] = field(default_factory=list)  # e.g., ["YES", "NO"]
    confidence: float = 1.0  # Mapping confidence (1.0 = manual/certain)
    mapping_method: str = "manual"  # "manual", "deterministic", "heuristic"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class EventRegistry:
    """Registry for managing canonical events and venue mappings."""
    
    def __init__(
        self,
        events_file: str | Path | None = None,
        mappings_file: str | Path | None = None,
    ):
        """Initialize event registry.
        
        Args:
            events_file: Path to canonical events CSV
            mappings_file: Path to venue mappings CSV
        """
        self.events_file = Path(events_file) if events_file else None
        self.mappings_file = Path(mappings_file) if mappings_file else None
        
        # In-memory storage
        self.events: dict[str, CanonicalEvent] = {}
        self.mappings: dict[str, VenueMapping] = {}  # Key: f"{venue}:{market_id}"
        self.event_aliases: dict[str, str] = {}  # Alias -> event_id
        
        # Load from disk
        self._load_events()
        self._load_mappings()
    
    def add_event(self, event: CanonicalEvent) -> None:
        """Add a canonical event to the registry."""
        self.events[event.event_id] = event
        
        # Register aliases
        for alias in event.aliases:
            self.event_aliases[alias.upper()] = event.event_id
    
    def get_event(self, event_id: str) -> CanonicalEvent | None:
        """Get canonical event by ID."""
        return self.events.get(event_id)
    
    def add_mapping(self, mapping: VenueMapping) -> None:
        """Add a venue mapping to the registry."""
        key = f"{mapping.venue}:{mapping.market_id}"
        mapping.updated_at = datetime.utcnow()
        self.mappings[key] = mapping
    
    def get_mapping(self, venue: str, market_id: str) -> VenueMapping | None:
        """Get venue mapping for a specific market."""
        key = f"{venue}:{market_id}"
        return self.mappings.get(key)
    
    def get_event_id(self, venue: str, market_id: str) -> str | None:
        """Get canonical event ID for a venue market.
        
        Args:
            venue: Venue name (e.g., "polymarket")
            market_id: Venue's market ID
            
        Returns:
            Canonical event ID or None if not mapped
        """
        mapping = self.get_mapping(venue, market_id)
        return mapping.event_id if mapping else None
    
    def get_mapped_markets(self, event_id: str) -> list[VenueMapping]:
        """Get all venue mappings for a canonical event."""
        return [
            mapping for mapping in self.mappings.values()
            if mapping.event_id == event_id
        ]
    
    def search_by_alias(self, alias: str) -> CanonicalEvent | None:
        """Search for event by alias."""
        event_id = self.event_aliases.get(alias.upper())
        return self.events.get(event_id) if event_id else None
    
    def get_coverage_stats(self) -> dict[str, Any]:
        """Get mapping coverage statistics."""
        total_events = len(self.events)
        total_mappings = len(self.mappings)
        
        # Count by venue
        venue_counts: dict[str, int] = {}
        for mapping in self.mappings.values():
            venue_counts[mapping.venue] = venue_counts.get(mapping.venue, 0) + 1
        
        # Count by method
        method_counts: dict[str, int] = {}
        for mapping in self.mappings.values():
            method = mapping.mapping_method
            method_counts[method] = method_counts.get(method, 0) + 1
        
        # Events with cross-venue mappings
        events_with_multiple_venues = 0
        for event_id in self.events:
            mapped_markets = self.get_mapped_markets(event_id)
            venues = set(m.venue for m in mapped_markets)
            if len(venues) >= 2:
                events_with_multiple_venues += 1
        
        return {
            "total_events": total_events,
            "total_mappings": total_mappings,
            "events_with_cross_venue": events_with_multiple_venues,
            "coverage_by_venue": venue_counts,
            "coverage_by_method": method_counts,
        }
    
    def save(self) -> None:
        """Save registry to disk."""
        self._save_events()
        self._save_mappings()
    
    def _load_events(self) -> None:
        """Load canonical events from CSV."""
        if not self.events_file or not self.events_file.exists():
            return
        
        try:
            with open(self.events_file, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    event = self._parse_event_row(row)
                    if event:
                        self.add_event(event)
        except Exception as e:
            print(f"Failed to load events from {self.events_file}: {e}")
    
    def _load_mappings(self) -> None:
        """Load venue mappings from CSV."""
        if not self.mappings_file or not self.mappings_file.exists():
            return
        
        try:
            with open(self.mappings_file, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    mapping = self._parse_mapping_row(row)
                    if mapping:
                        self.add_mapping(mapping)
        except Exception as e:
            print(f"Failed to load mappings from {self.mappings_file}: {e}")
    
    def _save_events(self) -> None:
        """Save canonical events to CSV."""
        if not self.events_file:
            return
        
        try:
            self.events_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.events_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'event_id', 'event_type', 'scope', 'date_close',
                    'canonical_units', 'display_title', 'resolution_source',
                    'aliases', 'created_at'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for event in self.events.values():
                    writer.writerow({
                        'event_id': event.event_id,
                        'event_type': event.event_type.value,
                        'scope': event.scope.value,
                        'date_close': event.date_close.isoformat(),
                        'canonical_units': event.canonical_units,
                        'display_title': event.display_title,
                        'resolution_source': event.resolution_source,
                        'aliases': '|'.join(event.aliases),
                        'created_at': event.created_at.isoformat(),
                    })
        except Exception as e:
            print(f"Failed to save events to {self.events_file}: {e}")
    
    def _save_mappings(self) -> None:
        """Save venue mappings to CSV."""
        if not self.mappings_file:
            return
        
        try:
            self.mappings_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.mappings_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'venue', 'market_id', 'event_id', 'title_raw',
                    'description_raw', 'outcomes', 'confidence',
                    'mapping_method', 'created_at', 'updated_at'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for mapping in self.mappings.values():
                    writer.writerow({
                        'venue': mapping.venue,
                        'market_id': mapping.market_id,
                        'event_id': mapping.event_id,
                        'title_raw': mapping.title_raw,
                        'description_raw': mapping.description_raw,
                        'outcomes': '|'.join(mapping.outcomes),
                        'confidence': mapping.confidence,
                        'mapping_method': mapping.mapping_method,
                        'created_at': mapping.created_at.isoformat(),
                        'updated_at': mapping.updated_at.isoformat(),
                    })
        except Exception as e:
            print(f"Failed to save mappings to {self.mappings_file}: {e}")
    
    def _parse_event_row(self, row: dict[str, str]) -> CanonicalEvent | None:
        """Parse event from CSV row."""
        try:
            aliases = row.get('aliases', '').split('|') if row.get('aliases') else []
            aliases = [a.strip() for a in aliases if a.strip()]
            
            return CanonicalEvent(
                event_id=row['event_id'],
                event_type=EventType(row['event_type']),
                scope=EventScope(row['scope']),
                date_open=None,
                date_close=datetime.fromisoformat(row['date_close']),
                canonical_units=row.get('canonical_units', 'YES/NO'),
                display_title=row.get('display_title', ''),
                resolution_source=row.get('resolution_source', ''),
                aliases=aliases,
                created_at=datetime.fromisoformat(row.get('created_at', datetime.utcnow().isoformat())),
            )
        except (KeyError, ValueError) as e:
            print(f"Failed to parse event row: {e}")
            return None
    
    def _parse_mapping_row(self, row: dict[str, str]) -> VenueMapping | None:
        """Parse mapping from CSV row."""
        try:
            outcomes = row.get('outcomes', '').split('|') if row.get('outcomes') else []
            outcomes = [o.strip() for o in outcomes if o.strip()]
            
            return VenueMapping(
                venue=row['venue'],
                market_id=row['market_id'],
                event_id=row['event_id'],
                title_raw=row.get('title_raw', ''),
                description_raw=row.get('description_raw', ''),
                outcomes=outcomes,
                confidence=float(row.get('confidence', 1.0)),
                mapping_method=row.get('mapping_method', 'manual'),
                created_at=datetime.fromisoformat(row.get('created_at', datetime.utcnow().isoformat())),
                updated_at=datetime.fromisoformat(row.get('updated_at', datetime.utcnow().isoformat())),
            )
        except (KeyError, ValueError) as e:
            print(f"Failed to parse mapping row: {e}")
            return None


def generate_event_id_hash(*components: str) -> str:
    """Generate a deterministic hash-based event ID.
    
    Useful for creating consistent IDs from multiple components.
    
    Args:
        *components: Components to hash together
        
    Returns:
        8-character hex hash
    """
    content = ":".join(str(c).upper().strip() for c in components)
    return hashlib.sha256(content.encode()).hexdigest()[:8].upper()

