#!/usr/bin/env python3
"""Backtest CLI for PM Arbitrage Bot."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

def load_data(data_path: str) -> pd.DataFrame:
    """Load quotes data from CSV or Parquet file."""
    data_file = Path(data_path)
    
    if not data_file.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    if data_path.endswith('.parquet'):
        df = pd.read_parquet(data_file)
    elif data_path.endswith('.csv'):
        df = pd.read_csv(data_file)
    else:
        raise ValueError(f"Unsupported file format: {data_path}")
    
    # Ensure timestamp column is datetime
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return df

def simulate_discovery(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Simulate discovery process on historical data."""
    opportunities = []
    
    # Group by timestamp to simulate real-time discovery
    for timestamp, group in df.groupby('timestamp'):
        # Simple arbitrage detection: look for price differences between venues
        venues = group['venue'].unique()
        
        if len(venues) >= 2:
            # Find contracts with same event_id across venues
            for event_id in group['event_id'].unique():
                event_data = group[group['event_id'] == event_id]
                
                if len(event_data) >= 2:
                    # Calculate potential arbitrage
                    prices = event_data['mid_price'].values
                    if len(prices) >= 2:
                        min_price = min(prices)
                        max_price = max(prices)
                        edge_bps = (max_price - min_price) * 10000
                        
                        if edge_bps > 50:  # Minimum edge threshold
                            opportunities.append({
                                'timestamp': timestamp,
                                'event_id': event_id,
                                'edge_bps': edge_bps,
                                'min_price': min_price,
                                'max_price': max_price,
                                'venues': list(event_data['venue'].values),
                                'contract_ids': list(event_data['contract_id'].values)
                            })
    
    return opportunities

def calculate_position_size(
    opportunity: Dict[str, Any],
    kelly_fraction: float,
    bankroll: float,
    max_per_trade: float
) -> float:
    """Calculate position size using Kelly criterion."""
    edge_fraction = opportunity['edge_bps'] / 10000.0
    kelly_size = bankroll * kelly_fraction * edge_fraction
    return min(kelly_size, max_per_trade)

def simulate_execution(
    opportunity: Dict[str, Any],
    position_size: float,
    slippage_bps: float
) -> Dict[str, Any]:
    """Simulate trade execution."""
    # Apply slippage
    slippage_factor = 1 + (slippage_bps / 10000.0)
    
    # Calculate costs
    leg_a_cost = position_size * opportunity['min_price'] * slippage_factor
    leg_b_cost = position_size * (1 - opportunity['max_price']) * slippage_factor
    
    total_cost = leg_a_cost + leg_b_cost
    expected_payout = position_size  # Guaranteed $1 payout
    
    # Calculate PnL
    pnl = expected_payout - total_cost
    
    return {
        'timestamp': opportunity['timestamp'],
        'event_id': opportunity['event_id'],
        'position_size': position_size,
        'total_cost': total_cost,
        'expected_payout': expected_payout,
        'pnl': pnl,
        'edge_bps': opportunity['edge_bps']
    }

def calculate_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate backtest metrics."""
    if not trades:
        return {
            'total_trades': 0,
            'total_pnl': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'avg_trade_pnl': 0.0
        }
    
    pnls = [trade['pnl'] for trade in trades]
    total_pnl = sum(pnls)
    
    # Calculate Sharpe ratio (simplified)
    if len(pnls) > 1:
        mean_pnl = sum(pnls) / len(pnls)
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_dev = variance ** 0.5
        sharpe_ratio = mean_pnl / std_dev if std_dev > 0 else 0
    else:
        sharpe_ratio = 0
    
    # Calculate max drawdown
    cumulative_pnl = []
    running_total = 0
    for pnl in pnls:
        running_total += pnl
        cumulative_pnl.append(running_total)
    
    max_drawdown = 0
    peak = 0
    for pnl in cumulative_pnl:
        if pnl > peak:
            peak = pnl
        drawdown = peak - pnl
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    # Calculate win rate
    winning_trades = sum(1 for pnl in pnls if pnl > 0)
    win_rate = winning_trades / len(pnls) if pnls else 0
    
    return {
        'total_trades': len(trades),
        'total_pnl': total_pnl,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'avg_trade_pnl': total_pnl / len(trades) if trades else 0
    }

def save_results(
    trades: List[Dict[str, Any]],
    equity_curve: List[Dict[str, Any]],
    timestamp: str
) -> None:
    """Save results to CSV files in artifacts/ folder."""
    artifacts_dir = Path('artifacts')
    artifacts_dir.mkdir(exist_ok=True)
    
    # Save trades
    trades_df = pd.DataFrame(trades)
    trades_file = artifacts_dir / f'trades_{timestamp}.csv'
    trades_df.to_csv(trades_file, index=False)
    print(f"Saved trades to: {trades_file}")
    
    # Save equity curve
    equity_df = pd.DataFrame(equity_curve)
    equity_file = artifacts_dir / f'equity_{timestamp}.csv'
    equity_df.to_csv(equity_file, index=False)
    print(f"Saved equity curve to: {equity_file}")

def run_backtest(
    data_path: str,
    start_date: str,
    end_date: str,
    min_edge_bps: float,
    slippage_bps: float,
    kelly_fraction: float
) -> Dict[str, Any]:
    """Run the backtest."""
    print(f"Loading data from: {data_path}")
    df = load_data(data_path)
    
    # Filter by date range
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    
    if 'timestamp' in df.columns:
        # Ensure both timestamps are timezone-aware
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        
        if start_dt.tz is None:
            start_dt = start_dt.tz_localize('UTC')
        if end_dt.tz is None:
            end_dt = end_dt.tz_localize('UTC')
        
        df = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)]
    
    print(f"Data points: {len(df)}")
    
    # Print venue statistics
    if 'venue' in df.columns:
        unique_venues = df['venue'].nunique()
        venue_counts = df['venue'].value_counts().to_dict()
        print(f"Unique venues: {unique_venues}")
        for venue, count in venue_counts.items():
            print(f"  {venue}: {count} quotes")
    
    # Simulate discovery
    print("Simulating discovery...")
    opportunities = simulate_discovery(df)
    print(f"Found {len(opportunities)} opportunities")
    
    # Filter by minimum edge
    opportunities = [opp for opp in opportunities if opp['edge_bps'] >= min_edge_bps]
    print(f"Opportunities after edge filter: {len(opportunities)}")
    
    # Simulate trading
    print("Simulating trades...")
    trades = []
    bankroll = 10000.0  # Starting bankroll
    max_per_trade = 1000.0  # Max per trade
    
    for opportunity in opportunities:
        position_size = calculate_position_size(opportunity, kelly_fraction, bankroll, max_per_trade)
        if position_size > 0:
            trade = simulate_execution(opportunity, position_size, slippage_bps)
            trades.append(trade)
    
    # Calculate equity curve
    equity_curve = []
    running_pnl = 0
    for trade in trades:
        running_pnl += trade['pnl']
        equity_curve.append({
            'timestamp': trade['timestamp'],
            'cumulative_pnl': running_pnl,
            'trade_pnl': trade['pnl']
        })
    
    # Calculate metrics
    metrics = calculate_metrics(trades)
    
    return {
        'backtest_summary': metrics,
        'trades': trades,
        'equity_curve': equity_curve
    }

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PM Arbitrage Bot Backtest")
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to quotes data file (CSV or Parquet)"
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--min-edge-bps",
        type=float,
        default=50.0,
        help="Minimum edge in basis points (default: 50)"
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=25.0,
        help="Slippage in basis points (default: 25)"
    )
    parser.add_argument(
        "--kelly-fraction",
        type=float,
        default=0.25,
        help="Kelly fraction for position sizing (default: 0.25)"
    )
    
    args = parser.parse_args()
    
    try:
        # Run backtest
        results = run_backtest(
            args.data,
            args.start,
            args.end,
            args.min_edge_bps,
            args.slippage_bps,
            args.kelly_fraction
        )
        
        # Print JSON summary
        print("\n=== BACKTEST RESULTS ===")
        print(json.dumps(results['backtest_summary'], indent=2))
        
        # Save results
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        save_results(results['trades'], results['equity_curve'], timestamp)
        
    except Exception as e:
        print(f"Backtest failed: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
