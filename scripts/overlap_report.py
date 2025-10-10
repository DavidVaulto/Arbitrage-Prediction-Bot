#!/usr/bin/env python3
"""Generate overlap report from pairs data."""

import argparse
import sys
from pathlib import Path

import pandas as pd


def generate_report(pairs_path: str, top_n: int = 50):
    """Generate overlap report."""
    print(f"Loading pairs from: {pairs_path}")
    
    try:
        pairs_df = pd.read_parquet(pairs_path)
    except FileNotFoundError:
        print(f"Error: File not found: {pairs_path}")
        print("Run 'make pairs' first to generate pairs.")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"MARKET OVERLAP REPORT")
    print(f"{'='*80}\n")
    
    print(f"Total pairs found: {len(pairs_df)}")
    
    if len(pairs_df) == 0:
        print("\nNo pairs found. The markets may not have overlapping topics.")
        return
    
    # Summary statistics
    print(f"\nScore Statistics:")
    print(f"  Mean:   {pairs_df.score.mean():.3f}")
    print(f"  Median: {pairs_df.score.median():.3f}")
    print(f"  Min:    {pairs_df.score.min():.3f}")
    print(f"  Max:    {pairs_df.score.max():.3f}")
    
    # Market type breakdown
    print(f"\nMarket Type Breakdown:")
    type_counts = pairs_df.market_type.value_counts()
    for market_type, count in type_counts.items():
        print(f"  {market_type}: {count} pairs")
    
    # Top N pairs
    print(f"\n{'='*80}")
    print(f"TOP {top_n} MATCHED PAIRS (by score)")
    print(f"{'='*80}\n")
    
    top_pairs = pairs_df.nlargest(top_n, 'score')
    
    for i, row in enumerate(top_pairs.iterrows(), 1):
        _, pair = row
        
        print(f"{i}. Score: {pair.score:.3f} | Type: {pair.market_type}")
        print(f"   Canonical Key: {pair.canonical_key}")
        print(f"   Polymarket:  {pair.pm_title[:70]}")
        print(f"   Kalshi:      {pair.kalshi_title[:70]}")
        
        # Show relevant features
        if pair.get('year'):
            print(f"   Year: {pair.year}", end="")
        if pair.get('office'):
            print(f" | Office: {pair.office}", end="")
        if pair.get('jurisdiction'):
            print(f" | Jurisdiction: {pair.jurisdiction}", end="")
        if pair.get('persons'):
            print(f" | Persons: {pair.persons}", end="")
        print()  # Newline
        print()
    
    # Venue representation check
    print(f"\n{'='*80}")
    print(f"VENUE REPRESENTATION")
    print(f"{'='*80}\n")
    
    unique_pm = pairs_df.pm_market_id.nunique()
    unique_kalshi = pairs_df.kalshi_market_id.nunique()
    
    print(f"Unique Polymarket markets in pairs: {unique_pm}")
    print(f"Unique Kalshi markets in pairs:     {unique_kalshi}")
    
    # Check for quality
    high_quality = len(pairs_df[pairs_df.score >= 0.8])
    medium_quality = len(pairs_df[(pairs_df.score >= 0.65) & (pairs_df.score < 0.8)])
    low_quality = len(pairs_df[pairs_df.score < 0.65])
    
    print(f"\nQuality Breakdown:")
    print(f"  High (≥0.80):    {high_quality} pairs")
    print(f"  Medium (0.65-0.80): {medium_quality} pairs")
    print(f"  Low (<0.65):     {low_quality} pairs")


def main():
    parser = argparse.ArgumentParser(description="Generate overlap report")
    parser.add_argument(
        "--pairs",
        default="data/pairs.parquet",
        help="Path to pairs parquet file (default: data/pairs.parquet)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Number of top pairs to show (default: 50)"
    )
    
    args = parser.parse_args()
    generate_report(args.pairs, args.top)


if __name__ == "__main__":
    main()

