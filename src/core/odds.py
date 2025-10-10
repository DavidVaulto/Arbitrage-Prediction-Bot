"""Odds calculation and arbitrage edge detection."""

from __future__ import annotations

from .types import ContractSide, Quote


def price_to_probability(price: float, side: ContractSide) -> float:
    """Convert contract price to implied probability.
    
    For YES contracts: probability = price
    For NO contracts: probability = 1 - price
    
    Args:
        price: Contract price (0-1)
        side: Contract side (YES or NO)
        
    Returns:
        Implied probability (0-1)
    """
    if side == ContractSide.YES:
        return price
    elif side == ContractSide.NO:
        return 1.0 - price
    else:
        raise ValueError(f"Invalid contract side: {side}")


def probability_to_price(prob: float, side: ContractSide) -> float:
    """Convert probability to contract price.
    
    Args:
        prob: Probability (0-1)
        side: Contract side (YES or NO)
        
    Returns:
        Contract price (0-1)
    """
    if side == ContractSide.YES:
        return prob
    elif side == ContractSide.NO:
        return 1.0 - prob
    else:
        raise ValueError(f"Invalid contract side: {side}")


def effective_price(
    price: float,
    taker_bps: float,
    slippage_bps: float = 0.0,
    gas_cost_usd: float = 0.0,
    notional_usd: float = 1.0,
) -> float:
    """Calculate effective price including fees and slippage.
    
    Args:
        price: Base contract price
        taker_bps: Taker fee in basis points
        slippage_bps: Estimated slippage in basis points
        gas_cost_usd: Gas cost in USD
        notional_usd: Trade notional in USD
        
    Returns:
        Effective price including all costs
    """
    # Convert basis points to decimal
    taker_fee = taker_bps / 10000.0
    slippage = slippage_bps / 10000.0

    # Calculate total cost as percentage of notional
    total_cost_pct = taker_fee + slippage + (gas_cost_usd / notional_usd)

    # Adjust price for costs
    if price > 0.5:  # Buying (paying ask)
        return price + total_cost_pct
    else:  # Selling (receiving bid)
        return price - total_cost_pct


def calculate_arbitrage_edge(
    ask_yes_a: float,
    ask_no_b: float,
    ask_no_a: float,
    ask_yes_b: float,
    total_costs: float = 0.0,
) -> tuple[float, float, str]:
    """Calculate arbitrage edge for both directions.
    
    Args:
        ask_yes_a: Best ask for YES at venue A
        ask_no_b: Best ask for NO at venue B
        ask_no_a: Best ask for NO at venue A
        ask_yes_b: Best ask for YES at venue B
        total_costs: Total trading costs as decimal
        
    Returns:
        Tuple of (max_edge_bps, edge_direction, rationale)
    """
    # Direction 1: Buy YES@A + Buy NO@B
    sum1 = ask_yes_a + ask_no_b + total_costs
    edge1_bps = max(0.0, (1.0 - sum1) * 10000.0)

    # Direction 2: Buy NO@A + Buy YES@B
    sum2 = ask_no_a + ask_yes_b + total_costs
    edge2_bps = max(0.0, (1.0 - sum2) * 10000.0)

    if edge1_bps > edge2_bps:
        return edge1_bps, edge1_bps, f"YES@A+NO@B: {edge1_bps:.1f}bps"
    else:
        return edge2_bps, edge2_bps, f"NO@A+YES@B: {edge2_bps:.1f}bps"


def min_executable_qty(
    qty_yes: float,
    qty_no: float,
    max_capital: float,
    price_yes: float,
    price_no: float,
) -> float:
    """Calculate minimum executable quantity for both legs.
    
    Args:
        qty_yes: Available quantity for YES leg
        qty_no: Available quantity for NO leg
        max_capital: Maximum capital to deploy
        price_yes: YES contract price
        price_no: NO contract price
        
    Returns:
        Maximum executable quantity for both legs
    """
    # Calculate capital required per unit
    capital_per_unit = price_yes + price_no

    # Calculate quantity limits
    qty_limit_capital = max_capital / capital_per_unit if capital_per_unit > 0 else 0
    qty_limit_liquidity = min(qty_yes, qty_no)

    return min(qty_limit_capital, qty_limit_liquidity)


def calculate_breakeven_probability(
    price_yes: float,
    price_no: float,
    total_costs: float = 0.0,
) -> float:
    """Calculate breakeven probability for arbitrage trade.
    
    Args:
        price_yes: YES contract price
        price_no: NO contract price
        total_costs: Total trading costs
        
    Returns:
        Breakeven probability
    """
    total_cost = price_yes + price_no + total_costs
    return 1.0 - total_cost


def is_arbitrage_profitable(
    edge_bps: float,
    min_edge_bps: float,
    notional_usd: float,
    min_notional_usd: float,
) -> bool:
    """Check if arbitrage opportunity meets profitability criteria.
    
    Args:
        edge_bps: Arbitrage edge in basis points
        min_edge_bps: Minimum required edge in basis points
        notional_usd: Trade notional in USD
        min_notional_usd: Minimum required notional in USD
        
    Returns:
        True if profitable, False otherwise
    """
    return edge_bps >= min_edge_bps and notional_usd >= min_notional_usd


def calculate_expected_pnl(
    edge_bps: float,
    notional_usd: float,
    probability: float = 0.5,
) -> float:
    """Calculate expected PnL for arbitrage trade.
    
    Args:
        edge_bps: Arbitrage edge in basis points
        notional_usd: Trade notional in USD
        probability: Event probability (default 0.5 for risk-neutral)
        
    Returns:
        Expected PnL in USD
    """
    edge_decimal = edge_bps / 10000.0
    return notional_usd * edge_decimal


def normalize_quote_to_probability(quote: Quote, side: ContractSide) -> float:
    """Convert quote to implied probability.
    
    Args:
        quote: Market quote
        side: Contract side
        
    Returns:
        Implied probability from mid price
    """
    if quote.mid_price is None:
        mid_price = (quote.best_bid + quote.best_ask) / 2
    else:
        mid_price = quote.mid_price

    return price_to_probability(mid_price, side)


def calculate_spread_bps(quote: Quote) -> float:
    """Calculate bid-ask spread in basis points.
    
    Args:
        quote: Market quote
        
    Returns:
        Spread in basis points
    """
    if quote.best_ask <= quote.best_bid:
        return 0.0

    spread = quote.best_ask - quote.best_bid
    return spread * 10000.0


def calculate_liquidity_score(quote: Quote) -> float:
    """Calculate liquidity score based on size and spread.
    
    Args:
        quote: Market quote
        
    Returns:
        Liquidity score (higher is better)
    """
    spread_bps = calculate_spread_bps(quote)
    total_size = quote.best_bid_size + quote.best_ask_size

    # Higher size and lower spread = better liquidity
    if spread_bps == 0:
        return float("inf")

    return total_size / spread_bps


def round_to_tick_size(price: float, tick_size: float) -> float:
    """Round price to venue tick size.
    
    Args:
        price: Raw price
        tick_size: Venue tick size
        
    Returns:
        Rounded price
    """
    if tick_size <= 0:
        return price

    return round(price / tick_size) * tick_size


def calculate_kelly_fraction(
    edge_bps: float,
    probability: float = 0.5,
    bankroll: float = 10000.0,
) -> float:
    """Calculate Kelly fraction for position sizing.
    
    Args:
        edge_bps: Arbitrage edge in basis points
        probability: Event probability
        bankroll: Available bankroll
        
    Returns:
        Kelly fraction (0-1)
    """
    edge_decimal = edge_bps / 10000.0

    if edge_decimal <= 0:
        return 0.0

    # Kelly formula: f = (bp - q) / b
    # where b = odds, p = win probability, q = lose probability
    # For arbitrage: b = 1 (1:1 payout), p = probability, q = 1-p
    b = 1.0  # 1:1 payout
    p = probability
    q = 1.0 - probability

    kelly_fraction = (b * p - q) / b

    # Cap at reasonable maximum
    return max(0.0, min(kelly_fraction, 0.25))


