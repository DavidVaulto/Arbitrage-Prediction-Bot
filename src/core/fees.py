"""Fee calculation and cost estimation for different venues."""

from __future__ import annotations

from .types import FeeModel, OrderSide, Venue


class FeeCalculator:
    """Calculates trading fees and costs for different venues."""

    def __init__(self, fee_models: dict[Venue, FeeModel]):
        """Initialize with fee models for each venue.
        
        Args:
            fee_models: Dictionary mapping venues to their fee models
        """
        self.fee_models = fee_models

    def estimate_trade_cost(
        self,
        venue: Venue,
        side: OrderSide,
        price: float,
        qty: float,
        is_maker: bool = False,
    ) -> float:
        """Estimate total trading cost for a trade.
        
        Args:
            venue: Trading venue
            side: Order side (BUY/SELL)
            price: Contract price
            qty: Trade quantity
            is_maker: Whether this is a maker order
            
        Returns:
            Total cost in USD
        """
        fee_model = self.fee_models.get(venue)
        if not fee_model:
            return 0.0

        notional = price * qty

        # Calculate trading fee
        fee_bps = fee_model.maker_bps if is_maker else fee_model.taker_bps
        trading_fee = notional * (fee_bps / 10000.0)

        # Add gas costs (for crypto venues)
        gas_cost = fee_model.gas_estimate_usd

        # Add withdrawal fees if applicable
        withdrawal_fee = fee_model.withdrawal_fee or 0.0

        return trading_fee + gas_cost + withdrawal_fee

    def calculate_effective_price(
        self,
        venue: Venue,
        side: OrderSide,
        price: float,
        qty: float,
        is_maker: bool = False,
    ) -> float:
        """Calculate effective price including all costs.
        
        Args:
            venue: Trading venue
            side: Order side (BUY/SELL)
            price: Contract price
            qty: Trade quantity
            is_maker: Whether this is a maker order
            
        Returns:
            Effective price including costs
        """
        total_cost = self.estimate_trade_cost(venue, side, price, qty, is_maker)
        notional = price * qty

        if notional == 0:
            return price

        cost_per_unit = total_cost / qty

        if side == OrderSide.BUY:
            return price + cost_per_unit
        else:
            return price - cost_per_unit

    def calculate_breakeven_price(
        self,
        venue: Venue,
        side: OrderSide,
        target_price: float,
        qty: float,
        is_maker: bool = False,
    ) -> float:
        """Calculate breakeven price for a target effective price.
        
        Args:
            venue: Trading venue
            side: Order side (BUY/SELL)
            target_price: Target effective price
            qty: Trade quantity
            is_maker: Whether this is a maker order
            
        Returns:
            Breakeven contract price
        """
        fee_model = self.fee_models.get(venue)
        if not fee_model:
            return target_price

        # Calculate cost components
        fee_bps = fee_model.maker_bps if is_maker else fee_model.taker_bps
        gas_cost = fee_model.gas_estimate_usd
        withdrawal_fee = fee_model.withdrawal_fee or 0.0

        # Solve for contract price given target effective price
        # For BUY: target = price + (price * fee_bps/10000 + gas_cost + withdrawal_fee) / qty
        # For SELL: target = price - (price * fee_bps/10000 + gas_cost + withdrawal_fee) / qty

        total_fixed_cost = gas_cost + withdrawal_fee

        if side == OrderSide.BUY:
            # target = price + (price * fee_bps/10000 + total_fixed_cost) / qty
            # target = price * (1 + fee_bps/10000/qty) + total_fixed_cost / qty
            # price = (target - total_fixed_cost/qty) / (1 + fee_bps/10000/qty)
            denominator = 1 + (fee_bps / 10000.0) / qty
            numerator = target_price - total_fixed_cost / qty
            return numerator / denominator if denominator != 0 else target_price
        else:
            # target = price - (price * fee_bps/10000 + total_fixed_cost) / qty
            # target = price * (1 - fee_bps/10000/qty) - total_fixed_cost / qty
            # price = (target + total_fixed_cost/qty) / (1 - fee_bps/10000/qty)
            denominator = 1 - (fee_bps / 10000.0) / qty
            numerator = target_price + total_fixed_cost / qty
            return numerator / denominator if denominator != 0 else target_price

    def get_fee_summary(self, venue: Venue) -> dict[str, float]:
        """Get fee summary for a venue.
        
        Args:
            venue: Trading venue
            
        Returns:
            Dictionary with fee information
        """
        fee_model = self.fee_models.get(venue)
        if not fee_model:
            return {}

        return {
            "maker_bps": fee_model.maker_bps,
            "taker_bps": fee_model.taker_bps,
            "gas_estimate_usd": fee_model.gas_estimate_usd,
            "withdrawal_fee": fee_model.withdrawal_fee or 0.0,
        }


class PolymarketFeeCalculator(FeeCalculator):
    """Specialized fee calculator for Polymarket."""

    def __init__(self, fee_model: FeeModel):
        """Initialize with Polymarket fee model."""
        super().__init__({Venue.POLYMARKET: fee_model})

    def estimate_gas_cost(
        self,
        network: str = "polygon",
        gas_price_gwei: float | None = None,
    ) -> float:
        """Estimate gas cost for Polymarket transactions.
        
        Args:
            network: Blockchain network
            gas_price_gwei: Gas price in Gwei (if None, use default)
            
        Returns:
            Estimated gas cost in USD
        """
        # Default gas prices (in Gwei)
        default_gas_prices = {
            "polygon": 30.0,
            "ethereum": 20.0,
        }

        gas_price = gas_price_gwei or default_gas_prices.get(network, 30.0)

        # Typical gas usage for Polymarket operations
        gas_usage = {
            "place_order": 150000,
            "cancel_order": 100000,
            "settle": 200000,
        }

        # Estimate cost for placing an order
        gas_cost_gwei = gas_usage["place_order"] * gas_price

        # Convert to USD (rough estimate: 1 Gwei ≈ $0.000001)
        gas_cost_usd = gas_cost_gwei * 0.000001

        return gas_cost_usd


class KalshiFeeCalculator(FeeCalculator):
    """Specialized fee calculator for Kalshi."""

    def __init__(self, fee_model: FeeModel):
        """Initialize with Kalshi fee model."""
        super().__init__({Venue.KALSHI: fee_model})

    def calculate_commission(
        self,
        notional: float,
        is_maker: bool = False,
    ) -> float:
        """Calculate Kalshi commission.
        
        Args:
            notional: Trade notional in USD
            is_maker: Whether this is a maker order
            
        Returns:
            Commission in USD
        """
        fee_model = self.fee_models[Venue.KALSHI]
        fee_bps = fee_model.maker_bps if is_maker else fee_model.taker_bps

        return notional * (fee_bps / 10000.0)

    def calculate_settlement_fee(self, qty: float) -> float:
        """Calculate settlement fee for Kalshi.
        
        Args:
            qty: Settlement quantity
            
        Returns:
            Settlement fee in USD
        """
        # Kalshi typically charges a small settlement fee per contract
        return qty * 0.01  # $0.01 per contract


def create_default_fee_calculator() -> FeeCalculator:
    """Create default fee calculator with standard fee models.
    
    Returns:
        Fee calculator with default fee models
    """
    fee_models = {
        Venue.POLYMARKET: FeeModel(
            maker_bps=0.0,
            taker_bps=25.0,
            gas_estimate_usd=0.50,
        ),
        Venue.KALSHI: FeeModel(
            maker_bps=0.0,
            taker_bps=30.0,
        ),
    }

    return FeeCalculator(fee_models)


