"""Arbitrage opportunity discovery engine."""

from __future__ import annotations

import asyncio
from datetime import datetime

from .event_registry import EventRegistry
from .fees import FeeCalculator
from .matcher import EventMatcher
from .odds import (
    calculate_arbitrage_edge,
    is_arbitrage_profitable,
    min_executable_qty,
)
from .types import (
    ArbOpportunity,
    Contract,
    OrderRequest,
    OrderSide,
    OrderTIF,
    Quote,
    Venue,
)
from .venue_mappers import KalshiMapper, PolymarketMapper


class DiscoveryEngine:
    """Discovers arbitrage opportunities across venues."""

    def __init__(
        self,
        fee_calculator: FeeCalculator,
        event_matcher: EventMatcher,
        event_registry: EventRegistry | None = None,
        min_edge_bps: float = 80.0,
        min_notional_usd: float = 100.0,
        max_slippage_bps: float = 25.0,
        use_deterministic_mapping: bool = True,
    ):
        """Initialize discovery engine.
        
        Args:
            fee_calculator: Fee calculator for cost estimation
            event_matcher: Event matcher for cross-venue matching (fallback)
            event_registry: Event registry for deterministic mapping
            min_edge_bps: Minimum edge in basis points
            min_notional_usd: Minimum notional size in USD
            max_slippage_bps: Maximum slippage tolerance in basis points
            use_deterministic_mapping: Use registry-based deterministic mapping
        """
        self.fee_calculator = fee_calculator
        self.event_matcher = event_matcher
        self.min_edge_bps = min_edge_bps
        self.min_notional_usd = min_notional_usd
        self.max_slippage_bps = max_slippage_bps
        self.use_deterministic_mapping = use_deterministic_mapping

        # Event registry and mappers
        self.event_registry = event_registry or EventRegistry()
        self.venue_mappers = {
            Venue.POLYMARKET: PolymarketMapper(self.event_registry),
            Venue.KALSHI: KalshiMapper(self.event_registry),
        }

        # Cache for contracts and quotes
        self._contracts_cache: dict[Venue, list[Contract]] = {}
        self._quotes_cache: dict[str, Quote] = {}
        self._last_update: dict[Venue, datetime] = {}
        
        # Track mapping statistics
        self._mapping_stats = {
            "total_markets": 0,
            "mapped_markets": 0,
            "abstained_markets": 0,
        }

    async def discover_opportunities(
        self,
        connectors: dict[Venue, any],  # VenueClient protocol
        refresh_contracts: bool = False,
    ) -> list[ArbOpportunity]:
        """Discover arbitrage opportunities across venues.
        
        Args:
            connectors: Dictionary mapping venues to their connectors
            refresh_contracts: Whether to refresh contract list
            
        Returns:
            List of arbitrage opportunities
        """
        opportunities = []

        # Refresh contracts if needed
        if refresh_contracts or not self._contracts_cache:
            await self._refresh_contracts(connectors)

        # Get matched pairs
        matched_pairs = self._get_matched_pairs()

        # Refresh quotes for matched contracts
        await self._refresh_quotes(connectors, matched_pairs)

        # Find opportunities
        for pair in matched_pairs:
            pair_opportunities = self._find_pair_opportunities(pair)
            opportunities.extend(pair_opportunities)

        # Filter and sort opportunities
        filtered_opportunities = self._filter_opportunities(opportunities)

        return filtered_opportunities

    async def _refresh_contracts(self, connectors: dict[Venue, any]) -> None:
        """Refresh contract lists from all venues."""
        tasks = []
        for venue, connector in connectors.items():
            tasks.append(self._fetch_contracts(venue, connector))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_contracts(self, venue: Venue, connector: any) -> None:
        """Fetch contracts from a single venue."""
        try:
            contracts = await connector.list_contracts()
            
            # Map contracts to canonical event IDs if using deterministic mapping
            if self.use_deterministic_mapping:
                mapped_contracts = []
                mapper = self.venue_mappers.get(venue)
                
                for contract in contracts:
                    self._mapping_stats["total_markets"] += 1
                    
                    if mapper:
                        # Try to map to canonical event ID
                        event_id = mapper.map_to_event_id(
                            market_id=contract.normalized_event_id,
                            title=contract.event_key,
                            description="",
                            metadata={"close_time": contract.expires_at},
                        )
                        
                        if event_id:
                            # Update contract with canonical event ID
                            contract.normalized_event_id = event_id
                            mapped_contracts.append(contract)
                            self._mapping_stats["mapped_markets"] += 1
                        else:
                            # Abstain - don't include unmapped contracts
                            self._mapping_stats["abstained_markets"] += 1
                    else:
                        # No mapper for venue, include as-is
                        mapped_contracts.append(contract)
                
                self._contracts_cache[venue] = mapped_contracts
            else:
                # Use legacy matcher
                self._contracts_cache[venue] = contracts
            
            self._last_update[venue] = datetime.utcnow()
        except Exception as e:
            print(f"Failed to fetch contracts from {venue}: {e}")

    def _get_matched_pairs(self) -> list[any]:  # MatchedPair
        """Get matched pairs from cached contracts."""
        venues = list(self._contracts_cache.keys())
        if len(venues) < 2:
            return []

        # Get contracts from first two venues
        venue_a, venue_b = venues[0], venues[1]
        contracts_a = self._contracts_cache[venue_a]
        contracts_b = self._contracts_cache[venue_b]

        if self.use_deterministic_mapping:
            # Use deterministic event_id matching
            return self._match_by_event_id(contracts_a, contracts_b)
        else:
            # Use legacy fuzzy matching
            return self.event_matcher.match_events(contracts_a, contracts_b)

    async def _refresh_quotes(
        self,
        connectors: dict[Venue, any],
        matched_pairs: list[any],  # MatchedPair
    ) -> None:
        """Refresh quotes for matched contracts."""
        # Collect all contract IDs
        contract_ids = set()
        for pair in matched_pairs:
            contract_ids.add(pair.contract_a.contract_id)
            contract_ids.add(pair.contract_b.contract_id)

        # Fetch quotes from each venue
        tasks = []
        for venue, connector in connectors.items():
            venue_contracts = [
                cid for cid in contract_ids
                if cid.startswith(f"{venue.value}_")
            ]
            if venue_contracts:
                tasks.append(self._fetch_quotes(venue, connector, venue_contracts))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_quotes(
        self,
        venue: Venue,
        connector: any,
        contract_ids: list[str],
    ) -> None:
        """Fetch quotes from a single venue."""
        try:
            quotes = await connector.get_quotes(contract_ids)
            for quote in quotes:
                self._quotes_cache[quote.contract_id] = quote
        except Exception as e:
            print(f"Failed to fetch quotes from {venue}: {e}")

    def _find_pair_opportunities(self, pair: any) -> list[ArbOpportunity]:  # MatchedPair
        """Find opportunities for a matched pair."""
        opportunities = []

        # Get quotes for both contracts
        quote_a = self._quotes_cache.get(pair.contract_a.contract_id)
        quote_b = self._quotes_cache.get(pair.contract_b.contract_id)

        if not quote_a or not quote_b:
            return opportunities

        # Check liquidity
        if not self._has_sufficient_liquidity(quote_a, quote_b):
            return opportunities

        # Calculate both directions
        opportunities.extend(
            self._calculate_direction_opportunities(
                pair, quote_a, quote_b, "YES@A+NO@B"
            )
        )
        opportunities.extend(
            self._calculate_direction_opportunities(
                pair, quote_a, quote_b, "NO@A+YES@B"
            )
        )

        return opportunities

    def _has_sufficient_liquidity(self, quote_a: Quote, quote_b: Quote) -> bool:
        """Check if quotes have sufficient liquidity."""
        min_size = 100.0  # Minimum size requirement

        return (
            quote_a.best_bid_size >= min_size and
            quote_a.best_ask_size >= min_size and
            quote_b.best_bid_size >= min_size and
            quote_b.best_ask_size >= min_size
        )

    def _calculate_direction_opportunities(
        self,
        pair: any,  # MatchedPair
        quote_a: Quote,
        quote_b: Quote,
        direction: str,
    ) -> list[ArbOpportunity]:
        """Calculate opportunities for a specific direction."""
        opportunities = []

        if direction == "YES@A+NO@B":
            # Buy YES at A, Buy NO at B
            ask_yes_a = quote_a.best_ask
            ask_no_b = quote_b.best_ask

            # Calculate effective prices including costs
            eff_ask_yes_a = self._calculate_effective_price(
                pair.contract_a, ask_yes_a, OrderSide.BUY
            )
            eff_ask_no_b = self._calculate_effective_price(
                pair.contract_b, ask_no_b, OrderSide.BUY
            )

            # Calculate edge
            edge_bps, _, rationale = calculate_arbitrage_edge(
                eff_ask_yes_a, eff_ask_no_b, 0.0, 0.0
            )

            if edge_bps >= self.min_edge_bps:
                # Calculate executable quantity
                qty = min_executable_qty(
                    quote_a.best_ask_size,
                    quote_b.best_ask_size,
                    self.min_notional_usd,
                    eff_ask_yes_a,
                    eff_ask_no_b,
                )

                if qty >= 1.0:
                    notional = qty * (eff_ask_yes_a + eff_ask_no_b)

                    if notional >= self.min_notional_usd:
                        opportunity = ArbOpportunity(
                            event_id=pair.event_id,
                            leg_a=OrderRequest(
                                venue=pair.contract_a.venue,
                                contract_id=pair.contract_a.contract_id,
                                side=OrderSide.BUY,
                                price=ask_yes_a,
                                qty=qty,
                                tif=OrderTIF.IOC,
                            ),
                            leg_b=OrderRequest(
                                venue=pair.contract_b.venue,
                                contract_id=pair.contract_b.contract_id,
                                side=OrderSide.BUY,
                                price=ask_no_b,
                                qty=qty,
                                tif=OrderTIF.IOC,
                            ),
                            edge_bps=edge_bps,
                            notional=notional,
                            expiry=pair.contract_a.expires_at,
                            rationale=rationale,
                            confidence_score=pair.confidence_score,
                        )
                        opportunities.append(opportunity)

        elif direction == "NO@A+YES@B":
            # Buy NO at A, Buy YES at B
            ask_no_a = quote_a.best_ask
            ask_yes_b = quote_b.best_ask

            # Calculate effective prices including costs
            eff_ask_no_a = self._calculate_effective_price(
                pair.contract_a, ask_no_a, OrderSide.BUY
            )
            eff_ask_yes_b = self._calculate_effective_price(
                pair.contract_b, ask_yes_b, OrderSide.BUY
            )

            # Calculate edge
            edge_bps, _, rationale = calculate_arbitrage_edge(
                0.0, 0.0, eff_ask_no_a, eff_ask_yes_b
            )

            if edge_bps >= self.min_edge_bps:
                # Calculate executable quantity
                qty = min_executable_qty(
                    quote_a.best_ask_size,
                    quote_b.best_ask_size,
                    self.min_notional_usd,
                    eff_ask_no_a,
                    eff_ask_yes_b,
                )

                if qty >= 1.0:
                    notional = qty * (eff_ask_no_a + eff_ask_yes_b)

                    if notional >= self.min_notional_usd:
                        opportunity = ArbOpportunity(
                            event_id=pair.event_id,
                            leg_a=OrderRequest(
                                venue=pair.contract_a.venue,
                                contract_id=pair.contract_a.contract_id,
                                side=OrderSide.BUY,
                                price=ask_no_a,
                                qty=qty,
                                tif=OrderTIF.IOC,
                            ),
                            leg_b=OrderRequest(
                                venue=pair.contract_b.venue,
                                contract_id=pair.contract_b.contract_id,
                                side=OrderSide.BUY,
                                price=ask_yes_b,
                                qty=qty,
                                tif=OrderTIF.IOC,
                            ),
                            edge_bps=edge_bps,
                            notional=notional,
                            expiry=pair.contract_a.expires_at,
                            rationale=rationale,
                            confidence_score=pair.confidence_score,
                        )
                        opportunities.append(opportunity)

        return opportunities

    def _calculate_effective_price(
        self,
        contract: Contract,
        price: float,
        side: OrderSide,
    ) -> float:
        """Calculate effective price including fees and slippage."""
        return self.fee_calculator.calculate_effective_price(
            contract.venue,
            side,
            price,
            1.0,  # Assume 1 unit for cost calculation
            is_maker=False,  # Assume taker orders
        )

    def _filter_opportunities(
        self,
        opportunities: list[ArbOpportunity],
    ) -> list[ArbOpportunity]:
        """Filter opportunities based on criteria."""
        filtered = []

        for opp in opportunities:
            # Check profitability
            if not is_arbitrage_profitable(
                opp.edge_bps,
                self.min_edge_bps,
                opp.notional,
                self.min_notional_usd,
            ):
                continue

            # Check expiry (avoid trades too close to expiry)
            time_to_expiry = (opp.expiry - datetime.utcnow()).total_seconds()
            if time_to_expiry < 3600:  # Less than 1 hour
                continue

            filtered.append(opp)

        # Sort by edge (highest first)
        filtered.sort(key=lambda x: x.edge_bps, reverse=True)

        return filtered

    def _match_by_event_id(
        self,
        contracts_a: list[Contract],
        contracts_b: list[Contract],
    ) -> list[any]:  # MatchedPair
        """Match contracts by canonical event_id (deterministic).
        
        Args:
            contracts_a: Contracts from venue A
            contracts_b: Contracts from venue B
            
        Returns:
            List of matched pairs
        """
        from .types import MatchedPair
        
        matched_pairs = []
        
        # Group contracts by event_id
        events_a: dict[str, list[Contract]] = {}
        for contract in contracts_a:
            event_id = contract.normalized_event_id
            if event_id not in events_a:
                events_a[event_id] = []
            events_a[event_id].append(contract)
        
        events_b: dict[str, list[Contract]] = {}
        for contract in contracts_b:
            event_id = contract.normalized_event_id
            if event_id not in events_b:
                events_b[event_id] = []
            events_b[event_id].append(contract)
        
        # Find matching event_ids
        common_event_ids = set(events_a.keys()) & set(events_b.keys())
        
        for event_id in common_event_ids:
            contracts_a_group = events_a[event_id]
            contracts_b_group = events_b[event_id]
            
            # Create matched pairs for YES/NO contracts
            yes_a = next((c for c in contracts_a_group if c.side.value == "YES"), None)
            no_a = next((c for c in contracts_a_group if c.side.value == "NO"), None)
            yes_b = next((c for c in contracts_b_group if c.side.value == "YES"), None)
            no_b = next((c for c in contracts_b_group if c.side.value == "NO"), None)
            
            if yes_a and yes_b:
                matched_pairs.append(MatchedPair(
                    event_id=event_id,
                    contract_a=yes_a,
                    contract_b=yes_b,
                    confidence_score=1.0,
                    match_reason="deterministic_event_id_yes",
                ))
            
            if no_a and no_b:
                matched_pairs.append(MatchedPair(
                    event_id=event_id,
                    contract_a=no_a,
                    contract_b=no_b,
                    confidence_score=1.0,
                    match_reason="deterministic_event_id_no",
                ))
        
        return matched_pairs

    def get_discovery_stats(self) -> dict[str, any]:
        """Get discovery statistics."""
        total_contracts = sum(len(contracts) for contracts in self._contracts_cache.values())
        total_quotes = len(self._quotes_cache)

        stats = {
            "total_contracts": total_contracts,
            "total_quotes": total_quotes,
            "venues_connected": len(self._contracts_cache),
            "last_update": self._last_update,
        }
        
        # Add mapping statistics if using deterministic mapping
        if self.use_deterministic_mapping:
            stats["mapping_stats"] = self._mapping_stats
            stats["registry_stats"] = self.event_registry.get_coverage_stats()
        
        return stats


