#!/usr/bin/env python3
"""Build market pairs from quote data."""

import argparse
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pandas as pd
from match.features import extract_features
from match.canonical import make_key
from match.score import score_pair_with_market_type


def build_pairs(
    data_path: str,
    out_path: str,
    score_threshold: float = 0.75,
    loose_mode: bool = False
):
    """Build market pairs from quote data."""
    print(f"Loading data from: {data_path}")
    df = pd.read_parquet(data_path)
    
    print(f"Total rows: {len(df)}")
    print(f"Venues: {df.venue.unique()}")
    
    # Group by venue and extract unique markets
    pm_markets = df[df.venue == 'polymarket'][['contract_id', 'title']].drop_duplicates()
    kalshi_markets = df[df.venue == 'kalshi'][['contract_id', 'title']].drop_duplicates()
    
    print(f"\nUnique Polymarket markets: {len(pm_markets)}")
    print(f"Unique Kalshi markets: {len(kalshi_markets)}")
    
    # Extract features for all markets
    print("\nExtracting features...")
    pm_features_list = []
    for _, row in pm_markets.iterrows():
        features = extract_features(row['title'], "")
        features['contract_id'] = row['contract_id']
        features['canonical_key'] = make_key(features)
        pm_features_list.append(features)
    
    kalshi_features_list = []
    for _, row in kalshi_markets.iterrows():
        features = extract_features(row['title'], "")
        features['contract_id'] = row['contract_id']
        features['canonical_key'] = make_key(features)
        kalshi_features_list.append(features)
    
    # Score all pairs
    print("\nScoring pairs...")
    pairs = []
    
    for pm_feat in pm_features_list:
        best_match = None
        best_score = 0.0
        
        for kalshi_feat in kalshi_features_list:
            score = score_pair_with_market_type(pm_feat, kalshi_feat)
            
            if score > best_score:
                best_score = score
                best_match = kalshi_feat
        
        # Only keep pairs above threshold
        threshold = score_threshold if not loose_mode else score_threshold - 0.10
        if best_score >= threshold and best_match:
            pair = {
                'canonical_key': pm_feat['canonical_key'],
                'pm_market_id': pm_feat['contract_id'],
                'kalshi_market_id': best_match['contract_id'],
                'score': best_score,
                'pm_title': pm_feat['title'],
                'kalshi_title': best_match['title'],
                'market_type': pm_feat['market_type'],
                'office': pm_feat.get('office'),
                'year': pm_feat.get('year'),
                'jurisdiction': pm_feat.get('jurisdiction'),
                'persons': ','.join(pm_feat.get('persons', [])),
            }
            pairs.append(pair)
    
    print(f"\nFound {len(pairs)} pairs with score >= {threshold:.2f}")
    
    if pairs:
        # Save to parquet
        pairs_df = pd.DataFrame(pairs)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        pairs_df.to_parquet(out_path, index=False)
        print(f"Saved pairs to: {out_path}")
        
        # Show summary
        print("\nPair Summary:")
        print(f"  Total pairs: {len(pairs_df)}")
        print(f"  Score range: {pairs_df.score.min():.3f} - {pairs_df.score.max():.3f}")
        print(f"  Market types: {pairs_df.market_type.value_counts().to_dict()}")
    else:
        print("\nNo pairs found. Try using --loose mode or lowering the threshold.")


def main():
    parser = argparse.ArgumentParser(description="Build market pairs")
    parser.add_argument(
        "--data",
        required=True,
        help="Path to quotes parquet file"
    )
    parser.add_argument(
        "--out",
        default="data/pairs.parquet",
        help="Output path for pairs (default: data/pairs.parquet)"
    )
    parser.add_argument(
        "--score",
        type=float,
        default=0.75,
        help="Score threshold (default: 0.75)"
    )
    parser.add_argument(
        "--loose",
        action="store_true",
        help="Use loose matching (threshold - 0.10)"
    )
    
    args = parser.parse_args()
    build_pairs(args.data, args.out, args.score, args.loose)


if __name__ == "__main__":
    main()

