"""Backtest CLI script for historical data analysis."""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from ..core.backtest import BacktestEngine


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run backtest on historical data")

    parser.add_argument(
        "--data",
        required=True,
        help="Path to historical data file (CSV or Parquet)"
    )

    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--output",
        help="Output file for results (JSON)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )

    return parser.parse_args()


async def main():
    """Main backtest function."""
    args = parse_args()

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        sys.exit(1)

    # Check data file exists
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Data file not found: {args.data}")
        sys.exit(1)

    print("Starting backtest...")
    print(f"Data file: {args.data}")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")

    # Initialize backtest engine
    backtest_engine = BacktestEngine()

    try:
        # Load historical data
        print("Loading historical data...")
        backtest_engine.load_historical_data(
            data_file=args.data,
            start_date=start_date,
            end_date=end_date,
        )

        # Run backtest
        print("Running backtest...")
        result = backtest_engine.run_backtest()

        # Print results
        print("\n" + "="*50)
        print("BACKTEST RESULTS")
        print("="*50)
        print(f"Period: {result.start_date} to {result.end_date}")
        print(f"Total trades: {result.total_trades}")
        print(f"Successful trades: {result.successful_trades}")
        print(f"Win rate: {result.win_rate:.1f}%")
        print(f"Total PnL: ${result.total_pnl:.2f}")
        print(f"Max drawdown: ${result.max_drawdown:.2f}")
        print(f"Sharpe ratio: {result.sharpe_ratio:.2f}")
        print(f"Average edge: {result.avg_edge_bps:.1f}bps")
        print(f"Total fees: ${result.total_fees:.2f}")
        print("="*50)

        # Save results if output file specified
        if args.output:
            import json
            output_data = {
                "start_date": result.start_date.isoformat(),
                "end_date": result.end_date.isoformat(),
                "total_trades": result.total_trades,
                "successful_trades": result.successful_trades,
                "total_pnl": result.total_pnl,
                "max_drawdown": result.max_drawdown,
                "sharpe_ratio": result.sharpe_ratio,
                "win_rate": result.win_rate,
                "avg_edge_bps": result.avg_edge_bps,
                "total_fees": result.total_fees,
            }

            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)

            print(f"Results saved to: {args.output}")

    except Exception as e:
        print(f"Error in backtest: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


