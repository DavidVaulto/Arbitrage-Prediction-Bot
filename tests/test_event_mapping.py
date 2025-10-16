"""Unit tests for event registry and deterministic mapping."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.core.event_registry import CanonicalEvent, EventRegistry, EventScope, EventType, VenueMapping
from src.core.venue_mappers import KalshiMapper, PolymarketMapper


class TestEventRegistry:
    """Test Event Registry functionality."""
    
    def test_build_event_id(self):
        """Test deterministic event ID building."""
        event_id = CanonicalEvent.build_event_id(
            "ELECTION", "US", "PRESIDENT", "2028", "TRUMP"
        )
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_build_event_id_normalization(self):
        """Test event ID component normalization."""
        event_id = CanonicalEvent.build_event_id(
            "election", "us", "president ", "2028", " trump"
        )
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_add_and_get_event(self):
        """Test adding and retrieving events."""
        registry = EventRegistry()
        
        event = CanonicalEvent(
            event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
            event_type=EventType.ELECTION,
            scope=EventScope.US,
            date_open=None,
            date_close=datetime(2028, 11, 5),
            canonical_units="YES/NO",
            display_title="Will Trump win the 2028 Presidential Election?",
        )
        
        registry.add_event(event)
        
        retrieved = registry.get_event("ELECTION:US:PRESIDENT:2028:TRUMP")
        assert retrieved is not None
        assert retrieved.event_id == event.event_id
        assert retrieved.event_type == EventType.ELECTION
    
    def test_add_and_get_mapping(self):
        """Test adding and retrieving venue mappings."""
        registry = EventRegistry()
        
        mapping = VenueMapping(
            venue="polymarket",
            market_id="test_market_123",
            event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
            title_raw="Will Trump win 2028?",
            confidence=1.0,
            mapping_method="manual",
        )
        
        registry.add_mapping(mapping)
        
        retrieved = registry.get_mapping("polymarket", "test_market_123")
        assert retrieved is not None
        assert retrieved.market_id == "test_market_123"
        assert retrieved.event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_get_event_id(self):
        """Test getting event ID from venue mapping."""
        registry = EventRegistry()
        
        mapping = VenueMapping(
            venue="polymarket",
            market_id="market_123",
            event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
            title_raw="Trump 2028?",
        )
        
        registry.add_mapping(mapping)
        
        event_id = registry.get_event_id("polymarket", "market_123")
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_get_mapped_markets(self):
        """Test retrieving all markets mapped to an event."""
        registry = EventRegistry()
        
        registry.add_mapping(VenueMapping(
            venue="polymarket",
            market_id="pm_123",
            event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
            title_raw="Trump 2028?",
        ))
        
        registry.add_mapping(VenueMapping(
            venue="kalshi",
            market_id="PRES-2028-TRUMP",
            event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
            title_raw="Trump wins 2028?",
        ))
        
        markets = registry.get_mapped_markets("ELECTION:US:PRESIDENT:2028:TRUMP")
        assert len(markets) == 2
        venues = {m.venue for m in markets}
        assert venues == {"polymarket", "kalshi"}
    
    def test_save_and_load_events(self):
        """Test saving and loading events from CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            events_file = Path(tmpdir) / "events.csv"
            
            # Create and save
            registry1 = EventRegistry(events_file=events_file)
            event = CanonicalEvent(
                event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
                event_type=EventType.ELECTION,
                scope=EventScope.US,
                date_open=None,
                date_close=datetime(2028, 11, 5),
                canonical_units="YES/NO",
                display_title="Trump 2028",
            )
            registry1.add_event(event)
            registry1.save()
            
            # Load in new registry
            registry2 = EventRegistry(events_file=events_file)
            loaded = registry2.get_event("ELECTION:US:PRESIDENT:2028:TRUMP")
            
            assert loaded is not None
            assert loaded.event_id == event.event_id
            assert loaded.event_type == EventType.ELECTION
    
    def test_save_and_load_mappings(self):
        """Test saving and loading mappings from CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_file = Path(tmpdir) / "mappings.csv"
            
            # Create and save
            registry1 = EventRegistry(mappings_file=mappings_file)
            mapping = VenueMapping(
                venue="polymarket",
                market_id="pm_123",
                event_id="ELECTION:US:PRESIDENT:2028:TRUMP",
                title_raw="Trump 2028?",
            )
            registry1.add_mapping(mapping)
            registry1.save()
            
            # Load in new registry
            registry2 = EventRegistry(mappings_file=mappings_file)
            loaded = registry2.get_mapping("polymarket", "pm_123")
            
            assert loaded is not None
            assert loaded.market_id == "pm_123"
            assert loaded.event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"


class TestPolymarketMapper:
    """Test Polymarket-specific mapper."""
    
    def test_election_mapping_trump(self):
        """Test mapping Trump election market."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_12345",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={"close_time": datetime(2028, 11, 5)},
        )
        
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_election_mapping_biden(self):
        """Test mapping Biden election market."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_67890",
            title="Will Joe Biden win the 2024 Presidential Election?",
            description="",
            metadata={},
        )
        
        assert event_id == "ELECTION:US:PRESIDENT:2024:BIDEN"
    
    def test_crypto_btc_target(self):
        """Test mapping Bitcoin price target market."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_crypto_1",
            title="Will Bitcoin reach $150,000 by end of 2025?",
            description="",
            metadata={},
        )
        
        assert event_id is not None
        assert "CRYPTO" in event_id
        assert "BTC" in event_id
        assert "150000" in event_id
    
    def test_crypto_btc_shorthand(self):
        """Test mapping Bitcoin market with shorthand."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_crypto_2",
            title="BTC to $100K by December 2024?",
            description="",
            metadata={},
        )
        
        assert event_id is not None
        assert "CRYPTO" in event_id
        assert "BTC" in event_id
    
    def test_awards_oscars(self):
        """Test mapping Oscars award market."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_awards_1",
            title="Will Emma Stone win Best Actress at the 2026 Oscars?",
            description="",
            metadata={},
        )
        
        assert event_id is not None
        assert "AWARDS" in event_id
        assert "OSCARS" in event_id
        assert "2026" in event_id
    
    def test_abstain_on_unclear_market(self):
        """Test that mapper abstains on unclear markets."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_unclear",
            title="Will something happen?",
            description="Very vague market",
            metadata={},
        )
        
        # Should abstain
        assert event_id is None
    
    def test_creates_event_in_registry(self):
        """Test that successful mapping creates event in registry."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="pm_test",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={"close_time": datetime(2028, 11, 5)},
        )
        
        assert event_id is not None
        
        # Check event was created
        event = registry.get_event(event_id)
        assert event is not None
        assert event.event_type == EventType.ELECTION
        
        # Check mapping was created
        mapping = registry.get_mapping("polymarket", "pm_test")
        assert mapping is not None
        assert mapping.event_id == event_id


class TestKalshiMapper:
    """Test Kalshi-specific mapper."""
    
    def test_ticker_election_format(self):
        """Test mapping Kalshi ticker format for elections."""
        registry = EventRegistry()
        mapper = KalshiMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="PRES-2028-TRUMP",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_ticker_crypto_format(self):
        """Test mapping Kalshi ticker format for crypto."""
        registry = EventRegistry()
        mapper = KalshiMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="BTC-150K-2025",
            title="Bitcoin to $150K by 2025?",
            description="",
            metadata={},
        )
        
        assert event_id is not None
        assert "CRYPTO" in event_id
        assert "BTC" in event_id
        assert "150000" in event_id
    
    def test_title_based_election_mapping(self):
        """Test title-based mapping when ticker doesn't match."""
        registry = EventRegistry()
        mapper = KalshiMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="CUSTOM-ID-123",
            title="Will Donald Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        assert event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
    
    def test_creates_mapping_in_registry(self):
        """Test that successful mapping creates mapping in registry."""
        registry = EventRegistry()
        mapper = KalshiMapper(registry)
        
        event_id = mapper.map_to_event_id(
            market_id="PRES-2028-TRUMP",
            title="Trump 2028",
            description="",
            metadata={},
        )
        
        assert event_id is not None
        
        # Check mapping was created
        mapping = registry.get_mapping("kalshi", "PRES-2028-TRUMP")
        assert mapping is not None
        assert mapping.event_id == event_id
        assert mapping.venue == "kalshi"


class TestCrossVenueMapping:
    """Test cross-venue event mapping."""
    
    def test_same_event_different_venues(self):
        """Test that same event maps consistently across venues."""
        registry = EventRegistry()
        
        pm_mapper = PolymarketMapper(registry)
        kalshi_mapper = KalshiMapper(registry)
        
        # Map Polymarket market
        pm_event_id = pm_mapper.map_to_event_id(
            market_id="pm_123",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        # Map Kalshi market
        kalshi_event_id = kalshi_mapper.map_to_event_id(
            market_id="PRES-2028-TRUMP",
            title="Trump wins 2028 Presidential Election",
            description="",
            metadata={},
        )
        
        # Should map to same canonical event
        assert pm_event_id == kalshi_event_id
        assert pm_event_id == "ELECTION:US:PRESIDENT:2028:TRUMP"
        
        # Check both mappings exist
        markets = registry.get_mapped_markets(pm_event_id)
        assert len(markets) == 2
        venues = {m.venue for m in markets}
        assert venues == {"polymarket", "kalshi"}
    
    def test_registry_tracks_cross_venue_events(self):
        """Test that registry correctly tracks cross-venue coverage."""
        registry = EventRegistry()
        
        pm_mapper = PolymarketMapper(registry)
        kalshi_mapper = KalshiMapper(registry)
        
        # Map same event on both venues
        pm_mapper.map_to_event_id(
            market_id="pm_trump",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        kalshi_mapper.map_to_event_id(
            market_id="PRES-2028-TRUMP",
            title="Trump 2028",
            description="",
            metadata={},
        )
        
        # Check stats
        stats = registry.get_coverage_stats()
        assert stats["events_with_cross_venue"] == 1
        assert stats["total_mappings"] == 2


class TestDeterministicMatching:
    """Test deterministic event ID matching."""
    
    def test_deterministic_id_is_consistent(self):
        """Test that event IDs are deterministically generated."""
        registry1 = EventRegistry()
        registry2 = EventRegistry()
        
        mapper1 = PolymarketMapper(registry1)
        mapper2 = PolymarketMapper(registry2)
        
        event_id_1 = mapper1.map_to_event_id(
            market_id="test_1",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        event_id_2 = mapper2.map_to_event_id(
            market_id="test_2",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        # Should produce same event ID
        assert event_id_1 == event_id_2
    
    def test_similar_titles_different_events(self):
        """Test that similar titles for different events don't collide."""
        registry = EventRegistry()
        mapper = PolymarketMapper(registry)
        
        event_2024 = mapper.map_to_event_id(
            market_id="trump_2024",
            title="Will Trump win the 2024 Presidential Election?",
            description="",
            metadata={},
        )
        
        event_2028 = mapper.map_to_event_id(
            market_id="trump_2028",
            title="Will Trump win the 2028 Presidential Election?",
            description="",
            metadata={},
        )
        
        # Should be different events
        assert event_2024 != event_2028
        assert "2024" in event_2024
        assert "2028" in event_2028

