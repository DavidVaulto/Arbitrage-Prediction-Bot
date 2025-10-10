# Cross-Exchange Prediction Market Arbitrage Bot

A production-grade arbitrage engine that scans multiple prediction markets (Polymarket and Kalshi) for binary events, detects price discrepancies, and executes market-neutral trades automatically.

## Features

- **Multi-Venue Support**: Polymarket and Kalshi integration
- **Event Matching**: Automatic cross-venue event identification
- **Arbitrage Detection**: Real-time opportunity discovery
- **Risk Management**: Comprehensive risk controls and circuit breakers
- **Multiple Modes**: Paper trading, live trading, and backtesting
- **Position Sizing**: Kelly fraction and risk-based sizing
- **Atomic Execution**: Semi-atomic order placement with hedging
- **Portfolio Tracking**: Real-time PnL and position management
- **Observability**: Structured logging and metrics

## Quick Start – No Fuss

Get up and running in minutes with these simple commands:

```bash
# Activate virtual environment
source venv/bin/activate  # Windows: venv\Scripts\activate

# Run health check
make doctor

# Start discovery with data recording
make discovery-record
```

The health check will verify your Python version, environment configuration, and module imports. The discovery mode will start collecting market data and save it to `data/quotes_sample.parquet` for backtesting.

**Note**: For offline testing without real API connections, set `USE_STUBS=true` in your `.env` file to use stub connectors instead of real market data.

## Kalshi Public Data Mode

The system supports fetching Kalshi market data through **public endpoints** without requiring API authentication. This allows you to monitor markets and collect data for backtesting without setting up API keys.

### Configuration

In your `.env` file:

```bash
# Enable Kalshi public API (default: true)
KALSHI_USE_PUBLIC=true

# Kalshi public API base URL
KALSHI_PUBLIC_BASE=https://api.elections.kalshi.com/trade-api/v2
```

When `KALSHI_USE_PUBLIC=true`:
- No API keys required for Kalshi
- Read-only access to market data
- Fetches live quotes, orderbook data, and market information
- Prices automatically normalized from cents (0-100) to probabilities (0-1)

When `KALSHI_USE_PUBLIC=false`:
- Requires `KALSHI_API_KEY` and `KALSHI_API_SECRET`
- Enables authenticated endpoints for trading
- Falls back to the trading API

### Usage

The discovery script automatically uses the public API when enabled:

```bash
# Start discovery with Kalshi public data
python -m scripts.run_discovery --poll-ms 1500 --record data/quotes_dual.parquet
```

Output will show:
```json
{
  "msg": "discovery_heartbeat",
  "fetched_polymarket": 0,
  "fetched_kalshi": 50,
  "total_quotes": 50
}
```

For more information on the Kalshi public API, see the [official documentation](https://trading-api.readme.io/reference/getting-started).

## Quick Start

### Prerequisites

- Python 3.11+
- API credentials for Polymarket and/or Kalshi
- Pre-funded balances on trading venues

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd pm-arb
```

2. Install dependencies:
```bash
pip install -e .
```

3. Copy environment template:
```bash
cp env.example .env
```

4. Configure your environment variables in `.env`:
```bash
# Trading Mode: paper, live, backtest
MODE=paper

# API Credentials
POLYMARKET_API_KEY=your_polymarket_api_key
KALSHI_API_KEY=your_kalshi_api_key

# Risk Management
MIN_EDGE_BPS=80
MAX_OPEN_RISK_USD=3000
STARTING_BALANCE_USD=10000
```

### Running the Bot

#### Discovery Mode (No Trading)
```bash
python -m src.scripts.run_discovery
```

#### Paper Trading
```bash
python -m src.scripts.run_paper
```

#### Live Trading (Requires Confirmation)
```bash
CONFIRM_LIVE=true python -m src.scripts.run_live
```

#### Backtesting
```bash
python -m src.scripts.backtest_cli --data data/historical_data.parquet --start 2024-01-01 --end 2024-12-31
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODE` | Trading mode (paper/live/backtest) | `paper` |
| `MIN_EDGE_BPS` | Minimum edge in basis points | `80` |
| `MAX_OPEN_RISK_USD` | Maximum open risk | `3000` |
| `KELLY_FRACTION` | Kelly fraction multiplier | `0.25` |
| `STARTING_BALANCE_USD` | Starting balance for paper trading | `10000` |
| `POLYMARKET_API_KEY` | Polymarket API key | - |
| `KALSHI_API_KEY` | Kalshi API key | - |
| `CONFIRM_LIVE` | Enable live trading | `false` |

### Risk Management

The bot includes comprehensive risk management:

- **Position Limits**: Maximum exposure per event and total
- **Drawdown Protection**: Automatic stop on excessive losses
- **Circuit Breakers**: Pause trading on venue errors or latency
- **Edge Thresholds**: Minimum profitability requirements
- **Slippage Controls**: Maximum acceptable slippage

## Architecture

### Core Components

- **Types**: Canonical data models for contracts, quotes, trades
- **Config**: Pydantic-based configuration management
- **Odds**: Price normalization and edge calculations
- **Fees**: Per-venue fee modeling and cost estimation
- **Matcher**: Cross-venue event matching algorithms
- **Discovery**: Real-time opportunity detection
- **Sizing**: Position sizing algorithms (Kelly, fixed, percentage)
- **Risk**: Risk management and circuit breakers
- **Execution**: Atomic order placement and hedging
- **Portfolio**: PnL tracking and position management
- **Persistence**: Database storage with SQLModel

### Connectors

- **Base**: Abstract connector protocol
- **Polymarket**: REST API integration
- **Kalshi**: REST API integration
- **Mock**: Testing and development connector

### Trading Modes

- **Paper**: Simulated trading with real-time data
- **Live**: Real order placement (requires confirmation)
- **Backtest**: Historical data analysis

## API Integration

### Polymarket

- **Data**: REST API for contracts and quotes
- **Trading**: Order placement and management
- **Fees**: Maker/taker fees + gas costs
- **Settlement**: USDC on Polygon

### Kalshi

- **Data**: REST API for markets and quotes
- **Trading**: Order placement and management
- **Fees**: Commission-based pricing
- **Settlement**: USD

## Event Matching

The bot automatically matches events across venues using:

1. **Title Similarity**: Jaro-Winkler and token set ratio
2. **Expiry Proximity**: Date-based matching
3. **Manual Overrides**: CSV-based manual mappings
4. **Confidence Scoring**: Weighted combination of factors

## Arbitrage Detection

Opportunities are detected by:

1. **Cross-Venue Comparison**: YES@A + NO@B vs NO@A + YES@B
2. **Cost Inclusion**: Fees, slippage, and gas costs
3. **Liquidity Checks**: Minimum size requirements
4. **Edge Calculation**: (1 - sum_of_prices) * 10000

## Position Sizing

Multiple sizing strategies:

- **Kelly Fraction**: Optimal sizing based on edge
- **Fixed Size**: Constant position size
- **Percentage**: Percentage of bankroll
- **Risk-Limited**: Capped by risk limits

## Safety Features

### Live Trading Guards

- **Confirmation Required**: `CONFIRM_LIVE=true` environment variable
- **Balance Verification**: Pre-trade balance checks
- **Risk Limits**: Multiple layers of risk controls
- **Circuit Breakers**: Automatic pause on errors

### Error Handling

- **Retry Logic**: Automatic retry with exponential backoff
- **Partial Fill Handling**: Hedging and unwinding
- **Connection Monitoring**: Health checks and reconnection
- **Graceful Degradation**: Fallback to mock connectors

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

## Development

### Project Structure

```
pm-arb/
├── src/
│   ├── core/           # Core arbitrage engine
│   ├── connectors/     # Exchange connectors
│   ├── scripts/        # CLI scripts
│   └── ui/            # Optional dashboard
├── tests/             # Test suite
├── data/              # Historical data
├── docker/            # Docker configuration
└── pyproject.toml     # Project configuration
```

### Adding New Venues

1. Implement `VenueClient` protocol in `connectors/`
2. Add venue to `Venue` enum in `types.py`
3. Update fee models in `config.py`
4. Add connector initialization in scripts

### Adding New Features

1. Follow existing patterns in `core/` modules
2. Add comprehensive tests
3. Update documentation
4. Consider backward compatibility

## Docker Deployment

### Build and Run

```bash
# Build image
docker build -t pm-arb .

# Run paper trading
docker run -e MODE=paper pm-arb

# Run with environment file
docker run --env-file .env pm-arb
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Monitoring and Observability

### Logging

- **Structured Logs**: JSON format for easy parsing
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Context**: Trade IDs, event IDs, venue information

### Metrics

- **Trade Metrics**: Count, success rate, PnL
- **Risk Metrics**: Exposure, drawdown, circuit breakers
- **System Metrics**: Latency, error rates, health status

### Alerts

- **Webhook Integration**: Slack/Discord notifications
- **Threshold Alerts**: Large trades, errors, drawdowns
- **Health Alerts**: Venue connectivity issues

## Legal and Compliance

### Important Disclaimers

- **Not Financial Advice**: This software is for educational purposes
- **Use at Your Own Risk**: Trading involves significant risk
- **Regulatory Compliance**: Ensure compliance with local regulations
- **Venue Terms**: Accept API terms and conditions

### Venue-Specific Considerations

#### Kalshi
- **CFTC Regulated**: Automated trading may require compliance
- **US Eligibility**: Check geographic restrictions
- **API Terms**: Accept automated trading terms

#### Polymarket
- **Crypto-Native**: Ensure jurisdictional compliance
- **Custody Controls**: Implement proper key management
- **Gas Costs**: Account for blockchain transaction fees

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions and support:

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: README and inline docs

## Roadmap

### Version 1.1
- [ ] Additional venues (Manifold, PredictIt)
- [ ] Advanced position sizing
- [ ] Web dashboard
- [ ] Real-time alerts

### Version 1.2
- [ ] Multi-leg arbitrage
- [ ] Options strategies
- [ ] Machine learning features
- [ ] Advanced risk models

---

**⚠️ WARNING: This software is for educational and research purposes only. Trading involves significant financial risk. Use at your own risk and ensure compliance with all applicable regulations.**


north