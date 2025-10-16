#!/usr/bin/env python3
"""Backtest harness to measure mapping coverage and quality.

This tool analyzes historical market data to:
- Measure mapping coverage rates
- Identify unmapped markets
- Validate mapping quality
- Generate coverage reports
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.event_registry import EventRegistry
from src.core.venue_mappers import KalshiMapper, PolymarketMapper


class MappingCoverageAnalyzer:
    """Analyze mapping coverage from historical data."""
    
    def __init__(self, registry: EventRegistry):
        """Initialize analyzer.
        
        Args:
            registry: Event registry with mappings
        """
        self.registry = registry
        self.mappers = {
            "polymarket": PolymarketMapper(registry),
            "kalshi": KalshiMapper(registry),
        }
        
        self.stats = {
            "total_markets": 0,
            "mapped_markets": 0,
            "abstained_markets": 0,
            "cross_venue_markets": 0,
            "by_venue": defaultdict(lambda: {"total": 0, "mapped": 0, "abstained": 0}),
            "by_event_type": defaultdict(lambda: {"total": 0, "mapped": 0}),
            "unmapped_samples": [],
        }
    
    def analyze_parquet_file(self, file_path: str | Path, venue: str) -> None:
        """Analyze markets from a parquet file.
        
        Args:
            file_path: Path to parquet file with market data
            venue: Venue name (polymarket or kalshi)
        """
        df = pd.read_parquet(file_path)
        
        print(f"\nAnalyzing {len(df)} markets from {venue}...")
        
        # Get appropriate mapper
        mapper = self.mappers.get(venue)
        if not mapper:
            print(f"Warning: No mapper for venue {venue}")
            return
        
        # Analyze each market
        for idx, row in df.iterrows():
            self._analyze_market(row, venue, mapper)
        
        print(f"  Mapped: {self.stats['by_venue'][venue]['mapped']}")
        print(f"  Abstained: {self.stats['by_venue'][venue]['abstained']}")
        print(f"  Coverage: {self._calculate_coverage(venue):.1%}")
    
    def _analyze_market(self, market_data: Any, venue: str, mapper: Any) -> None:
        """Analyze a single market."""
        self.stats["total_markets"] += 1
        self.stats["by_venue"][venue]["total"] += 1
        
        # Extract market info
        market_id = self._get_market_id(market_data, venue)
        title = self._get_title(market_data, venue)
        description = self._get_description(market_data, venue)
        
        # Try to map
        event_id = mapper.map_to_event_id(
            market_id=market_id,
            title=title,
            description=description,
            metadata=self._extract_metadata(market_data, venue),
        )
        
        if event_id:
            self.stats["mapped_markets"] += 1
            self.stats["by_venue"][venue]["mapped"] += 1
            
            # Track event type
            event = self.registry.get_event(event_id)
            if event:
                event_type = event.event_type.value
                self.stats["by_event_type"][event_type]["total"] += 1
                self.stats["by_event_type"][event_type]["mapped"] += 1
        else:
            self.stats["abstained_markets"] += 1
            self.stats["by_venue"][venue]["abstained"] += 1
            
            # Sample unmapped markets for review
            if len(self.stats["unmapped_samples"]) < 50:
                self.stats["unmapped_samples"].append({
                    "venue": venue,
                    "market_id": market_id,
                    "title": title,
                    "description": description[:100] if description else "",
                })
    
    def _get_market_id(self, data: Any, venue: str) -> str:
        """Extract market ID from data."""
        if hasattr(data, "get"):
            return str(data.get("market_id") or data.get("id") or data.get("ticker") or "unknown")
        return getattr(data, "market_id", "unknown")
    
    def _get_title(self, data: Any, venue: str) -> str:
        """Extract title from data."""
        if hasattr(data, "get"):
            return str(data.get("title") or data.get("question") or data.get("name") or "")
        return getattr(data, "title", "")
    
    def _get_description(self, data: Any, venue: str) -> str:
        """Extract description from data."""
        if hasattr(data, "get"):
            return str(data.get("description") or data.get("desc") or "")
        return getattr(data, "description", "")
    
    def _extract_metadata(self, data: Any, venue: str) -> dict[str, Any]:
        """Extract metadata from data."""
        metadata = {}
        
        if hasattr(data, "get"):
            if "close_time" in data:
                metadata["close_time"] = data["close_time"]
            if "end_date" in data:
                metadata["close_time"] = data["end_date"]
        
        return metadata
    
    def _calculate_coverage(self, venue: str | None = None) -> float:
        """Calculate mapping coverage percentage."""
        if venue:
            stats = self.stats["by_venue"][venue]
            total = stats["total"]
            mapped = stats["mapped"]
        else:
            total = self.stats["total_markets"]
            mapped = self.stats["mapped_markets"]
        
        return mapped / total if total > 0 else 0.0
    
    def analyze_cross_venue_coverage(self) -> None:
        """Analyze cross-venue mapping coverage."""
        print("\nAnalyzing cross-venue coverage...")
        
        event_venues = defaultdict(set)
        
        # Track which venues have each event
        for mapping in self.registry.mappings.values():
            event_venues[mapping.event_id].add(mapping.venue)
        
        # Count events with multiple venues
        cross_venue_count = sum(1 for venues in event_venues.values() if len(venues) >= 2)
        
        self.stats["cross_venue_markets"] = cross_venue_count
        
        print(f"  Events mapped across multiple venues: {cross_venue_count}")
        print(f"  Total unique events: {len(event_venues)}")
    
    def generate_report(self, output_path: str | None = None) -> None:
        """Generate coverage report.
        
        Args:
            output_path: Optional path to save report
        """
        report = []
        report.append("=" * 80)
        report.append("MAPPING COVERAGE REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Overall statistics
        report.append("OVERALL STATISTICS")
        report.append("-" * 80)
        report.append(f"Total markets analyzed: {self.stats['total_markets']}")
        report.append(f"Successfully mapped: {self.stats['mapped_markets']}")
        report.append(f"Abstained (unmapped): {self.stats['abstained_markets']}")
        report.append(f"Overall coverage: {self._calculate_coverage():.1%}")
        report.append("")
        
        # By venue
        report.append("COVERAGE BY VENUE")
        report.append("-" * 80)
        for venue, stats in self.stats["by_venue"].items():
            coverage = stats["mapped"] / stats["total"] if stats["total"] > 0 else 0
            report.append(f"{venue}:")
            report.append(f"  Total: {stats['total']}")
            report.append(f"  Mapped: {stats['mapped']}")
            report.append(f"  Coverage: {coverage:.1%}")
            report.append("")
        
        # By event type
        if self.stats["by_event_type"]:
            report.append("COVERAGE BY EVENT TYPE")
            report.append("-" * 80)
            for event_type, stats in self.stats["by_event_type"].items():
                report.append(f"{event_type}: {stats['mapped']} markets")
        report.append("")
        
        # Cross-venue coverage
        report.append("CROSS-VENUE COVERAGE")
        report.append("-" * 80)
        report.append(f"Events mapped on multiple venues: {self.stats['cross_venue_markets']}")
        report.append("")
        
        # Registry statistics
        registry_stats = self.registry.get_coverage_stats()
        report.append("REGISTRY STATISTICS")
        report.append("-" * 80)
        report.append(f"Total canonical events: {registry_stats['total_events']}")
        report.append(f"Total venue mappings: {registry_stats['total_mappings']}")
        report.append("")
        
        # Unmapped samples
        if self.stats["unmapped_samples"]:
            report.append("UNMAPPED MARKET SAMPLES (for review)")
            report.append("-" * 80)
            for i, sample in enumerate(self.stats["unmapped_samples"][:20], 1):
                report.append(f"{i}. [{sample['venue']}] {sample['market_id']}")
                report.append(f"   Title: {sample['title']}")
                if sample['description']:
                    report.append(f"   Desc: {sample['description']}")
                report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS")
        report.append("-" * 80)
        
        coverage = self._calculate_coverage()
        if coverage < 0.5:
            report.append("⚠ Low coverage (<50%). Consider:")
            report.append("  - Adding more mapping patterns to venue mappers")
            report.append("  - Creating manual overrides for common markets")
        elif coverage < 0.8:
            report.append("✓ Moderate coverage (50-80%). Consider:")
            report.append("  - Review unmapped samples above")
            report.append("  - Add manual overrides for edge cases")
        else:
            report.append("✓ Good coverage (>80%)!")
            report.append("  - Continue monitoring unmapped markets")
            report.append("  - Add overrides for any critical markets")
        
        report.append("")
        report.append("=" * 80)
        
        # Print report
        report_text = "\n".join(report)
        print("\n" + report_text)
        
        # Save to file if requested
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(report_text)
            print(f"\n✓ Report saved to: {output_path}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze mapping coverage from historical market data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--events-file",
        help="Path to canonical events CSV",
        default=None,
    )
    parser.add_argument(
        "--mappings-file",
        help="Path to venue mappings CSV",
        default=None,
    )
    parser.add_argument(
        "--polymarket-data",
        help="Path to Polymarket parquet file",
        default=None,
    )
    parser.add_argument(
        "--kalshi-data",
        help="Path to Kalshi parquet file",
        default=None,
    )
    parser.add_argument(
        "--output",
        help="Path to save report",
        default=None,
    )
    
    args = parser.parse_args()
    
    # Setup registry
    events_file = args.events_file or Path(__file__).parent.parent / "data" / "canonical_events.csv"
    mappings_file = args.mappings_file or Path(__file__).parent.parent / "data" / "venue_mappings.csv"
    
    registry = EventRegistry(events_file=events_file, mappings_file=mappings_file)
    
    # Create analyzer
    analyzer = MappingCoverageAnalyzer(registry)
    
    # Analyze data files
    if args.polymarket_data:
        pm_file = Path(args.polymarket_data)
        if pm_file.exists():
            analyzer.analyze_parquet_file(pm_file, "polymarket")
        else:
            print(f"Warning: Polymarket file not found: {pm_file}")
    
    if args.kalshi_data:
        kalshi_file = Path(args.kalshi_data)
        if kalshi_file.exists():
            analyzer.analyze_parquet_file(kalshi_file, "kalshi")
        else:
            print(f"Warning: Kalshi file not found: {kalshi_file}")
    
    # Analyze cross-venue coverage
    analyzer.analyze_cross_venue_coverage()
    
    # Generate report
    analyzer.generate_report(output_path=args.output)


if __name__ == "__main__":
    main()

