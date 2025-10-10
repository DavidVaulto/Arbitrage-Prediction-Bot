"""Tests for event matcher module."""

from datetime import datetime, timedelta

from src.core.matcher import EventMatcher
from src.core.types import Contract, ContractSide, FeeModel, Venue


class TestEventMatcher:
    """Test event matching functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.matcher = EventMatcher()

        # Create test contracts
        self.contracts_a = [
            Contract(
                venue=Venue.POLYMARKET,
                contract_id="pm_event1_YES",
                event_key="Will Biden win 2024 election?",
                normalized_event_id="event1",
                side=ContractSide.YES,
                tick_size=0.01,
                settlement_ccy="USDC",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
            Contract(
                venue=Venue.POLYMARKET,
                contract_id="pm_event1_NO",
                event_key="Will Biden win 2024 election?",
                normalized_event_id="event1",
                side=ContractSide.NO,
                tick_size=0.01,
                settlement_ccy="USDC",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
        ]

        self.contracts_b = [
            Contract(
                venue=Venue.KALSHI,
                contract_id="kalshi_event1_YES",
                event_key="Biden wins 2024 election",
                normalized_event_id="event1",
                side=ContractSide.YES,
                tick_size=0.01,
                settlement_ccy="USD",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
            Contract(
                venue=Venue.KALSHI,
                contract_id="kalshi_event1_NO",
                event_key="Biden wins 2024 election",
                normalized_event_id="event1",
                side=ContractSide.NO,
                tick_size=0.01,
                settlement_ccy="USD",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
        ]

    def test_match_events_same_event(self):
        """Test matching same event across venues."""
        matched_pairs = self.matcher.match_events(
            self.contracts_a,
            self.contracts_b,
            min_confidence=0.5,
        )

        # Should find 2 pairs (YES and NO)
        assert len(matched_pairs) == 2

        # Check that pairs are correctly matched
        yes_pair = next(p for p in matched_pairs if p.contract_a.side == ContractSide.YES)
        no_pair = next(p for p in matched_pairs if p.contract_a.side == ContractSide.NO)

        assert yes_pair.contract_a.venue == Venue.POLYMARKET
        assert yes_pair.contract_b.venue == Venue.KALSHI
        assert yes_pair.contract_a.side == ContractSide.YES
        assert yes_pair.contract_b.side == ContractSide.YES

        assert no_pair.contract_a.venue == Venue.POLYMARKET
        assert no_pair.contract_b.venue == Venue.KALSHI
        assert no_pair.contract_a.side == ContractSide.NO
        assert no_pair.contract_b.side == ContractSide.NO

    def test_match_events_different_events(self):
        """Test matching different events."""
        # Create different event for venue B
        different_contracts_b = [
            Contract(
                venue=Venue.KALSHI,
                contract_id="kalshi_event2_YES",
                event_key="Will Trump win 2024 election?",
                normalized_event_id="event2",
                side=ContractSide.YES,
                tick_size=0.01,
                settlement_ccy="USD",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
        ]

        matched_pairs = self.matcher.match_events(
            self.contracts_a,
            different_contracts_b,
            min_confidence=0.5,
        )

        # Should find no matches
        assert len(matched_pairs) == 0

    def test_match_events_low_confidence(self):
        """Test matching with low confidence threshold."""
        matched_pairs = self.matcher.match_events(
            self.contracts_a,
            self.contracts_b,
            min_confidence=0.9,  # High threshold
        )

        # Should find no matches due to high threshold
        assert len(matched_pairs) == 0

    def test_title_similarity(self):
        """Test title similarity calculation."""
        title_a = "Will Biden win 2024 election?"
        title_b = "Biden wins 2024 election"

        similarity = self.matcher._calculate_title_similarity(title_a, title_b)

        # Should have high similarity
        assert similarity > 0.7

    def test_title_similarity_exact_match(self):
        """Test exact title match."""
        title_a = "Will Biden win 2024 election?"
        title_b = "Will Biden win 2024 election?"

        similarity = self.matcher._calculate_title_similarity(title_a, title_b)

        # Should be perfect match
        assert similarity == 1.0

    def test_title_similarity_no_match(self):
        """Test completely different titles."""
        title_a = "Will Biden win 2024 election?"
        title_b = "Will the stock market crash?"

        similarity = self.matcher._calculate_title_similarity(title_a, title_b)

        # Should have low similarity
        assert similarity < 0.5

    def test_expiry_similarity(self):
        """Test expiry similarity calculation."""
        expiry_a = datetime.utcnow() + timedelta(days=30)
        expiry_b = datetime.utcnow() + timedelta(days=31)

        similarity = self.matcher._calculate_expiry_similarity(expiry_a, expiry_b)

        # Should have high similarity (1 day difference)
        assert similarity > 0.8

    def test_expiry_similarity_far_apart(self):
        """Test expiry similarity for far apart dates."""
        expiry_a = datetime.utcnow() + timedelta(days=30)
        expiry_b = datetime.utcnow() + timedelta(days=37)  # 7 days apart

        similarity = self.matcher._calculate_expiry_similarity(expiry_a, expiry_b)

        # Should have low similarity
        assert similarity < 0.5

    def test_normalize_title(self):
        """Test title normalization."""
        title = "Will Biden win the 2024 election?"
        normalized = self.matcher._normalize_title(title)

        # Should remove stopwords and punctuation
        assert "will" not in normalized
        assert "the" not in normalized
        assert "?" not in normalized
        assert "biden" in normalized
        assert "win" in normalized
        assert "2024" in normalized
        assert "election" in normalized

    def test_manual_mapping(self):
        """Test manual event mapping."""
        # Add manual mapping
        self.matcher.add_manual_mapping("event1", "event2")

        # Create contracts with different normalized IDs
        contracts_a = [
            Contract(
                venue=Venue.POLYMARKET,
                contract_id="pm_event1_YES",
                event_key="Event 1",
                normalized_event_id="event1",
                side=ContractSide.YES,
                tick_size=0.01,
                settlement_ccy="USDC",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
        ]

        contracts_b = [
            Contract(
                venue=Venue.KALSHI,
                contract_id="kalshi_event2_YES",
                event_key="Event 2",
                normalized_event_id="event2",
                side=ContractSide.YES,
                tick_size=0.01,
                settlement_ccy="USD",
                expires_at=datetime.utcnow() + timedelta(days=30),
                fees=FeeModel(),
            ),
        ]

        matched_pairs = self.matcher.match_events(
            contracts_a,
            contracts_b,
            min_confidence=0.5,
        )

        # Should find match due to manual mapping
        assert len(matched_pairs) == 1
        assert matched_pairs[0].confidence_score == 1.0
        assert matched_pairs[0].match_reason == "manual_mapping_yes"

    def test_get_match_statistics(self):
        """Test match statistics calculation."""
        # Create some matched pairs
        matched_pairs = self.matcher.match_events(
            self.contracts_a,
            self.contracts_b,
            min_confidence=0.5,
        )

        stats = self.matcher.get_match_statistics(matched_pairs)

        assert stats["total_pairs"] == 2
        assert stats["avg_confidence"] > 0.0
        assert stats["manual_mappings"] == 0
        assert stats["automatic_matches"] == 2


