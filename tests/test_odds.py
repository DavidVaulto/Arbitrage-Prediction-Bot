"""Tests for odds calculation module."""

from datetime import datetime

from src.core.odds import (
    calculate_arbitrage_edge,
    calculate_breakeven_probability,
    calculate_expected_pnl,
    calculate_kelly_fraction,
    calculate_liquidity_score,
    calculate_spread_bps,
    is_arbitrage_profitable,
    min_executable_qty,
    normalize_quote_to_probability,
    price_to_probability,
    probability_to_price,
    round_to_tick_size,
)
from src.core.types import ContractSide, Quote, Venue


class TestOddsCalculations:
    """Test odds calculation functions."""

    def test_price_to_probability(self):
        """Test price to probability conversion."""
        # YES contract
        assert price_to_probability(0.6, ContractSide.YES) == 0.6
        assert price_to_probability(0.0, ContractSide.YES) == 0.0
        assert price_to_probability(1.0, ContractSide.YES) == 1.0

        # NO contract
        assert price_to_probability(0.6, ContractSide.NO) == 0.4
        assert price_to_probability(0.0, ContractSide.NO) == 1.0
        assert price_to_probability(1.0, ContractSide.NO) == 0.0

    def test_probability_to_price(self):
        """Test probability to price conversion."""
        # YES contract
        assert probability_to_price(0.6, ContractSide.YES) == 0.6
        assert probability_to_price(0.0, ContractSide.YES) == 0.0
        assert probability_to_price(1.0, ContractSide.YES) == 1.0

        # NO contract
        assert probability_to_price(0.6, ContractSide.NO) == 0.4
        assert probability_to_price(0.0, ContractSide.NO) == 1.0
        assert probability_to_price(1.0, ContractSide.NO) == 0.0

    def test_effective_price(self):
        """Test effective price calculation."""
        # Test with fees and slippage
        price = 0.5
        taker_bps = 25.0  # 0.25%
        slippage_bps = 10.0  # 0.1%
        gas_cost = 0.5
        notional = 100.0

        eff_price = effective_price(price, taker_bps, slippage_bps, gas_cost, notional)

        # Should be higher than original price due to costs
        assert eff_price > price
        assert eff_price == 0.5 + 0.0025 + 0.001 + 0.005  # price + taker + slippage + gas

    def test_calculate_arbitrage_edge(self):
        """Test arbitrage edge calculation."""
        # Test profitable arbitrage
        ask_yes_a = 0.4
        ask_no_b = 0.5
        ask_no_a = 0.6
        ask_yes_b = 0.5

        edge_bps, _, rationale = calculate_arbitrage_edge(
            ask_yes_a, ask_no_b, ask_no_a, ask_yes_b
        )

        # Direction 1: 0.4 + 0.5 = 0.9, edge = 0.1 = 1000bps
        # Direction 2: 0.6 + 0.5 = 1.1, edge = 0 (no arbitrage)
        assert edge_bps == 1000.0
        assert "YES@A+NO@B" in rationale

    def test_min_executable_qty(self):
        """Test minimum executable quantity calculation."""
        qty_yes = 100.0
        qty_no = 150.0
        max_capital = 1000.0
        price_yes = 0.4
        price_no = 0.5

        qty = min_executable_qty(qty_yes, qty_no, max_capital, price_yes, price_no)

        # Should be limited by liquidity (100.0) and capital (1000/0.9 = 1111.11)
        assert qty == 100.0

    def test_is_arbitrage_profitable(self):
        """Test arbitrage profitability check."""
        # Profitable arbitrage
        assert is_arbitrage_profitable(100.0, 50.0, 200.0, 100.0) == True

        # Edge too small
        assert is_arbitrage_profitable(50.0, 100.0, 200.0, 100.0) == False

        # Notional too small
        assert is_arbitrage_profitable(100.0, 50.0, 50.0, 100.0) == False

    def test_calculate_breakeven_probability(self):
        """Test breakeven probability calculation."""
        price_yes = 0.4
        price_no = 0.5
        total_costs = 0.05

        breakeven_prob = calculate_breakeven_probability(price_yes, price_no, total_costs)

        # Should be 1 - (0.4 + 0.5 + 0.05) = 0.05
        assert breakeven_prob == 0.05

    def test_calculate_expected_pnl(self):
        """Test expected PnL calculation."""
        edge_bps = 100.0  # 1%
        notional_usd = 1000.0
        probability = 0.5

        expected_pnl = calculate_expected_pnl(edge_bps, notional_usd, probability)

        # Should be 1000 * 0.01 = 10.0
        assert expected_pnl == 10.0

    def test_calculate_spread_bps(self):
        """Test spread calculation."""
        quote = Quote(
            venue=Venue.POLYMARKET,
            contract_id="test_contract",
            best_bid=0.4,
            best_ask=0.6,
            best_bid_size=100.0,
            best_ask_size=100.0,
            ts=datetime.utcnow(),
        )

        spread_bps = calculate_spread_bps(quote)

        # Should be (0.6 - 0.4) * 10000 = 2000bps
        assert spread_bps == 2000.0

    def test_calculate_liquidity_score(self):
        """Test liquidity score calculation."""
        quote = Quote(
            venue=Venue.POLYMARKET,
            contract_id="test_contract",
            best_bid=0.4,
            best_ask=0.6,
            best_bid_size=100.0,
            best_ask_size=100.0,
            ts=datetime.utcnow(),
        )

        liquidity_score = calculate_liquidity_score(quote)

        # Should be (100 + 100) / 2000 = 0.1
        assert liquidity_score == 0.1

    def test_round_to_tick_size(self):
        """Test price rounding to tick size."""
        price = 0.123456
        tick_size = 0.01

        rounded_price = round_to_tick_size(price, tick_size)

        # Should be 0.12
        assert rounded_price == 0.12

    def test_calculate_kelly_fraction(self):
        """Test Kelly fraction calculation."""
        edge_bps = 100.0  # 1%
        probability = 0.5
        bankroll = 10000.0

        kelly_fraction = calculate_kelly_fraction(edge_bps, probability, bankroll)

        # Should be capped at reasonable maximum
        assert kelly_fraction >= 0.0
        assert kelly_fraction <= 0.25

    def test_normalize_quote_to_probability(self):
        """Test quote normalization to probability."""
        quote = Quote(
            venue=Venue.POLYMARKET,
            contract_id="test_contract",
            best_bid=0.4,
            best_ask=0.6,
            best_bid_size=100.0,
            best_ask_size=100.0,
            ts=datetime.utcnow(),
        )

        prob_yes = normalize_quote_to_probability(quote, ContractSide.YES)
        prob_no = normalize_quote_to_probability(quote, ContractSide.NO)

        # YES probability should be mid price (0.5)
        assert prob_yes == 0.5

        # NO probability should be 1 - mid price (0.5)
        assert prob_no == 0.5


