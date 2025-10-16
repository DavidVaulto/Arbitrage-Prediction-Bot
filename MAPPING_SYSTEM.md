# Event Mapping System

## Overview

This system implements **deterministic event mapping** for cross-venue arbitrage detection, inspired by the [betfairmappings](https://github.com/mberk/betfairmappings) architecture. It maps venue-specific market IDs to canonical event IDs, enabling precise cross-venue matching without fuzzy string matching.

## Architecture

### Core Components

1. **Event Registry** (`src/core/event_registry.py`)
   - Stores canonical events with deterministic IDs
   - Manages venue-to-event mappings
   - Provides persistent storage (CSV-based)

2. **Venue Mappers** (`src/core/venue_mappers.py`)
   - Parse venue-specific market titles
   - Extract canonical features (event type, date, participants)
   - Map to deterministic event IDs
   - **Abstain** if mapping confidence is low (precision over recall)

3. **Discovery Pipeline** (`src/core/discovery.py`)
   - Integrated with event registry
   - Only passes mapped markets downstream
   - Matches by canonical `event_id` (deterministic)

## Canonical Event ID Format

Event IDs follow a deterministic structure:

```
{TYPE}:{SCOPE}:{DESCRIPTOR}:{DATE}:{OUTCOME}
```

### Examples

```
ELECTION:US:PRESIDENT:2028:TRUMP
CRYPTO:GLOBAL:BTC_TARGET:150000:2025-12-31
AWARDS:GLOBAL:OSCARS:BEST_ACTRESS:2026:EMMA_STONE
```

### Benefits

- **Deterministic**: Same event always gets same ID
- **Parseable**: Components are easily extracted
- **Collision-resistant**: Unique structure prevents false matches
- **Version-safe**: No dependency on fuzzy logic

## Venue Mappers

### Polymarket Mapper

Extracts from natural language questions:

```python
"Will Trump win the 2028 Presidential Election?"
→ ELECTION:US:PRESIDENT:2028:TRUMP

"Will Bitcoin reach $150,000 by end of 2025?"
→ CRYPTO:GLOBAL:BTC_TARGET:150000:2025-12-31
```

**Supported patterns:**
- Elections (US Presidential)
- Crypto price targets (BTC, ETH)
- Awards (Oscars, Emmys, Grammys)

### Kalshi Mapper

Handles both ticker format and titles:

```python
"PRES-2028-TRUMP" → ELECTION:US:PRESIDENT:2028:TRUMP
"BTC-150K-2025" → CRYPTO:GLOBAL:BTC_TARGET:150000:2025-12-31
```

**Ticker patterns:**
- `PRES-{YEAR}-{CANDIDATE}`
- `BTC-{PRICE}K-{YEAR}`

### Abstention Strategy

Mappers follow **precision over recall**:
- Return `None` if confidence < 85%
- Skip unmapped markets (don't force matches)
- Favor manual overrides for edge cases

## Data Layer

### File Structure

```
data/
├── canonical_events.csv      # Master event registry
└── venue_mappings.csv         # Venue-specific mappings
```

### Schema: Canonical Events

| Field | Description | Example |
|-------|-------------|---------|
| `event_id` | Deterministic canonical ID | `ELECTION:US:PRESIDENT:2028:TRUMP` |
| `event_type` | Event category | `ELECTION` |
| `scope` | Geographic scope | `US` |
| `date_close` | Market close date | `2028-11-05T23:59:59` |
| `canonical_units` | Settlement units | `YES/NO` |
| `display_title` | Human-readable title | `Will Trump win 2028?` |
| `resolution_source` | Truth source | `official_results` |
| `aliases` | Alternative names | `TRUMP_2028\|PRES_2028_TRUMP` |

### Schema: Venue Mappings

| Field | Description | Example |
|-------|-------------|---------|
| `venue` | Venue name | `polymarket` |
| `market_id` | Venue's native ID | `clzj4qmgq000108jq1kg74f58` |
| `event_id` | Canonical event ID | `ELECTION:US:PRESIDENT:2028:TRUMP` |
| `title_raw` | Original market title | `Will Trump win 2028?` |
| `confidence` | Mapping confidence | `1.0` |
| `mapping_method` | How mapped | `deterministic` |

## CLI Tools

### 1. Manage Mappings (`scripts/manage_mappings.py`)

```bash
# View statistics
python scripts/manage_mappings.py stats

# List all canonical events
python scripts/manage_mappings.py list-events

# List venue mappings
python scripts/manage_mappings.py list-mappings --venue polymarket

# Add a new canonical event
python scripts/manage_mappings.py add-event \
  ELECTION US PRESIDENT 2028 HARRIS \
  --close-date 2028-11-05 \
  --title "Will Harris win 2028?"

# Add manual override
python scripts/manage_mappings.py add-override \
  polymarket \
  clzj4qmgq000108jq1kg74f58 \
  ELECTION:US:PRESIDENT:2028:TRUMP \
  --title "Trump 2028?"

# Test mapper on a title
python scripts/manage_mappings.py test-mapper \
  polymarket \
  "Will Trump win the 2028 Presidential Election?"
```

### 2. Coverage Report (`scripts/mapping_coverage_report.py`)

```bash
# Analyze mapping coverage from historical data
python scripts/mapping_coverage_report.py \
  --polymarket-data data/quotes_sample.parquet \
  --kalshi-data data/kalshi_sample.parquet \
  --output reports/coverage_$(date +%Y%m%d).txt
```

**Output:**
- Overall coverage percentage
- Coverage by venue
- Coverage by event type
- Cross-venue mapping count
- Unmapped market samples
- Recommendations

## Usage in Discovery Pipeline

### Basic Setup

```python
from src.core.event_registry import EventRegistry
from src.core.discovery import DiscoveryEngine
from src.core.fees import FeeCalculator
from src.core.matcher import EventMatcher

# Initialize registry
registry = EventRegistry(
    events_file="data/canonical_events.csv",
    mappings_file="data/venue_mappings.csv",
)

# Create discovery engine with deterministic mapping
engine = DiscoveryEngine(
    fee_calculator=FeeCalculator(),
    event_matcher=EventMatcher(),  # Fallback only
    event_registry=registry,
    use_deterministic_mapping=True,  # Enable new system
)

# Discover opportunities
opportunities = await engine.discover_opportunities(connectors)
```

### Statistics

```python
stats = engine.get_discovery_stats()

print(f"Total contracts: {stats['total_contracts']}")
print(f"Mapped: {stats['mapping_stats']['mapped_markets']}")
print(f"Abstained: {stats['mapping_stats']['abstained_markets']}")

# Registry coverage
print(f"Cross-venue events: {stats['registry_stats']['events_with_cross_venue']}")
```

## Quality Gates

### 1. Precision Over Recall
- Mapper returns `None` if uncertain
- Only high-confidence mappings (≥85%) are stored
- Manual review for abstained markets

### 2. Deterministic Matching
- No fuzzy string matching in production
- Exact `event_id` matching only
- Consistent results across runs

### 3. Unit Tests
Run comprehensive tests:

```bash
pytest tests/test_event_mapping.py -v
```

Tests cover:
- Event ID generation
- Venue-specific parsing
- Cross-venue consistency
- Registry persistence
- Edge cases

### 4. Canary Mode
Monitor new mappings:

```bash
# Test mapper before deploying
python scripts/manage_mappings.py test-mapper polymarket \
  "Will Trump win the 2028 Presidential Election?"
```

## Performance Optimization

### 1. Indexed Lookups
- Registry uses `dict` for O(1) lookups
- Keyed by `venue:market_id` and `event_id`

### 2. Memory Caching
```python
# Optional: Use Redis for distributed caching
from redis import Redis

cache = Redis(host='localhost', port=6379)

def get_event_id_cached(venue: str, market_id: str) -> str | None:
    key = f"mapping:{venue}:{market_id}"
    cached = cache.get(key)
    if cached:
        return cached.decode()
    
    event_id = registry.get_event_id(venue, market_id)
    if event_id:
        cache.setex(key, 3600, event_id)  # Cache 1 hour
    return event_id
```

### 3. Batch Processing
Process markets in batches:

```python
# Map contracts in batch
for contract in contracts:
    event_id = mapper.map_to_event_id(
        market_id=contract.normalized_event_id,
        title=contract.event_key,
        description="",
        metadata={"close_time": contract.expires_at},
    )
    if event_id:
        contract.normalized_event_id = event_id
```

## Workflow

### 1. Initial Setup
1. Create canonical events for known markets
2. Add manual overrides for critical markets
3. Run coverage analysis on historical data

### 2. Production Operation
1. Discovery engine maps new markets automatically
2. Abstained markets are logged for review
3. Add overrides for important unmapped markets

### 3. Continuous Improvement
1. Run weekly coverage reports
2. Review unmapped samples
3. Extend mapper patterns as needed
4. Add manual overrides for edge cases

## Extending the System

### Add New Event Type

1. **Update EventType enum:**
```python
class EventType(str, Enum):
    ELECTION = "ELECTION"
    CRYPTO = "CRYPTO"
    AWARDS = "AWARDS"
    SPORTS = "SPORTS"  # New
```

2. **Add parsing logic to mapper:**
```python
def _parse_sports_event(self, text: str, metadata: dict) -> str | None:
    # Pattern: SPORTS:{LEAGUE}:{EVENT}:{YEAR}:{TEAM}
    if "SUPER BOWL" in text:
        # Extract year, teams, etc.
        return CanonicalEvent.build_event_id(
            "SPORTS", "US", "NFL", "SUPER_BOWL", year, team
        )
    return None
```

3. **Add test cases:**
```python
def test_sports_super_bowl():
    event_id = mapper.map_to_event_id(
        market_id="test",
        title="Will the Chiefs win Super Bowl 2025?",
    )
    assert "SPORTS" in event_id
```

### Add New Venue

1. **Create mapper class:**
```python
class NewVenueMapper(BaseVenueMapper):
    def __init__(self, registry: EventRegistry):
        super().__init__(registry)
        self.venue_name = "newvenue"
    
    def map_to_event_id(self, market_id, title, description="", metadata=None):
        # Implement venue-specific parsing
        pass
```

2. **Register in discovery:**
```python
self.venue_mappers = {
    Venue.POLYMARKET: PolymarketMapper(self.event_registry),
    Venue.KALSHI: KalshiMapper(self.event_registry),
    Venue.NEWVENUE: NewVenueMapper(self.event_registry),
}
```

## Comparison: Before vs After

### Before (Fuzzy Matching)
```python
# Old: Fuzzy string similarity
similarity = SequenceMatcher(None, title_a, title_b).ratio()
if similarity > 0.7:  # Arbitrary threshold
    return True  # Maybe same event?
```

**Problems:**
- Non-deterministic
- False positives
- Maintenance nightmare
- No cross-venue guarantees

### After (Deterministic Mapping)
```python
# New: Canonical event ID
event_id_a = mapper_a.map_to_event_id(market_a)
event_id_b = mapper_b.map_to_event_id(market_b)

if event_id_a == event_id_b:  # Exact match
    return True  # Definitely same event
```

**Benefits:**
- Deterministic
- Zero false positives
- Easy to maintain
- Cross-venue guaranteed

## Troubleshooting

### Low Coverage (<50%)

**Causes:**
- Mapper patterns too strict
- Many markets don't match known types

**Solutions:**
1. Review unmapped samples: `python scripts/mapping_coverage_report.py`
2. Add more patterns to mappers
3. Create manual overrides for common markets

### Incorrect Mappings

**Causes:**
- Parser extracted wrong information
- Event ID collision

**Solutions:**
1. Add manual override: `manage_mappings.py add-override`
2. Fix parser logic and add test case
3. Update canonical event ID structure if needed

### Missing Cross-Venue Matches

**Causes:**
- Different parsing results across venues
- Markets not mapped on one venue

**Solutions:**
1. Check both venue mappers produce same `event_id`
2. Add test case for cross-venue consistency
3. Add manual override if parser can't handle

## References

- [betfairmappings](https://github.com/mberk/betfairmappings) - Original inspiration for ID mapping
- Event Registry pattern for deterministic identification
- Precision-over-recall approach to mapping quality

