"""Event matching across different venues."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from .types import Contract, MatchedPair


class EventMatcher:
    """Matches events across different venues."""

    def __init__(self, mappings_file: str | None = None):
        """Initialize event matcher.
        
        Args:
            mappings_file: Path to CSV file with manual event mappings
        """
        self.mappings_file = mappings_file
        self.manual_mappings: dict[str, str] = {}
        self._load_manual_mappings()

    def _load_manual_mappings(self) -> None:
        """Load manual event mappings from CSV file."""
        if not self.mappings_file or not Path(self.mappings_file).exists():
            return

        try:
            with open(self.mappings_file, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    venue_a_id = row.get('venue_a_id', '').strip()
                    venue_b_id = row.get('venue_b_id', '').strip()
                    if venue_a_id and venue_b_id:
                        self.manual_mappings[venue_a_id] = venue_b_id
                        self.manual_mappings[venue_b_id] = venue_a_id

        except Exception as e:
            print(f"Failed to load manual mappings: {e}")

    def match_events(
        self,
        contracts_a: list[Contract],
        contracts_b: list[Contract],
        min_confidence: float = 0.7,
    ) -> list[MatchedPair]:
        """Match events between two venues.
        
        Args:
            contracts_a: Contracts from venue A
            contracts_b: Contracts from venue B
            min_confidence: Minimum confidence score for matches
            
        Returns:
            List of matched pairs
        """
        matched_pairs = []

        # Group contracts by normalized event ID
        events_a = self._group_contracts_by_event(contracts_a)
        events_b = self._group_contracts_by_event(contracts_b)

        # Check manual mappings first
        for event_id_a, contracts_a_group in events_a.items():
            if event_id_a in self.manual_mappings:
                event_id_b = self.manual_mappings[event_id_a]
                if event_id_b in events_b:
                    pairs = self._create_matched_pairs(
                        contracts_a_group,
                        events_b[event_id_b],
                        confidence_score=1.0,
                        match_reason="manual_mapping",
                    )
                    matched_pairs.extend(pairs)

        # Find automatic matches
        for event_id_a, contracts_a_group in events_a.items():
            if event_id_a in self.manual_mappings:
                continue  # Skip manually mapped events

            best_match = None
            best_score = 0.0

            for event_id_b, contracts_b_group in events_b.items():
                if event_id_b in self.manual_mappings:
                    continue  # Skip manually mapped events

                score = self._calculate_match_score(
                    contracts_a_group,
                    contracts_b_group,
                )

                if score > best_score and score >= min_confidence:
                    best_match = contracts_b_group
                    best_score = score

            if best_match:
                pairs = self._create_matched_pairs(
                    contracts_a_group,
                    best_match,
                    confidence_score=best_score,
                    match_reason="automatic",
                )
                matched_pairs.extend(pairs)

        return matched_pairs

    def _group_contracts_by_event(self, contracts: list[Contract]) -> dict[str, list[Contract]]:
        """Group contracts by normalized event ID."""
        events = {}
        for contract in contracts:
            event_id = contract.normalized_event_id
            if event_id not in events:
                events[event_id] = []
            events[event_id].append(contract)
        return events

    def _create_matched_pairs(
        self,
        contracts_a: list[Contract],
        contracts_b: list[Contract],
        confidence_score: float,
        match_reason: str,
    ) -> list[MatchedPair]:
        """Create matched pairs from contract groups."""
        pairs = []

        # Find YES and NO contracts for each venue
        yes_a = next((c for c in contracts_a if c.side.value == "YES"), None)
        no_a = next((c for c in contracts_a if c.side.value == "NO"), None)
        yes_b = next((c for c in contracts_b if c.side.value == "YES"), None)
        no_b = next((c for c in contracts_b if c.side.value == "NO"), None)

        if yes_a and yes_b:
            pairs.append(MatchedPair(
                event_id=yes_a.normalized_event_id,
                contract_a=yes_a,
                contract_b=yes_b,
                confidence_score=confidence_score,
                match_reason=f"{match_reason}_yes",
            ))

        if no_a and no_b:
            pairs.append(MatchedPair(
                event_id=no_a.normalized_event_id,
                contract_a=no_a,
                contract_b=no_b,
                confidence_score=confidence_score,
                match_reason=f"{match_reason}_no",
            ))

        return pairs

    def _calculate_match_score(
        self,
        contracts_a: list[Contract],
        contracts_b: list[Contract],
    ) -> float:
        """Calculate match score between two contract groups."""
        if not contracts_a or not contracts_b:
            return 0.0

        # Get representative contracts
        contract_a = contracts_a[0]
        contract_b = contracts_b[0]

        # Calculate various similarity scores
        title_score = self._calculate_title_similarity(
            contract_a.event_key,
            contract_b.event_key,
        )

        expiry_score = self._calculate_expiry_similarity(
            contract_a.expires_at,
            contract_b.expires_at,
        )

        # Weighted combination
        total_score = (
            0.6 * title_score +
            0.4 * expiry_score
        )

        return min(total_score, 1.0)

    def _calculate_title_similarity(self, title_a: str, title_b: str) -> float:
        """Calculate similarity between event titles."""
        if not title_a or not title_b:
            return 0.0

        # Normalize titles
        norm_a = self._normalize_title(title_a)
        norm_b = self._normalize_title(title_b)

        # Calculate string similarity
        similarity = SequenceMatcher(None, norm_a, norm_b).ratio()

        # Boost score for exact matches
        if norm_a == norm_b:
            similarity = 1.0

        return similarity

    def _calculate_expiry_similarity(self, expiry_a: datetime, expiry_b: datetime) -> float:
        """Calculate similarity between expiry dates."""
        if not expiry_a or not expiry_b:
            return 0.0

        # Calculate time difference
        time_diff = abs((expiry_a - expiry_b).total_seconds())

        # Score decreases with time difference
        # Perfect match (0 difference) = 1.0
        # 1 day difference = 0.8
        # 3 days difference = 0.4
        # 7 days difference = 0.0
        max_diff = 7 * 24 * 3600  # 7 days in seconds
        score = max(0.0, 1.0 - (time_diff / max_diff))

        return score

    def _normalize_title(self, title: str) -> str:
        """Normalize event title for comparison."""
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower()

        # Remove common stopwords
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into", "through", "during",
            "before", "after", "above", "below", "between", "among", "is", "are",
            "was", "were", "be", "been", "being", "have", "has", "had", "do",
            "does", "did", "will", "would", "could", "should", "may", "might",
            "must", "can", "shall", "this", "that", "these", "those", "i", "you",
            "he", "she", "it", "we", "they", "me", "him", "her", "us", "them"
        }

        words = normalized.split()
        filtered_words = [word for word in words if word not in stopwords]

        # Remove punctuation and special characters
        cleaned_words = []
        for word in filtered_words:
            cleaned = re.sub(r'[^\w]', '', word)
            if cleaned:
                cleaned_words.append(cleaned)

        return " ".join(cleaned_words)

    def add_manual_mapping(self, venue_a_id: str, venue_b_id: str) -> None:
        """Add a manual mapping between venues."""
        self.manual_mappings[venue_a_id] = venue_b_id
        self.manual_mappings[venue_b_id] = venue_a_id

        # Save to file if mappings file is specified
        if self.mappings_file:
            self._save_manual_mappings()

    def _save_manual_mappings(self) -> None:
        """Save manual mappings to CSV file."""
        if not self.mappings_file:
            return

        try:
            # Create directory if it doesn't exist
            Path(self.mappings_file).parent.mkdir(parents=True, exist_ok=True)

            with open(self.mappings_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['venue_a_id', 'venue_b_id'])

                # Write mappings (avoid duplicates)
                written = set()
                for venue_a_id, venue_b_id in self.manual_mappings.items():
                    if venue_a_id not in written and venue_b_id not in written:
                        writer.writerow([venue_a_id, venue_b_id])
                        written.add(venue_a_id)
                        written.add(venue_b_id)

        except Exception as e:
            print(f"Failed to save manual mappings: {e}")

    def get_match_statistics(self, matched_pairs: list[MatchedPair]) -> dict[str, float]:
        """Get statistics about matched pairs."""
        if not matched_pairs:
            return {
                "total_pairs": 0,
                "avg_confidence": 0.0,
                "manual_mappings": 0,
                "automatic_matches": 0,
            }

        total_pairs = len(matched_pairs)
        avg_confidence = sum(pair.confidence_score for pair in matched_pairs) / total_pairs
        manual_mappings = sum(1 for pair in matched_pairs if "manual" in pair.match_reason)
        automatic_matches = total_pairs - manual_mappings

        return {
            "total_pairs": total_pairs,
            "avg_confidence": avg_confidence,
            "manual_mappings": manual_mappings,
            "automatic_matches": automatic_matches,
        }


