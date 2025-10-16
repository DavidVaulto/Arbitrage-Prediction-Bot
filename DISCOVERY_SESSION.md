# Live Discovery Session - October 16, 2025

## Session Details

**Start Time:** 13:00:24  
**Duration:** 30 minutes  
**Data File:** `data/discovery_20251016_130024.parquet`  
**Process PIDs:** Discovery=7757, Monitor=7933

## Setup

### Discovery Process
```bash
python3 scripts/run_discovery.py \
  --poll-ms 5000 \
  --record data/discovery_20251016_130024.parquet
```

- Polling interval: 5 seconds
- Collects from Kalshi and Polymarket public APIs
- Saves to Parquet format for efficient analysis

### Monitor Process
```bash
python3 scripts/monitor_and_analyze.py \
  --data-file data/discovery_20251016_130024.parquet \
  --duration 30
```

- Monitors progress every 60 seconds
- Automatically analyzes data after 30 minutes
- Reports arbitrage opportunities

## Data Collection

### Status (2 minutes in)
- **Rows Collected:** 2,300 quotes
- **File Size:** 41.2 KB
- **Collection Rate:** ~1,069 quotes/minute
- **Estimated Total:** ~32,000 quotes

### Markets
| Venue | Markets | Quotes |
|-------|---------|--------|
| Kalshi | 160 | 1,150 |
| Polymarket | 50 | 1,150 |

### Sample Markets
- Bitcoin price targets ($50K, $20K by Dec 2025)
- Ethereum price targets ($10K, $8K, $7K by Dec 31)
- NFL game outcomes and player props
- Political prediction markets
- Economic indicators

## Analysis Pipeline

The monitoring script will automatically:

1. **Map Markets to Canonical Events**
   - Use Polymarket and Kalshi mappers
   - Apply deterministic event ID matching
   - Track mapping coverage

2. **Find Cross-Venue Pairs**
   - Group by canonical `event_id`
   - Align quotes in 5-second buckets
   - Match same events across venues

3. **Calculate Arbitrage Edges**
   - Strategy 1: Buy YES@PM + Buy NO@Kalshi
   - Strategy 2: Buy NO@PM + Buy YES@Kalshi
   - Include venue fees (PM: 25bps, Kalshi: 30bps)
   - Calculate net edge in basis points

4. **Filter Opportunities**
   - Minimum edge: 50 bps
   - Account for slippage
   - Report top opportunities

## Expected Output

After 30 minutes, the analysis will produce:

- **Arbitrage Opportunities CSV** with:
  - Event ID and title
  - Edge in basis points
  - Strategy (which venue/side to trade)
  - Bid/ask prices on each venue
  - Timestamp

- **Summary Statistics:**
  - Total opportunities found
  - Average and maximum edge
  - Unique events with arbitrage
  - Mapping coverage rate

## Monitoring Commands

```bash
# Check discovery progress
tail -f discovery_20251016_130024.log

# Check monitor progress  
tail -f monitor.log

# View current data
python3 -c "import pandas as pd; df = pd.read_parquet('data/discovery_20251016_130024.parquet'); print(df.tail())"

# Kill processes if needed
kill $(cat discovery.pid)
```

## Technical Implementation

### Event Mapping
Uses the deterministic event registry system:
- Maps venue-specific titles to canonical event IDs
- Format: `TYPE:SCOPE:DESCRIPTOR:DATE:OUTCOME`
- Examples:
  - `CRYPTO:GLOBAL:BTC_TARGET:50000:2025-12-31`
  - `CRYPTO:GLOBAL:ETH_TARGET:10000:2025-12-31`

### Arbitrage Detection
Exploits cross-venue price discrepancies:

```
YES@PM + NO@Kalshi = 1.0 (perfect hedge if same event)

If: PM_ask_yes + Kalshi_ask_no < 1.0 - fees
Then: Arbitrage opportunity exists

Edge = (1.0 - total_cost_with_fees) * 10,000 bps
```

### Data Schema
```
timestamp: datetime with timezone
venue: "kalshi" | "polymarket"  
contract_id: venue-specific ID
title: market question
best_bid_yes, best_ask_yes: YES side prices [0,1]
best_bid_no, best_ask_no: NO side prices [0,1]
best_bid_size, best_ask_size: liquidity
expires_at: market close time
event_id: canonical event (added during analysis)
```

## Results Location

After completion:
- **Raw Data:** `data/discovery_20251016_130024.parquet`
- **Opportunities:** `data/arbitrage_opportunities_discovery_20251016_130024.csv`
- **Logs:** `monitor.log`, `discovery_20251016_130024.log`

## Next Steps (Post-Analysis)

1. Review top arbitrage opportunities
2. Validate event mappings for accuracy
3. Add manual overrides for unmapped markets
4. Adjust minimum edge threshold if needed
5. Run backtest with collected data
6. Calculate expected PnL for strategies

---

**Status:** 🟢 RUNNING  
**ETA:** ~28 minutes remaining  
**Last Updated:** 13:02 (2 min elapsed)

