"""Debt rebalancing optimizer for lending markets."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from collections import OrderedDict
import statistics

from src.sandbox.models.rebalancing import (
    RebalancingConfig,
    RebalancingMode,
    RebalancingTrigger,
    MarketDebtInfo,
    DebtPosition,
    RebalancingOpportunity,
    RebalancingSnapshot,
    RebalancingMetrics,
    RiskSnapshot,
    PositionSummary,
    RebalancingResult,
)
from src.sandbox.data import DataAggregator
from src.sandbox.engine.risk import RiskCalculator
from src.core.models import Market, TimeseriesPoint

logger = logging.getLogger(__name__)


class DebtRebalancingOptimizer:
    """
    Optimizer for debt rebalancing across Morpho markets.

    Features:
    - Market discovery for collateral/borrow pairs
    - Rate analysis with IRM predictions
    - Greedy optimal allocation algorithm
    - Cost/benefit opportunity analysis
    - Historical simulation with benchmarking
    """

    # Cache configuration
    CACHE_TTL_SECONDS = 300  # 5 minutes
    CACHE_MAX_ENTRIES = 100

    def __init__(self, data: DataAggregator):
        self.data = data
        self._market_cache: OrderedDict[str, Tuple[Market, datetime]] = OrderedDict()

    def _cache_market(self, market: Market) -> None:
        """Add market to cache with timestamp, evicting old entries if needed."""
        now = datetime.now(timezone.utc)

        # Evict expired entries
        expired_keys = [
            key for key, (_, ts) in self._market_cache.items()
            if (now - ts).total_seconds() > self.CACHE_TTL_SECONDS
        ]
        for key in expired_keys:
            del self._market_cache[key]

        # Evict oldest entries if over max size
        while len(self._market_cache) >= self.CACHE_MAX_ENTRIES:
            self._market_cache.popitem(last=False)

        # Add new entry (move to end if exists for LRU)
        if market.id in self._market_cache:
            self._market_cache.move_to_end(market.id)
        self._market_cache[market.id] = (market, now)

    def _get_cached_market(self, market_id: str) -> Optional[Market]:
        """Get market from cache if valid, None otherwise."""
        if market_id not in self._market_cache:
            return None

        market, ts = self._market_cache[market_id]
        if (datetime.now(timezone.utc) - ts).total_seconds() > self.CACHE_TTL_SECONDS:
            del self._market_cache[market_id]
            return None

        # Move to end for LRU
        self._market_cache.move_to_end(market_id)
        return market

    def _get_collateral_price(
        self,
        markets: List[MarketDebtInfo],
    ) -> Tuple[Decimal, Decimal]:
        """Get collateral and loan prices from market data.

        Returns: (collateral_price_usd, loan_price_usd)

        Raises:
            ValueError: If no valid price data is available
        """
        # Get prices from first available market in cache
        for market in markets:
            m = self._get_cached_market(market.market_id)
            if m and m.collateral_asset_price_usd > 0 and m.loan_asset_price_usd > 0:
                return (m.collateral_asset_price_usd, m.loan_asset_price_usd)

        # No fallback - raise exception for missing price data
        raise ValueError(
            "No valid price data available. Ensure markets are cached with valid prices."
        )

    async def optimize(
        self,
        config: RebalancingConfig,
    ) -> RebalancingResult:
        """
        Run debt rebalancing optimization.

        Args:
            config: Rebalancing configuration

        Returns:
            RebalancingResult with markets, allocations, and simulation
        """
        logger.info(
            f"Starting debt optimization: {config.collateral_asset}/{config.borrow_asset}, "
            f"collateral={config.collateral_amount}, LTV={config.initial_ltv*100:.0f}%, "
            f"borrow={config.total_debt}"
        )

        start_time = datetime.now(timezone.utc)

        try:
            # 1. Discover available markets
            markets = await self._discover_markets(config)
            if not markets:
                return RebalancingResult(
                    config=config,
                    start_time=start_time,
                    end_time=datetime.now(timezone.utc),
                    success=False,
                    error_message=f"No markets found for {config.collateral_asset}/{config.borrow_asset}",
                )

            logger.info(f"Found {len(markets)} markets")

            # 2. Analyze markets (rates, predictions, scoring)
            analyzed_markets = await self._analyze_markets(markets, config)

            # 3. Calculate optimal allocation
            allocation, positions = self._calculate_optimal_allocation(
                analyzed_markets, config
            )

            # 4. Generate rebalancing opportunities
            opportunities = self._generate_opportunities(
                analyzed_markets, positions, config
            )

            # 5. Run historical simulation
            snapshots, benchmark_snapshots = await self._run_simulation(
                analyzed_markets, config
            )

            # 6. Calculate metrics
            metrics = self._calculate_metrics(
                snapshots, benchmark_snapshots, config
            )

            # 7. Generate position summary with price scenarios
            position_summary = self._generate_position_summary(
                analyzed_markets, positions, config
            )

            end_time = datetime.now(timezone.utc)

            result = RebalancingResult(
                config=config,
                start_time=snapshots[0].timestamp if snapshots else start_time,
                end_time=snapshots[-1].timestamp if snapshots else end_time,
                available_markets=analyzed_markets,
                optimal_allocation=allocation,
                optimal_positions=positions,
                opportunities=opportunities,
                snapshots=snapshots,
                benchmark_snapshots=benchmark_snapshots,
                metrics=metrics,
                position_summary=position_summary,
                success=True,
            )

            logger.info(
                f"Optimization complete: {len(markets)} markets, "
                f"{len(opportunities)} opportunities"
            )

            return result

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            return RebalancingResult(
                config=config,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                success=False,
                error_message=str(e),
            )

    async def _discover_markets(
        self,
        config: RebalancingConfig,
    ) -> List[Market]:
        """Find markets matching the collateral/borrow pair.

        Supports matching by:
        - Address (0x...): Exact match on collateral_asset and loan_asset addresses
        - Symbol: Substring match (less precise, may include unwanted tokens)
        """
        # Get all markets
        all_markets = await self.data.get_markets(config.protocol, first=500)

        # Filter by collateral/borrow pair
        matching_markets = []

        for m in all_markets:
            # Check if config uses addresses (more precise)
            if config.uses_address_matching:
                # Exact address matching (case-insensitive)
                collat_match = m.collateral_asset.lower() == config.collateral_asset.lower()
                loan_match = m.loan_asset.lower() == config.borrow_asset.lower()
            else:
                # Symbol substring matching (fallback, less precise)
                collat_match = config.collateral_asset.lower() in m.collateral_asset_symbol.lower()
                loan_match = config.borrow_asset.lower() in m.loan_asset_symbol.lower()

            if collat_match and loan_match:
                matching_markets.append(m)

        logger.info(
            f"Found {len(matching_markets)} markets matching "
            f"{config.collateral_asset}/{config.borrow_asset} "
            f"(address_match={config.uses_address_matching})"
        )

        # Filter by reasonable TVL, liquidity, and rates
        valid_markets = []
        for m in matching_markets:
            # Minimum TVL threshold
            if float(m.tvl) < 100_000:
                logger.debug(f"Skipping {m.name}: TVL too low ({m.tvl})")
                continue

            # Must have available liquidity
            available = float(m.state.available_liquidity) if m.state else 0
            if available < 10_000:
                logger.debug(f"Skipping {m.name}: Liquidity too low ({available})")
                continue

            # Reasonable borrow APY (not broken/extreme)
            if float(m.borrow_apy) > 0.5:  # > 50% APY seems broken
                logger.debug(f"Skipping {m.name}: Borrow APY too high ({m.borrow_apy})")
                continue

            # Check LLTV is reasonable (not 0 or broken)
            if float(m.lltv) < 0.5 or float(m.lltv) > 0.99:
                logger.debug(f"Skipping {m.name}: LLTV out of range ({m.lltv})")
                continue

            valid_markets.append(m)
            self._cache_market(m)

        # Sort by TVL descending
        valid_markets.sort(key=lambda x: float(x.tvl), reverse=True)

        return valid_markets

    async def _analyze_markets(
        self,
        markets: List[Market],
        config: RebalancingConfig,
    ) -> List[MarketDebtInfo]:
        """Analyze markets with rate predictions, LLTV-based scoring, and volatility."""
        analyzed = []

        # Fetch historical data for volatility calculation
        market_history: Dict[str, List[TimeseriesPoint]] = {}
        for market in markets:
            try:
                timeseries = await self.data.get_market_timeseries(
                    protocol=config.protocol,
                    market_id=market.id,
                    interval="HOUR",
                    days=7,  # 7 days for volatility analysis
                )
                if timeseries:
                    market_history[market.id] = timeseries
            except Exception as e:
                logger.debug(f"Could not fetch history for {market.name}: {e}")

        for market in markets:
            # Get current state
            state = market.state
            available = state.available_liquidity if state else Decimal("0")
            total_borrow = state.total_borrow_assets if state else Decimal("0")
            utilization = float(market.utilization)
            lltv = float(market.lltv)

            # Calculate LLTV-based limits
            # max_leverage = 1 / (1 - LLTV)
            # e.g., LLTV 0.945 -> max leverage = 18.18x
            effective_max_leverage = Decimal("1") / (Decimal("1") - market.lltv) if market.lltv < Decimal("1") else Decimal("999")

            # Safe leverage based on maintaining min health factor
            # For LTV-based approach, safe_leverage indicates max leverage at initial_ltv
            safe_leverage = effective_max_leverage * Decimal("0.85")  # 85% of max as safety buffer

            # Calculate rate volatility from historical data
            rate_volatility = Decimal("0")
            rate_trend = Decimal("0")

            if market.id in market_history:
                history = market_history[market.id]
                if len(history) >= 2:
                    rates = [float(p.borrow_apy) for p in history]

                    # Volatility = standard deviation of rates
                    if len(rates) > 1:
                        rate_volatility = Decimal(str(statistics.stdev(rates)))

                    # Trend = (recent rate - older rate) / older rate
                    # Positive = rates increasing, negative = rates decreasing
                    recent_rates = rates[-24:] if len(rates) >= 24 else rates  # Last 24h
                    older_rates = rates[:24] if len(rates) >= 48 else rates[:len(rates)//2]

                    if older_rates and recent_rates:
                        avg_recent = statistics.mean(recent_rates)
                        avg_older = statistics.mean(older_rates)
                        if avg_older > 0:
                            rate_trend = Decimal(str((avg_recent - avg_older) / avg_older))

            # Predict future rates based on utilization and trend
            predicted_1d = market.borrow_apy
            predicted_7d = market.borrow_apy

            # Utilization-based prediction
            if utilization > float(config.utilization_alert_threshold):
                # High utilization - expect rate increase
                predicted_1d = market.borrow_apy * Decimal("1.05")
                predicted_7d = market.borrow_apy * Decimal("1.15")
            elif utilization > 0.8:
                # Medium-high utilization
                predicted_1d = market.borrow_apy * Decimal("1.02")
                predicted_7d = market.borrow_apy * Decimal("1.05")

            # Adjust with trend
            if rate_trend > Decimal("0.05"):  # >5% uptrend
                predicted_1d *= Decimal("1.02")
                predicted_7d *= Decimal("1.05")
            elif rate_trend < Decimal("-0.05"):  # >5% downtrend
                predicted_1d *= Decimal("0.98")
                predicted_7d *= Decimal("0.95")

            # Calculate component scores (lower = better)
            # 1. Rate score: Normalized borrow APY
            rate_score = market.borrow_apy * Decimal("100")  # Scale for readability

            # 2. Risk score: Combines LLTV risk and utilization risk
            # Higher LLTV = more efficient but riskier
            # Higher utilization = higher rate risk
            lltv_risk = Decimal("1") - market.lltv  # Lower LLTV = higher risk margin = safer
            util_risk = market.utilization if market.utilization > Decimal("0.8") else Decimal("0")
            risk_score = (Decimal("1") - lltv_risk) * Decimal("30") + util_risk * Decimal("20")

            # 3. Liquidity score: Penalize if not enough liquidity for our debt
            liquidity_ratio = min(Decimal("1"), available / config.total_debt) if config.total_debt > 0 else Decimal("1")
            liquidity_score = (Decimal("1") - liquidity_ratio) * Decimal("50")

            # Combined score (lower = better)
            # Weights: 60% rate, 25% risk, 15% liquidity
            score = rate_score * Decimal("0.6") + risk_score * Decimal("0.25") + liquidity_score * Decimal("0.15")

            info = MarketDebtInfo(
                market_id=market.id,
                market_name=market.name,
                collateral_symbol=market.collateral_asset_symbol,
                loan_symbol=market.loan_asset_symbol,
                collateral_address=market.collateral_asset,
                loan_address=market.loan_asset,
                borrow_apy=market.borrow_apy,
                supply_apy=market.supply_apy,
                utilization=market.utilization,
                lltv=market.lltv,
                available_liquidity=available,
                total_borrow=total_borrow,
                tvl=market.tvl,
                effective_max_leverage=effective_max_leverage,
                safe_leverage_at_lltv=safe_leverage,
                rate_volatility_24h=rate_volatility,
                rate_trend=rate_trend,
                predicted_rate_1d=predicted_1d,
                predicted_rate_7d=predicted_7d,
                score=score,
                rate_score=rate_score,
                risk_score=risk_score,
                liquidity_score=liquidity_score,
            )
            analyzed.append(info)

        # Sort by score (best first)
        analyzed.sort(key=lambda x: x.score)

        return analyzed

    def _calculate_optimal_allocation(
        self,
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
    ) -> Tuple[Dict[str, Decimal], List[DebtPosition]]:
        """
        Calculate optimal debt allocation using greedy algorithm with LTV constraints.

        Algorithm:
        1. Filter markets where initial_ltv < LLTV * 0.95 (safety margin)
        2. Sort by composite score (rate + risk + liquidity)
        3. Calculate borrow_amount in USD = collateral_amount * collateral_price * initial_ltv
        4. Convert to loan tokens: borrow_tokens = borrow_amount_usd / loan_price
        5. Allocate proportionally to markets by score
        """
        allocation: Dict[str, Decimal] = {}
        positions: List[DebtPosition] = []

        # Get real prices from market data
        collateral_price_usd, loan_price_usd = self._get_collateral_price(markets)

        # Calculate collateral value in USD and borrow amount in loan tokens
        collateral_value_usd = config.collateral_amount * collateral_price_usd
        borrow_amount_usd = collateral_value_usd * config.initial_ltv
        # Convert to loan tokens (e.g., USDC amount = USD / $1.00)
        # Note: loan_price_usd is guaranteed > 0 by _get_collateral_price validation
        total_borrow = borrow_amount_usd / loan_price_usd
        remaining_debt = total_borrow

        # Filter markets where our LTV is safe (below 95% of LLTV)
        viable_markets = []
        for market in markets:
            max_safe_ltv = market.lltv * Decimal("0.95")
            if config.initial_ltv > max_safe_ltv:
                logger.debug(
                    f"Skipping {market.market_name}: LTV {config.initial_ltv*100:.0f}% > "
                    f"safe limit {max_safe_ltv*100:.0f}% (LLTV={market.lltv*100:.0f}%)"
                )
                continue
            viable_markets.append(market)

        if not viable_markets:
            logger.warning("No markets viable for target LTV, using all markets")
            viable_markets = markets

        # Sort by composite score (lower = better)
        sorted_markets = sorted(viable_markets, key=lambda m: m.score)

        # First pass: greedy allocation with liquidity constraints
        for market in sorted_markets:
            if remaining_debt <= 0:
                break

            # Calculate max we can allocate to this market
            max_by_pct = total_borrow * config.max_allocation_pct
            max_by_liquidity = market.available_liquidity * Decimal("0.8")  # 80% of liquidity

            max_alloc = min(max_by_pct, max_by_liquidity, remaining_debt)

            # Check if allocation meets minimum
            min_alloc = total_borrow * config.min_allocation_pct
            if max_alloc >= min_alloc:
                allocation[market.market_id] = max_alloc
                remaining_debt -= max_alloc
            elif remaining_debt == total_borrow:
                # First market - allocate even if below min
                allocation[market.market_id] = max_alloc
                remaining_debt -= max_alloc

        # Second pass: distribute any remainder proportionally
        if remaining_debt > 0 and allocation:
            total_allocated = sum(allocation.values())
            for market_id in allocation:
                proportion = allocation[market_id] / total_allocated
                additional = remaining_debt * proportion
                allocation[market_id] += additional

        # Build positions with accurate metrics
        total_collateral = config.collateral_amount
        market_lookup = {m.market_id: m for m in markets}

        # Use real collateral price (relative to loan asset)
        # collateral_price = collateral_usd / loan_usd (e.g., WBTC/USDC = 80000)
        # Note: loan_price_usd is guaranteed > 0 by _get_collateral_price validation
        collateral_price = collateral_price_usd / loan_price_usd

        for market_id, debt_amount in allocation.items():
            market = market_lookup.get(market_id)
            if not market:
                continue

            weight = debt_amount / total_borrow if total_borrow > 0 else Decimal("0")
            collateral_amount = total_collateral * weight

            # Calculate health factor and liquidation price using real price
            hf = RiskCalculator.health_factor(
                collateral_amount=collateral_amount,
                collateral_price=collateral_price,
                borrow_amount=debt_amount,
                lltv=market.lltv,
            )
            liq_price = RiskCalculator.liquidation_price(
                collateral_amount=collateral_amount,
                borrow_amount=debt_amount,
                lltv=market.lltv,
            )

            # Calculate current LTV (debt / collateral value in loan terms)
            collateral_value = collateral_amount * collateral_price
            current_ltv = debt_amount / collateral_value if collateral_value > 0 else Decimal("0")

            # Distance to liquidation (% price drop before liquidation)
            distance_to_liq = (Decimal("1") - liq_price / collateral_price) * 100 if collateral_price > 0 else Decimal("0")

            # Margin call price (at margin_call_threshold HF)
            # HF = (collateral * price * LLTV) / borrow
            # price_at_margin = (borrow * margin_call_threshold) / (collateral * LLTV)
            margin_call_price = (debt_amount * config.margin_call_threshold) / (collateral_amount * market.lltv) if collateral_amount > 0 and market.lltv > 0 else Decimal("0")

            # Calculate interest estimates
            daily_interest = debt_amount * market.borrow_apy / 365
            monthly_interest = debt_amount * market.borrow_apy / 12
            annual_interest = debt_amount * market.borrow_apy

            position = DebtPosition(
                market_id=market.market_id,
                market_name=market.market_name,
                collateral_amount=collateral_amount,
                borrow_amount=debt_amount,
                borrow_apy=market.borrow_apy,
                health_factor=hf,
                liquidation_price=liq_price,
                current_ltv=current_ltv,
                distance_to_liquidation_pct=distance_to_liq,
                margin_call_price=margin_call_price,
                estimated_daily_interest=daily_interest,
                estimated_monthly_interest=monthly_interest,
                estimated_annual_interest=annual_interest,
                allocation_weight=weight,
            )
            positions.append(position)

        # Sort positions by allocation weight (highest first) for display
        positions.sort(key=lambda p: p.allocation_weight, reverse=True)

        return allocation, positions

    def _simulate_price_scenarios(
        self,
        collateral_amount: Decimal,
        borrow_amount: Decimal,
        current_price: Decimal,
        lltv: Decimal,
        margin_call_threshold: Decimal,
    ) -> List[RiskSnapshot]:
        """Simulate health factor at different price scenarios.

        Scenarios: -20%, -15%, -10%, -5%, 0%, +5%, +10%
        """
        scenarios = []
        price_changes = [
            Decimal("-0.20"),
            Decimal("-0.15"),
            Decimal("-0.10"),
            Decimal("-0.05"),
            Decimal("0"),
            Decimal("0.05"),
            Decimal("0.10"),
        ]

        for change in price_changes:
            scenario_price = current_price * (Decimal("1") + change)

            # Calculate HF at this price
            # HF = (collateral * price * LLTV) / borrow
            collateral_value = collateral_amount * scenario_price
            hf = (collateral_value * lltv) / borrow_amount if borrow_amount > 0 else Decimal("999")

            # Current LTV at this price
            current_ltv = borrow_amount / collateral_value if collateral_value > 0 else Decimal("0")

            # Distance to liquidation at this price
            liq_price = (borrow_amount) / (collateral_amount * lltv) if collateral_amount > 0 and lltv > 0 else Decimal("0")
            distance_to_liq = (Decimal("1") - liq_price / scenario_price) * 100 if scenario_price > 0 else Decimal("0")

            snapshot = RiskSnapshot(
                price_change_pct=change * 100,  # Convert to percentage
                collateral_price=scenario_price,
                health_factor=hf,
                current_ltv=current_ltv,
                distance_to_liquidation_pct=distance_to_liq,
                is_liquidatable=hf < Decimal("1"),
                is_margin_call=hf < margin_call_threshold,
            )
            scenarios.append(snapshot)

        return scenarios

    def _generate_position_summary(
        self,
        markets: List[MarketDebtInfo],
        positions: List[DebtPosition],
        config: RebalancingConfig,
    ) -> Optional[PositionSummary]:
        """Generate complete position summary with risk analysis."""
        if not positions:
            return None

        # Get real prices from market data
        collateral_price_usd, loan_price_usd = self._get_collateral_price(markets)

        # Aggregate position data
        total_collateral = config.collateral_amount

        # Calculate actual borrow amount in loan tokens using real prices
        collateral_value_usd = total_collateral * collateral_price_usd
        borrow_amount_usd = collateral_value_usd * config.initial_ltv
        total_borrow = borrow_amount_usd / loan_price_usd if loan_price_usd > 0 else borrow_amount_usd

        # Use weighted average of market LLTVs for aggregated metrics
        market_lookup = {m.market_id: m for m in markets}
        weighted_lltv = Decimal("0")
        weighted_apy = Decimal("0")
        total_weight = Decimal("0")

        collateral_symbol = ""
        borrow_symbol = ""

        for pos in positions:
            market = market_lookup.get(pos.market_id)
            if market:
                weighted_lltv += market.lltv * pos.allocation_weight
                weighted_apy += market.borrow_apy * pos.allocation_weight
                total_weight += pos.allocation_weight
                if not collateral_symbol:
                    collateral_symbol = market.collateral_symbol
                    borrow_symbol = market.loan_symbol

        if total_weight > 0:
            weighted_lltv /= total_weight
            weighted_apy /= total_weight

        # Current price of collateral in loan asset terms (e.g., WBTC/USDC = 80000)
        # Note: loan_price_usd is guaranteed > 0 by _get_collateral_price validation
        current_price = collateral_price_usd / loan_price_usd

        # Calculate aggregated risk metrics using correct HF formula:
        # HF = (collateral_value × LLTV) / borrow_amount
        current_ltv = config.initial_ltv
        collateral_value = total_collateral * current_price
        hf = (collateral_value * weighted_lltv) / total_borrow if total_borrow > 0 else Decimal("999")

        # Liquidation price
        liq_price = (total_borrow) / (total_collateral * weighted_lltv) if total_collateral > 0 and weighted_lltv > 0 else Decimal("0")

        # Distance to liquidation
        distance_to_liq = (Decimal("1") - liq_price / current_price) * 100 if current_price > 0 else Decimal("0")

        # Margin call price
        margin_call_price = (total_borrow * config.margin_call_threshold) / (total_collateral * weighted_lltv) if total_collateral > 0 and weighted_lltv > 0 else Decimal("0")

        # Interest estimates
        daily_interest = total_borrow * weighted_apy / 365
        monthly_interest = total_borrow * weighted_apy / 12
        annual_interest = total_borrow * weighted_apy

        # Generate price scenarios
        price_scenarios = self._simulate_price_scenarios(
            collateral_amount=total_collateral,
            borrow_amount=total_borrow,
            current_price=current_price,
            lltv=weighted_lltv,
            margin_call_threshold=config.margin_call_threshold,
        )

        # Generate alerts
        alerts = []
        if hf < config.min_health_factor:
            alerts.append(f"WARNING: Health Factor {hf:.2f} below minimum {config.min_health_factor}")
        if hf < config.margin_call_threshold:
            alerts.append(f"ALERT: Health Factor {hf:.2f} below margin call threshold {config.margin_call_threshold}")
        if current_ltv > weighted_lltv * Decimal("0.90"):
            alerts.append(f"WARNING: LTV {current_ltv*100:.0f}% approaching liquidation threshold")
        if distance_to_liq < Decimal("10"):
            alerts.append(f"CRITICAL: Only {distance_to_liq:.1f}% price drop to liquidation")

        # Check price scenarios for margin call alerts
        for scenario in price_scenarios:
            if scenario.is_margin_call and scenario.price_change_pct >= Decimal("-10"):
                alerts.append(
                    f"ALERT: {scenario.price_change_pct:.0f}% price drop triggers margin call (HF={scenario.health_factor:.2f})"
                )
                break

        return PositionSummary(
            collateral_asset=config.collateral_asset,
            collateral_symbol=collateral_symbol,
            collateral_amount=total_collateral,
            borrow_asset=config.borrow_asset,
            borrow_symbol=borrow_symbol,
            borrow_amount=total_borrow,
            collateral_price=current_price,
            initial_ltv=config.initial_ltv,
            current_ltv=current_ltv,
            max_ltv=weighted_lltv,
            health_factor=hf,
            liquidation_price=liq_price,
            distance_to_liquidation_pct=distance_to_liq,
            margin_call_price=margin_call_price,
            margin_call_threshold=config.margin_call_threshold,
            borrow_apy=weighted_apy,
            estimated_daily_interest=daily_interest,
            estimated_monthly_interest=monthly_interest,
            estimated_annual_interest=annual_interest,
            price_scenarios=price_scenarios,
            alerts=alerts,
        )

    def _generate_opportunities(
        self,
        markets: List[MarketDebtInfo],
        current_positions: List[DebtPosition],
        config: RebalancingConfig,
    ) -> List[RebalancingOpportunity]:
        """Generate rebalancing opportunities with cost/benefit analysis."""
        opportunities = []

        if len(markets) < 2:
            return opportunities

        # Build market lookup
        market_lookup = {m.market_id: m for m in markets}

        # For each position, check if moving to a cheaper market is beneficial
        for position in current_positions:
            from_market = market_lookup.get(position.market_id)
            if not from_market:
                continue

            # Find cheaper markets
            for to_market in markets:
                if to_market.market_id == position.market_id:
                    continue

                # Calculate rate difference
                rate_diff = from_market.borrow_apy - to_market.borrow_apy
                rate_diff_bps = rate_diff * 10000  # Convert to basis points

                # Skip if difference below threshold
                if rate_diff_bps < config.rate_threshold_bps:
                    continue

                # Check if destination has liquidity
                if to_market.available_liquidity < position.borrow_amount:
                    continue

                # Calculate costs
                gas_cost = config.gas_cost_usd
                slippage_cost = position.borrow_amount * config.slippage_bps / 10000
                total_cost = gas_cost + slippage_cost

                # Calculate benefits
                annual_savings = position.borrow_amount * rate_diff
                monthly_savings = annual_savings / 12
                daily_savings = annual_savings / 365

                # Breakeven analysis
                breakeven_days = total_cost / daily_savings if daily_savings > 0 else Decimal("999")
                net_benefit_30d = monthly_savings - total_cost

                # Score the opportunity
                score = net_benefit_30d / config.total_debt * 10000 if config.total_debt > 0 else Decimal("0")

                opp = RebalancingOpportunity(
                    trigger=RebalancingTrigger.RATE_DIFF,
                    from_market_id=from_market.market_id,
                    from_market_name=from_market.market_name,
                    to_market_id=to_market.market_id,
                    to_market_name=to_market.market_name,
                    debt_amount=position.borrow_amount,
                    collateral_amount=position.collateral_amount,
                    from_rate=from_market.borrow_apy,
                    to_rate=to_market.borrow_apy,
                    rate_diff_bps=rate_diff_bps,
                    estimated_gas_cost=gas_cost,
                    estimated_slippage_cost=slippage_cost,
                    total_cost=total_cost,
                    annual_savings=annual_savings,
                    monthly_savings=monthly_savings,
                    daily_savings=daily_savings,
                    breakeven_days=breakeven_days,
                    net_benefit_30d=net_benefit_30d,
                    opportunity_score=score,
                )
                opportunities.append(opp)

        # Sort by score (best first)
        opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)

        return opportunities

    async def _run_simulation(
        self,
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
    ) -> Tuple[List[RebalancingSnapshot], List[RebalancingSnapshot]]:
        """Run historical simulation with rebalancing vs static benchmark."""

        # Fetch timeseries data for all markets
        market_timeseries: Dict[str, List[TimeseriesPoint]] = {}
        for market in markets:
            try:
                timeseries = await self.data.get_market_timeseries(
                    protocol=config.protocol,
                    market_id=market.market_id,
                    interval=config.simulation_interval,
                    days=config.simulation_days,
                )
                if timeseries:
                    market_timeseries[market.market_id] = timeseries
            except Exception as e:
                logger.warning(f"Error fetching timeseries for {market.market_name}: {e}")

        if not market_timeseries:
            logger.warning("No timeseries data available for simulation")
            return [], []

        # Fetch historical price data for first market
        price_history: Dict[datetime, Decimal] = {}
        if markets:
            try:
                price_points = await self.data.get_price_history(
                    protocol=config.protocol,
                    market_id=markets[0].market_id,
                    interval=config.simulation_interval,
                    days=config.simulation_days,
                )
                for pp in price_points:
                    price_history[pp.timestamp] = pp.price
                logger.info(f"Loaded {len(price_history)} price history points")
            except Exception as e:
                logger.warning(f"Could not load price history, using fallback: {e}")

        # Align timeseries
        aligned_data = self._align_timeseries(market_timeseries)
        if not aligned_data:
            return [], []

        timestamps = sorted(aligned_data.keys())

        # Run optimized strategy (with rebalancing and dynamic prices)
        strategy_snapshots = self._simulate_with_rebalancing(
            aligned_data, timestamps, markets, config, price_history
        )

        # Run benchmark (static allocation to best market)
        benchmark_snapshots = self._simulate_benchmark(
            aligned_data, timestamps, markets, config, price_history
        )

        return strategy_snapshots, benchmark_snapshots

    def _align_timeseries(
        self,
        market_timeseries: Dict[str, List[TimeseriesPoint]],
    ) -> Dict[datetime, Dict[str, TimeseriesPoint]]:
        """Align timeseries across markets by timestamp."""
        all_timestamps = set()
        for points in market_timeseries.values():
            for point in points:
                all_timestamps.add(point.timestamp)

        aligned = {}
        for ts in sorted(all_timestamps):
            points_at_ts = {}
            for market_id, points in market_timeseries.items():
                for point in points:
                    if point.timestamp == ts:
                        points_at_ts[market_id] = point
                        break

            # Include timestamps where at least one market has data
            if points_at_ts:
                aligned[ts] = points_at_ts

        return aligned

    def _interpolate_price(
        self,
        ts: datetime,
        timestamps: List[datetime],
        price_history: Dict[datetime, Decimal],
        initial_price: Decimal,
    ) -> Decimal:
        """Interpolate price linearly between known data points.

        If price_history is empty or ts is outside range, simulates
        price movement with small linear drift.
        """
        if not price_history:
            # No history - simulate linear price movement
            # Small drift based on hours elapsed (more realistic than day-based)
            if timestamps:
                hours_elapsed = (ts - timestamps[0]).total_seconds() / 3600
                # Simulate ±1% monthly drift = ±0.00139% per hour
                drift_per_hour = Decimal("0.0000139")
                # Use sin-like pattern for oscillation
                import math
                oscillation = Decimal(str(math.sin(hours_elapsed / 24 * math.pi)))
                drift = drift_per_hour * Decimal(str(hours_elapsed)) * oscillation
                return initial_price * (Decimal("1") + drift)
            return initial_price

        # If exact timestamp exists, return it
        if ts in price_history:
            return price_history[ts]

        # Find surrounding timestamps for interpolation
        sorted_ts = sorted(price_history.keys())

        # Before first known price
        if ts < sorted_ts[0]:
            return price_history[sorted_ts[0]]

        # After last known price
        if ts > sorted_ts[-1]:
            return price_history[sorted_ts[-1]]

        # Find bracketing timestamps
        prev_ts = sorted_ts[0]
        next_ts = sorted_ts[-1]

        for i, known_ts in enumerate(sorted_ts):
            if known_ts > ts:
                next_ts = known_ts
                prev_ts = sorted_ts[i - 1] if i > 0 else known_ts
                break

        # Linear interpolation
        if prev_ts == next_ts:
            return price_history[prev_ts]

        prev_price = price_history[prev_ts]
        next_price = price_history[next_ts]

        # t = (ts - prev) / (next - prev)
        total_seconds = (next_ts - prev_ts).total_seconds()
        elapsed_seconds = (ts - prev_ts).total_seconds()
        t = Decimal(str(elapsed_seconds / total_seconds)) if total_seconds > 0 else Decimal("0")

        # interpolated = prev + t * (next - prev)
        interpolated_price = prev_price + t * (next_price - prev_price)
        return interpolated_price

    def _simulate_with_rebalancing(
        self,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
        price_history: Optional[Dict[datetime, Decimal]] = None,
    ) -> List[RebalancingSnapshot]:
        """Simulate with dynamic rebalancing based on market conditions.

        Rebalancing modes:
        - STATIC_THRESHOLD: Fixed rate difference threshold
        - DYNAMIC_RATE: Adapts threshold based on rate volatility
        - PREDICTIVE: Uses utilization trends to anticipate rate changes
        - OPPORTUNITY_COST: Only rebalance when savings exceed costs

        Enhanced features:
        - Dynamic price evolution during simulation
        - Compound interest on debt
        - Health factor recalculation at each step
        - Margin call tracking
        """
        snapshots = []
        market_lookup = {m.market_id: m for m in markets}

        # Get initial prices
        collateral_price_usd, loan_price_usd = self._get_collateral_price(markets)
        initial_price = collateral_price_usd / loan_price_usd if loan_price_usd > 0 else collateral_price_usd

        # Start with optimal allocation
        _, initial_positions = self._calculate_optimal_allocation(markets, config)
        current_positions = {p.market_id: p for p in initial_positions}

        # Initialize per-position debt tracking (each position accrues interest independently)
        # This is more accurate than uniform scaling after rebalancing
        position_debts: Dict[str, Decimal] = {p.market_id: p.borrow_amount for p in initial_positions}
        initial_debt = sum(position_debts.values())
        current_debt = initial_debt

        cumulative_interest = Decimal("0")
        cumulative_rebalance_cost = Decimal("0")
        last_rebalance_ts = timestamps[0] if timestamps else None

        # Track rate history for dynamic analysis
        rate_history: Dict[str, List[Decimal]] = {m.market_id: [] for m in markets}

        # Get weighted LLTV for HF calculation
        weighted_lltv = Decimal("0")
        total_weight = Decimal("0")
        for pos in initial_positions:
            market = market_lookup.get(pos.market_id)
            if market:
                weighted_lltv += market.lltv * pos.allocation_weight
                total_weight += pos.allocation_weight
        if total_weight > 0:
            weighted_lltv /= total_weight

        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]

            # Get current collateral price with linear interpolation
            current_price = self._interpolate_price(
                ts=ts,
                timestamps=timestamps,
                price_history=price_history or {},
                initial_price=initial_price,
            )

            # Update rate history
            for market_id, point in market_points.items():
                if market_id in rate_history:
                    rate_history[market_id].append(point.borrow_apy)
                    # Keep only last lookback_periods
                    if len(rate_history[market_id]) > config.lookback_periods:
                        rate_history[market_id] = rate_history[market_id][-config.lookback_periods:]

            # Calculate compound interest per position (more accurate than uniform scaling)
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                period_interest = Decimal("0")

                for market_id in list(position_debts.keys()):
                    if market_id in market_points:
                        # Get current rate for this market
                        current_rate = market_points[market_id].borrow_apy
                        # Compound interest: debt(t) = debt(t-1) * (1 + rate * dt)
                        period_rate = current_rate * Decimal(str(hours_elapsed / 8760))
                        interest = position_debts[market_id] * period_rate
                        position_debts[market_id] += interest
                        period_interest += interest

                current_debt = sum(position_debts.values())
                cumulative_interest += period_interest

            # Update positions with current rates and recalculate HF
            updated_positions = []
            weighted_rate_sum = Decimal("0")
            total_debt = Decimal("0")

            for market_id, position in current_positions.items():
                if market_id in market_points:
                    point = market_points[market_id]
                    market = market_lookup.get(market_id)
                    lltv = market.lltv if market else Decimal("0.86")

                    # Use actual tracked debt for this position (with compound interest)
                    actual_borrow = position_debts.get(market_id, position.borrow_amount)

                    # Recalculate health factor with current price
                    # HF = (collateral * price * LLTV) / borrow
                    collateral_value = position.collateral_amount * current_price
                    hf = (collateral_value * lltv) / actual_borrow if actual_borrow > 0 else Decimal("999")

                    # Recalculate liquidation price
                    liq_price = actual_borrow / (position.collateral_amount * lltv) if position.collateral_amount > 0 and lltv > 0 else Decimal("0")

                    position = DebtPosition(
                        market_id=position.market_id,
                        market_name=position.market_name,
                        collateral_amount=position.collateral_amount,
                        borrow_amount=actual_borrow,
                        borrow_apy=point.borrow_apy,
                        health_factor=hf,
                        liquidation_price=liq_price,
                        allocation_weight=position.allocation_weight,
                    )
                    weighted_rate_sum += position.borrow_amount * point.borrow_apy
                    total_debt += position.borrow_amount
                    updated_positions.append(position)
                    current_positions[market_id] = position

            weighted_borrow_apy = weighted_rate_sum / total_debt if total_debt > 0 else Decimal("0")

            # Calculate aggregate health factor
            collateral_value = config.collateral_amount * current_price
            current_hf = (collateral_value * weighted_lltv) / current_debt if current_debt > 0 else Decimal("999")

            # Check for margin call
            margin_call_triggered = current_hf < config.margin_call_threshold

            # Check for rebalancing trigger based on mode
            rebalanced = False
            trigger = None

            if i > 0 and last_rebalance_ts and updated_positions:
                should_rebalance, trigger = self._check_rebalance_trigger(
                    config=config,
                    positions=updated_positions,
                    market_points=market_points,
                    rate_history=rate_history,
                    market_lookup=market_lookup,
                    hours_since_last=(ts - last_rebalance_ts).total_seconds() / 3600,
                )

                # Also trigger rebalancing on margin call if HF approaches danger zone
                if current_hf < config.min_health_factor and not should_rebalance:
                    should_rebalance = True
                    trigger = RebalancingTrigger.HEALTH_FACTOR

                if should_rebalance:
                    rebalanced = True
                    cumulative_rebalance_cost += config.gas_cost_usd
                    last_rebalance_ts = ts

                    # Preserve total accumulated debt before rebalancing
                    total_accumulated_debt = sum(position_debts.values())

                    # Create a copy of markets with current rates (avoid mutating original)
                    markets_copy = []
                    for market in markets:
                        market_copy = MarketDebtInfo(
                            market_id=market.market_id,
                            market_name=market.market_name,
                            collateral_symbol=market.collateral_symbol,
                            loan_symbol=market.loan_symbol,
                            collateral_address=market.collateral_address,
                            loan_address=market.loan_address,
                            borrow_apy=market_points[market.market_id].borrow_apy if market.market_id in market_points else market.borrow_apy,
                            supply_apy=market.supply_apy,
                            utilization=market_points[market.market_id].utilization if market.market_id in market_points else market.utilization,
                            lltv=market.lltv,
                            available_liquidity=market.available_liquidity,
                            total_borrow=market.total_borrow,
                            tvl=market.tvl,
                            effective_max_leverage=market.effective_max_leverage,
                            safe_leverage_at_lltv=market.safe_leverage_at_lltv,
                            rate_volatility_24h=market.rate_volatility_24h,
                            rate_trend=market.rate_trend,
                            predicted_rate_1d=market.predicted_rate_1d,
                            predicted_rate_7d=market.predicted_rate_7d,
                            score=market.score,
                            rate_score=market.rate_score,
                            risk_score=market.risk_score,
                            liquidity_score=market.liquidity_score,
                        )
                        markets_copy.append(market_copy)

                    _, new_positions = self._calculate_optimal_allocation(markets_copy, config)

                    # Redistribute the accumulated debt proportionally to new allocations
                    # (instead of using initial debt amounts from _calculate_optimal_allocation)
                    new_total_debt = sum(p.borrow_amount for p in new_positions)
                    position_debts.clear()
                    current_positions.clear()

                    for pos in new_positions:
                        # Scale position's debt by the ratio of accumulated to initial
                        scaled_debt = pos.borrow_amount * (total_accumulated_debt / new_total_debt) if new_total_debt > 0 else pos.borrow_amount
                        position_debts[pos.market_id] = scaled_debt

                        # Update position with scaled debt
                        scaled_pos = DebtPosition(
                            market_id=pos.market_id,
                            market_name=pos.market_name,
                            collateral_amount=pos.collateral_amount,
                            borrow_amount=scaled_debt,
                            borrow_apy=pos.borrow_apy,
                            health_factor=pos.health_factor,
                            liquidation_price=pos.liquidation_price,
                            allocation_weight=pos.allocation_weight,
                        )
                        current_positions[pos.market_id] = scaled_pos

                    updated_positions = list(current_positions.values())
                    current_debt = total_accumulated_debt

            snapshot = RebalancingSnapshot(
                timestamp=ts,
                positions=updated_positions,
                total_debt=current_debt,
                total_collateral=config.collateral_amount,
                weighted_borrow_apy=weighted_borrow_apy,
                cumulative_interest=cumulative_interest,
                cumulative_rebalance_cost=cumulative_rebalance_cost,
                rebalanced=rebalanced,
                rebalance_trigger=trigger,
                collateral_price=current_price,
                current_health_factor=current_hf,
                margin_call_triggered=margin_call_triggered,
            )
            snapshots.append(snapshot)

        return snapshots

    def _check_rebalance_trigger(
        self,
        config: RebalancingConfig,
        positions: List[DebtPosition],
        market_points: Dict[str, TimeseriesPoint],
        rate_history: Dict[str, List[Decimal]],
        market_lookup: Dict[str, MarketDebtInfo],
        hours_since_last: float,
    ) -> Tuple[bool, Optional[RebalancingTrigger]]:
        """Check if rebalancing should be triggered based on mode.

        Returns: (should_rebalance, trigger_type)
        """
        # Get current rates
        current_rates = {p.market_id: p.borrow_apy for p in positions}
        if not current_rates:
            return False, None

        rate_spread_bps = (max(current_rates.values()) - min(current_rates.values())) * 10000

        # Find best available market rate
        best_available_rate = min(
            (market_points[mid].borrow_apy for mid in market_points if mid in market_lookup),
            default=None
        )

        if best_available_rate is None:
            return False, None

        # Current weighted rate
        total_debt = sum(p.borrow_amount for p in positions)
        weighted_rate = sum(p.borrow_amount * p.borrow_apy for p in positions) / total_debt if total_debt > 0 else Decimal("0")

        # Potential savings from rebalancing
        potential_savings_rate = weighted_rate - best_available_rate
        potential_annual_savings = total_debt * potential_savings_rate
        potential_daily_savings = potential_annual_savings / 365

        # Cost of rebalancing
        total_cost = config.gas_cost_usd + (total_debt * config.slippage_bps / 10000)

        # Check based on mode
        if config.rebalancing_mode == RebalancingMode.STATIC_THRESHOLD:
            # Simple: trigger when rate spread exceeds threshold
            if rate_spread_bps >= config.rate_threshold_bps:
                return True, RebalancingTrigger.RATE_DIFF
            return False, None

        elif config.rebalancing_mode == RebalancingMode.DYNAMIC_RATE:
            # Adapt threshold based on rate volatility
            # Higher volatility = higher threshold (avoid noise)
            volatilities = []
            for market_id, history in rate_history.items():
                if len(history) > 1:
                    vol = Decimal(str(statistics.stdev([float(r) for r in history])))
                    volatilities.append(vol)

            avg_volatility = Decimal(str(statistics.mean([float(v) for v in volatilities]))) if volatilities else Decimal("0")

            # Dynamic threshold = base threshold * (1 + volatility_factor)
            # Higher volatility -> higher threshold -> less frequent rebalancing
            volatility_factor = min(Decimal("2"), avg_volatility * 100)  # Cap at 2x
            dynamic_threshold = config.rate_threshold_bps * (Decimal("1") + volatility_factor)

            if rate_spread_bps >= dynamic_threshold:
                return True, RebalancingTrigger.RATE_DIFF

            # Also check for utilization alerts
            for pos in positions:
                if pos.market_id in market_points:
                    util = market_points[pos.market_id].utilization
                    if util > config.utilization_alert_threshold:
                        # High utilization in current position - rates likely to spike
                        return True, RebalancingTrigger.RATE_DIFF

            return False, None

        elif config.rebalancing_mode == RebalancingMode.PREDICTIVE:
            # Use rate trends and utilization to anticipate changes
            # Check if any current position is in a market with rising rates
            for pos in positions:
                if pos.market_id in rate_history and len(rate_history[pos.market_id]) >= 6:
                    recent = rate_history[pos.market_id][-6:]  # Last 6 periods
                    older = rate_history[pos.market_id][:-6] if len(rate_history[pos.market_id]) > 6 else rate_history[pos.market_id][:3]

                    if recent and older:
                        recent_avg = sum(recent) / len(recent)
                        older_avg = sum(older) / len(older)

                        # If rate is trending up significantly (>5% increase)
                        if older_avg > 0 and (recent_avg - older_avg) / older_avg > Decimal("0.05"):
                            # Check if there's a better market
                            if best_available_rate < pos.borrow_apy * Decimal("0.95"):
                                return True, RebalancingTrigger.RATE_DIFF

                # Check utilization trend
                if pos.market_id in market_points:
                    util = market_points[pos.market_id].utilization
                    if util > Decimal("0.85"):
                        # Getting close to high utilization zone
                        if best_available_rate < pos.borrow_apy:
                            return True, RebalancingTrigger.RATE_DIFF

            return False, None

        elif config.rebalancing_mode == RebalancingMode.OPPORTUNITY_COST:
            # Only rebalance when net benefit is positive within reasonable timeframe
            # Breakeven days = cost / daily_savings
            if potential_daily_savings > 0:
                breakeven_days = total_cost / potential_daily_savings

                # Rebalance if we break even within 30 days
                if breakeven_days <= 30 and potential_annual_savings > config.min_savings_to_rebalance:
                    return True, RebalancingTrigger.RATE_DIFF

            return False, None

        # Default: static threshold
        if rate_spread_bps >= config.rate_threshold_bps:
            return True, RebalancingTrigger.RATE_DIFF
        return False, None

    def _simulate_benchmark(
        self,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
        price_history: Optional[Dict[datetime, Decimal]] = None,
    ) -> List[RebalancingSnapshot]:
        """Simulate static allocation to lowest-rate market with dynamic prices."""
        snapshots = []

        # Get initial prices
        collateral_price_usd, loan_price_usd = self._get_collateral_price(markets)
        initial_price = collateral_price_usd / loan_price_usd if loan_price_usd > 0 else collateral_price_usd

        # Find market with lowest initial rate
        best_market = min(markets, key=lambda m: m.borrow_apy)

        # Calculate initial borrow amount using real prices
        collateral_value_usd = config.collateral_amount * collateral_price_usd
        borrow_amount_usd = collateral_value_usd * config.initial_ltv
        initial_borrow = borrow_amount_usd / loan_price_usd if loan_price_usd > 0 else borrow_amount_usd
        current_debt = initial_borrow

        # Create single position in best market
        position = DebtPosition(
            market_id=best_market.market_id,
            market_name=best_market.market_name,
            collateral_amount=config.collateral_amount,
            borrow_amount=initial_borrow,
            borrow_apy=best_market.borrow_apy,
            health_factor=Decimal("1.5"),
            liquidation_price=Decimal("0.9"),
            allocation_weight=Decimal("1"),
        )

        cumulative_interest = Decimal("0")

        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]

            # Get current price with linear interpolation
            current_price = self._interpolate_price(
                ts=ts,
                timestamps=timestamps,
                price_history=price_history or {},
                initial_price=initial_price,
            )

            # Update rate if data available
            current_rate = position.borrow_apy
            if best_market.market_id in market_points:
                current_rate = market_points[best_market.market_id].borrow_apy

            # Calculate compound interest
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                period_rate = current_rate * Decimal(str(hours_elapsed / 8760))
                interest_accrued = current_debt * period_rate
                current_debt += interest_accrued
                cumulative_interest += interest_accrued

            # Calculate health factor with current price
            collateral_value = config.collateral_amount * current_price
            current_hf = (collateral_value * best_market.lltv) / current_debt if current_debt > 0 else Decimal("999")
            liq_price = current_debt / (config.collateral_amount * best_market.lltv) if config.collateral_amount > 0 and best_market.lltv > 0 else Decimal("0")

            updated_position = DebtPosition(
                market_id=position.market_id,
                market_name=position.market_name,
                collateral_amount=position.collateral_amount,
                borrow_amount=current_debt,
                borrow_apy=current_rate,
                health_factor=current_hf,
                liquidation_price=liq_price,
                allocation_weight=position.allocation_weight,
            )

            # Check for margin call
            margin_call_triggered = current_hf < config.margin_call_threshold

            snapshot = RebalancingSnapshot(
                timestamp=ts,
                positions=[updated_position],
                total_debt=current_debt,
                total_collateral=config.collateral_amount,
                weighted_borrow_apy=current_rate,
                cumulative_interest=cumulative_interest,
                cumulative_rebalance_cost=Decimal("0"),
                rebalanced=False,
                rebalance_trigger=None,
                collateral_price=current_price,
                current_health_factor=current_hf,
                margin_call_triggered=margin_call_triggered,
            )
            snapshots.append(snapshot)

        return snapshots

    def _calculate_metrics(
        self,
        snapshots: List[RebalancingSnapshot],
        benchmark_snapshots: List[RebalancingSnapshot],
        config: RebalancingConfig,
    ) -> RebalancingMetrics:
        """Calculate aggregated metrics from simulation."""
        if not snapshots:
            return RebalancingMetrics(
                total_interest_paid=Decimal("0"),
                benchmark_interest_paid=Decimal("0"),
                interest_savings=Decimal("0"),
                interest_savings_pct=Decimal("0"),
                avg_weighted_borrow_apy=Decimal("0"),
                min_weighted_borrow_apy=Decimal("0"),
                max_weighted_borrow_apy=Decimal("0"),
                benchmark_avg_borrow_apy=Decimal("0"),
                rebalance_count=0,
                total_rebalance_cost=Decimal("0"),
                avg_rate_diff_trigger_bps=Decimal("0"),
                net_savings=Decimal("0"),
                net_savings_annualized=Decimal("0"),
                simulation_days=0,
                data_points=0,
            )

        # Interest
        total_interest = snapshots[-1].cumulative_interest
        benchmark_interest = benchmark_snapshots[-1].cumulative_interest if benchmark_snapshots else total_interest
        interest_savings = benchmark_interest - total_interest
        savings_pct = (interest_savings / benchmark_interest * 100) if benchmark_interest > 0 else Decimal("0")

        # Rates
        rates = [float(s.weighted_borrow_apy) for s in snapshots]
        avg_rate = Decimal(str(statistics.mean(rates))) if rates else Decimal("0")
        min_rate = Decimal(str(min(rates))) if rates else Decimal("0")
        max_rate = Decimal(str(max(rates))) if rates else Decimal("0")

        benchmark_rates = [float(s.weighted_borrow_apy) for s in benchmark_snapshots]
        benchmark_avg = Decimal(str(statistics.mean(benchmark_rates))) if benchmark_rates else Decimal("0")

        # Rebalancing stats
        rebalance_count = sum(1 for s in snapshots if s.rebalanced)
        total_rebalance_cost = snapshots[-1].cumulative_rebalance_cost if snapshots else Decimal("0")

        # Net savings
        net_savings = interest_savings - total_rebalance_cost

        # Annualize
        days = max(1, (snapshots[-1].timestamp - snapshots[0].timestamp).days) if snapshots else 1
        net_savings_ann = net_savings * Decimal("365") / Decimal(str(days))

        return RebalancingMetrics(
            total_interest_paid=total_interest,
            benchmark_interest_paid=benchmark_interest,
            interest_savings=interest_savings,
            interest_savings_pct=savings_pct,
            avg_weighted_borrow_apy=avg_rate,
            min_weighted_borrow_apy=min_rate,
            max_weighted_borrow_apy=max_rate,
            benchmark_avg_borrow_apy=benchmark_avg,
            rebalance_count=rebalance_count,
            total_rebalance_cost=total_rebalance_cost,
            avg_rate_diff_trigger_bps=config.rate_threshold_bps,
            net_savings=net_savings,
            net_savings_annualized=net_savings_ann,
            simulation_days=days,
            data_points=len(snapshots),
        )
