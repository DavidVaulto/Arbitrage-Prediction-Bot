#!/usr/bin/env python3
"""Monitor discovery and run arbitrage analysis when complete."""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.core.event_registry import EventRegistry
from src.core.venue_mappers import KalshiMapper, PolymarketMapper


def monitor_discovery(data_file: Path, duration_minutes: int = 30):
    """Monitor discovery progress."""
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    print(f"🔍 Monitoring discovery session:")
    print(f"   Start: {start_time.strftime('%H:%M:%S')}")
    print(f"   End: {end_time.strftime('%H:%M:%S')} ({duration_minutes} min)")
    print(f"   Data file: {data_file}")
    print()
    
    last_row_count = 0
    check_interval = 60  # Check every minute
    
    while datetime.now() < end_time:
        try:
            if data_file.exists():
                df = pd.read_parquet(data_file)
                rows = len(df)
                new_rows = rows - last_row_count
                
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                remaining = (end_time - datetime.now()).total_seconds() / 60
                
                print(f"⏱️  [{elapsed:.1f}min] Rows: {rows:,} (+{new_rows}) | Remaining: {remaining:.1f}min")
                
                if rows > 0:
                    venues = df['venue'].value_counts().to_dict()
                    markets = df.groupby('venue')['contract_id'].nunique().to_dict()
                    print(f"   Venues: {venues}")
                    print(f"   Unique markets: {markets}")
                
                last_row_count = rows
            else:
                print(f"⏳ Waiting for data file to be created...")
            
        except Exception as e:
            print(f"⚠️  Error reading data: {e}")
        
        time.sleep(check_interval)
    
    print(f"\n✅ Discovery session complete!")
    print(f"   Total rows collected: {last_row_count:,}")
    return data_file


def analyze_arbitrage(data_file: Path):
    """Analyze collected data for arbitrage opportunities."""
    print(f"\n🔬 Analyzing data for arbitrage opportunities...")
    print(f"   Loading: {data_file}")
    
    # Load data
    df = pd.read_parquet(data_file)
    print(f"   Loaded {len(df):,} rows")
    
    # Initialize registry and mappers
    registry = EventRegistry(
        events_file=Path("data/canonical_events.csv"),
        mappings_file=Path("data/venue_mappings.csv"),
    )
    
    pm_mapper = PolymarketMapper(registry)
    kalshi_mapper = KalshiMapper(registry)
    
    # Map markets to canonical events
    print(f"\n📍 Mapping markets to canonical events...")
    
    mapped_data = []
    mapping_stats = {"mapped": 0, "abstained": 0, "total": 0}
    
    for idx, row in df.iterrows():
        mapping_stats["total"] += 1
        
        venue = row['venue']
        contract_id = row['contract_id']
        title = row['title']
        
        # Select appropriate mapper
        mapper = pm_mapper if venue == 'polymarket' else kalshi_mapper
        
        # Try to map
        event_id = mapper.map_to_event_id(
            market_id=contract_id,
            title=title,
            description="",
            metadata={"close_time": row.get('expires_at')},
        )
        
        if event_id:
            mapping_stats["mapped"] += 1
            row_dict = row.to_dict()
            row_dict['event_id'] = event_id
            mapped_data.append(row_dict)
        else:
            mapping_stats["abstained"] += 1
    
    print(f"   Total markets: {mapping_stats['total']:,}")
    print(f"   Mapped: {mapping_stats['mapped']:,} ({mapping_stats['mapped']/mapping_stats['total']*100:.1f}%)")
    print(f"   Abstained: {mapping_stats['abstained']:,}")
    
    if not mapped_data:
        print(f"\n⚠️  No markets were successfully mapped. Cannot find arbitrage.")
        return
    
    # Create DataFrame with mapped data
    mapped_df = pd.DataFrame(mapped_data)
    
    # Find cross-venue opportunities
    print(f"\n🔍 Searching for cross-venue arbitrage opportunities...")
    
    # Group by event_id and timestamp bucket (5-second buckets)
    mapped_df['ts_bucket'] = pd.to_datetime(mapped_df['timestamp']).dt.floor('5S')
    
    opportunities = []
    
    for (event_id, ts_bucket), group in mapped_df.groupby(['event_id', 'ts_bucket']):
        venues = group['venue'].unique()
        
        if len(venues) < 2:
            continue  # Need both venues
        
        # Get quotes from each venue
        pm_quote = group[group['venue'] == 'polymarket'].iloc[0] if 'polymarket' in venues else None
        kalshi_quote = group[group['venue'] == 'kalshi'].iloc[0] if 'kalshi' in venues else None
        
        if pm_quote is None or kalshi_quote is None:
            continue
        
        # Calculate arbitrage edges
        # Strategy 1: Buy YES@PM, Buy NO@Kalshi
        pm_ask_yes = pm_quote['best_ask_yes']
        kalshi_ask_no = kalshi_quote['best_ask_no']
        
        # Include fees (approximate)
        pm_fee = 0.0025  # 25bps
        kalshi_fee = 0.003  # 30bps
        
        total_cost_1 = pm_ask_yes * (1 + pm_fee) + kalshi_ask_no * (1 + kalshi_fee)
        edge_1 = (1.0 - total_cost_1) * 10000  # in bps
        
        # Strategy 2: Buy NO@PM, Buy YES@Kalshi  
        pm_ask_no = pm_quote['best_ask_no']
        kalshi_ask_yes = kalshi_quote['best_ask_yes']
        
        total_cost_2 = pm_ask_no * (1 + pm_fee) + kalshi_ask_yes * (1 + kalshi_fee)
        edge_2 = (1.0 - total_cost_2) * 10000  # in bps
        
        # Record best opportunity
        if edge_1 > 50 or edge_2 > 50:  # At least 50bps edge
            best_edge = max(edge_1, edge_2)
            strategy = "YES@PM+NO@Kalshi" if edge_1 > edge_2 else "NO@PM+YES@Kalshi"
            
            opportunities.append({
                'timestamp': ts_bucket,
                'event_id': event_id,
                'title': pm_quote['title'],
                'edge_bps': best_edge,
                'strategy': strategy,
                'pm_bid_yes': pm_quote['best_bid_yes'],
                'pm_ask_yes': pm_quote['best_ask_yes'],
                'kalshi_bid_yes': kalshi_quote['best_bid_yes'],
                'kalshi_ask_yes': kalshi_quote['best_ask_yes'],
            })
    
    print(f"   Cross-venue pairs checked: {len(mapped_df.groupby(['event_id', 'ts_bucket']))}")
    print(f"   Arbitrage opportunities found: {len(opportunities)}")
    
    if opportunities:
        opp_df = pd.DataFrame(opportunities)
        opp_df = opp_df.sort_values('edge_bps', ascending=False)
        
        print(f"\n🎯 Top Arbitrage Opportunities:")
        print("=" * 100)
        
        for idx, opp in opp_df.head(10).iterrows():
            print(f"\n{idx+1}. {opp['event_id']}")
            print(f"   Title: {opp['title'][:80]}...")
            print(f"   Edge: {opp['edge_bps']:.1f} bps")
            print(f"   Strategy: {opp['strategy']}")
            print(f"   PM  YES: bid={opp['pm_bid_yes']:.3f}, ask={opp['pm_ask_yes']:.3f}")
            print(f"   KSH YES: bid={opp['kalshi_bid_yes']:.3f}, ask={opp['kalshi_ask_yes']:.3f}")
        
        # Save results
        output_file = data_file.parent / f"arbitrage_opportunities_{data_file.stem}.csv"
        opp_df.to_csv(output_file, index=False)
        print(f"\n💾 Saved opportunities to: {output_file}")
        
        # Summary statistics
        print(f"\n📊 Summary Statistics:")
        print(f"   Total opportunities: {len(opp_df)}")
        print(f"   Average edge: {opp_df['edge_bps'].mean():.1f} bps")
        print(f"   Max edge: {opp_df['edge_bps'].max():.1f} bps")
        print(f"   Unique events: {opp_df['event_id'].nunique()}")
    else:
        print(f"\n💡 No arbitrage opportunities found with edge > 50 bps")
        print(f"   This could mean:")
        print(f"   - Markets are efficiently priced")
        print(f"   - Fees consume potential edges")
        print(f"   - Need longer collection period")
        print(f"   - Try lower edge threshold")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor discovery and analyze for arbitrage")
    parser.add_argument("--data-file", required=True, help="Path to discovery data file")
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes")
    parser.add_argument("--skip-wait", action="store_true", help="Skip waiting, analyze immediately")
    
    args = parser.parse_args()
    
    data_file = Path(args.data_file)
    
    if not args.skip_wait:
        # Monitor discovery progress
        monitor_discovery(data_file, args.duration)
    
    # Analyze for arbitrage
    if data_file.exists():
        analyze_arbitrage(data_file)
    else:
        print(f"❌ Data file not found: {data_file}")


if __name__ == "__main__":
    main()

