"""Debt rebalancing optimizer for lending markets."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import statistics

from src.sandbox.models.rebalancing import (
    RebalancingConfig,
    RebalancingTrigger,
    MarketDebtInfo,
    DebtPosition,
    RebalancingOpportunity,
    RebalancingSnapshot,
    RebalancingMetrics,
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

    def __init__(self, data: DataAggregator):
        self.data = data
        self._market_cache: Dict[str, Market] = {}

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
            f"debt={config.total_debt}, leverage={config.target_leverage}x"
        )

        start_time = datetime.utcnow()

        try:
            # 1. Discover available markets
            markets = await self._discover_markets(config)
            if not markets:
                return RebalancingResult(
                    config=config,
                    start_time=start_time,
                    end_time=datetime.utcnow(),
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

            end_time = datetime.utcnow()

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
                end_time=datetime.utcnow(),
                success=False,
                error_message=str(e),
            )

    async def _discover_markets(
        self,
        config: RebalancingConfig,
    ) -> List[Market]:
        """Find markets matching the collateral/borrow pair."""
        markets = await self.data.find_markets_by_pair(
            protocol=config.protocol,
            collateral_symbol=config.collateral_asset,
            loan_symbol=config.borrow_asset,
        )

        # Filter by reasonable TVL and liquidity
        valid_markets = []
        for m in markets:
            # Minimum TVL threshold
            if float(m.tvl) < 100_000:
                continue

            # Must have available liquidity
            available = float(m.state.available_liquidity) if m.state else 0
            if available < 10_000:
                continue

            # Reasonable borrow APY (not broken/extreme)
            if float(m.borrow_apy) > 0.5:  # > 50% APY seems broken
                continue

            valid_markets.append(m)
            self._market_cache[m.id] = m

        return valid_markets

    async def _analyze_markets(
        self,
        markets: List[Market],
        config: RebalancingConfig,
    ) -> List[MarketDebtInfo]:
        """Analyze markets with rate predictions and scoring."""
        analyzed = []

        for market in markets:
            # Get current state
            state = market.state
            available = state.available_liquidity if state else Decimal("0")
            total_borrow = state.total_borrow_assets if state else Decimal("0")

            # Calculate predicted rates using IRM analysis
            # For high utilization (>90%), rates tend to increase
            # For lower utilization, rates are more stable
            utilization = float(market.utilization)
            predicted_1d = market.borrow_apy
            predicted_7d = market.borrow_apy

            if utilization > 0.9:
                # High utilization - expect rate increase
                predicted_1d = market.borrow_apy * Decimal("1.05")
                predicted_7d = market.borrow_apy * Decimal("1.15")
            elif utilization > 0.8:
                # Medium-high utilization
                predicted_1d = market.borrow_apy * Decimal("1.02")
                predicted_7d = market.borrow_apy * Decimal("1.05")

            # Calculate score (lower = better)
            # Score = borrow_apy * (1 + utilization_penalty) - liquidity_bonus
            utilization_penalty = Decimal(str(max(0, utilization - 0.8)))
            liquidity_ratio = min(Decimal("1"), available / config.total_debt) if config.total_debt > 0 else Decimal("1")
            liquidity_bonus = liquidity_ratio * Decimal("0.01")

            score = market.borrow_apy * (Decimal("1") + utilization_penalty) - liquidity_bonus

            info = MarketDebtInfo(
                market_id=market.id,
                market_name=market.name,
                collateral_symbol=market.collateral_asset_symbol,
                loan_symbol=market.loan_asset_symbol,
                borrow_apy=market.borrow_apy,
                supply_apy=market.supply_apy,
                utilization=market.utilization,
                lltv=market.lltv,
                available_liquidity=available,
                total_borrow=total_borrow,
                tvl=market.tvl,
                predicted_rate_1d=predicted_1d,
                predicted_rate_7d=predicted_7d,
                score=score,
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
        Calculate optimal debt allocation using greedy algorithm.

        Algorithm:
        1. Sort markets by borrow_apy (ascending)
        2. For each market:
           - max_alloc = min(max_pct, liquidity * 0.8, remaining_debt)
           - If max_alloc >= min_pct: allocate
        3. Distribute remainder proportionally
        """
        allocation: Dict[str, Decimal] = {}
        positions: List[DebtPosition] = []
        remaining_debt = config.total_debt

        # Sort by borrow APY (lowest first)
        sorted_markets = sorted(markets, key=lambda m: m.borrow_apy)

        # First pass: greedy allocation
        for market in sorted_markets:
            if remaining_debt <= 0:
                break

            # Calculate max we can allocate to this market
            max_by_pct = config.total_debt * config.max_allocation_pct
            max_by_liquidity = market.available_liquidity * Decimal("0.8")  # 80% of liquidity
            max_alloc = min(max_by_pct, max_by_liquidity, remaining_debt)

            # Check if allocation meets minimum
            min_alloc = config.total_debt * config.min_allocation_pct
            if max_alloc >= min_alloc:
                allocation[market.market_id] = max_alloc
                remaining_debt -= max_alloc
            elif remaining_debt == config.total_debt:
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

        # Build positions
        total_collateral = config.required_collateral
        total_debt = config.total_debt

        for market in sorted_markets:
            if market.market_id not in allocation:
                continue

            debt_amount = allocation[market.market_id]
            weight = debt_amount / total_debt if total_debt > 0 else Decimal("0")
            collateral_amount = total_collateral * weight

            # Calculate health factor and liquidation price
            collateral_price = Decimal("1.0")  # Simplified for same-asset pairs
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

            position = DebtPosition(
                market_id=market.market_id,
                market_name=market.market_name,
                collateral_amount=collateral_amount,
                borrow_amount=debt_amount,
                borrow_apy=market.borrow_apy,
                health_factor=hf,
                liquidation_price=liq_price,
                allocation_weight=weight,
            )
            positions.append(position)

        return allocation, positions

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

        # Align timeseries
        aligned_data = self._align_timeseries(market_timeseries)
        if not aligned_data:
            return [], []

        timestamps = sorted(aligned_data.keys())

        # Run optimized strategy (with rebalancing)
        strategy_snapshots = self._simulate_with_rebalancing(
            aligned_data, timestamps, markets, config
        )

        # Run benchmark (static allocation to best market)
        benchmark_snapshots = self._simulate_benchmark(
            aligned_data, timestamps, markets, config
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

    def _simulate_with_rebalancing(
        self,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
    ) -> List[RebalancingSnapshot]:
        """Simulate with dynamic rebalancing."""
        snapshots = []
        market_lookup = {m.market_id: m for m in markets}

        # Start with optimal allocation
        _, initial_positions = self._calculate_optimal_allocation(markets, config)
        current_positions = {p.market_id: p for p in initial_positions}

        cumulative_interest = Decimal("0")
        cumulative_rebalance_cost = Decimal("0")
        last_rebalance_ts = timestamps[0] if timestamps else None

        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]

            # Update positions with current rates
            updated_positions = []
            weighted_rate_sum = Decimal("0")
            total_debt = Decimal("0")

            for market_id, position in current_positions.items():
                if market_id in market_points:
                    point = market_points[market_id]
                    position = DebtPosition(
                        market_id=position.market_id,
                        market_name=position.market_name,
                        collateral_amount=position.collateral_amount,
                        borrow_amount=position.borrow_amount,
                        borrow_apy=point.borrow_apy,
                        health_factor=position.health_factor,
                        liquidation_price=position.liquidation_price,
                        allocation_weight=position.allocation_weight,
                    )
                    weighted_rate_sum += position.borrow_amount * point.borrow_apy
                    total_debt += position.borrow_amount
                    updated_positions.append(position)
                    current_positions[market_id] = position

            weighted_borrow_apy = weighted_rate_sum / total_debt if total_debt > 0 else Decimal("0")

            # Check for rebalancing trigger
            rebalanced = False
            trigger = None

            if i > 0 and last_rebalance_ts:
                # Find best and worst rates among current positions
                rates = [p.borrow_apy for p in updated_positions]
                if rates:
                    rate_spread_bps = (max(rates) - min(rates)) * 10000
                    if rate_spread_bps >= config.rate_threshold_bps:
                        rebalanced = True
                        trigger = RebalancingTrigger.RATE_DIFF
                        cumulative_rebalance_cost += config.gas_cost_usd
                        last_rebalance_ts = ts

                        # Recalculate optimal allocation with current rates
                        # Update market info with current rates
                        for market in markets:
                            if market.market_id in market_points:
                                market.borrow_apy = market_points[market.market_id].borrow_apy

                        _, new_positions = self._calculate_optimal_allocation(markets, config)
                        current_positions = {p.market_id: p for p in new_positions}

            # Calculate interest for this period
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                period_interest = total_debt * weighted_borrow_apy * Decimal(str(hours_elapsed / 8760))
                cumulative_interest += period_interest

            snapshot = RebalancingSnapshot(
                timestamp=ts,
                positions=updated_positions,
                total_debt=total_debt,
                total_collateral=config.required_collateral,
                weighted_borrow_apy=weighted_borrow_apy,
                cumulative_interest=cumulative_interest,
                cumulative_rebalance_cost=cumulative_rebalance_cost,
                rebalanced=rebalanced,
                rebalance_trigger=trigger,
            )
            snapshots.append(snapshot)

        return snapshots

    def _simulate_benchmark(
        self,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
        markets: List[MarketDebtInfo],
        config: RebalancingConfig,
    ) -> List[RebalancingSnapshot]:
        """Simulate static allocation to lowest-rate market."""
        snapshots = []

        # Find market with lowest initial rate
        best_market = min(markets, key=lambda m: m.borrow_apy)

        # Create single position in best market
        position = DebtPosition(
            market_id=best_market.market_id,
            market_name=best_market.market_name,
            collateral_amount=config.required_collateral,
            borrow_amount=config.total_debt,
            borrow_apy=best_market.borrow_apy,
            health_factor=Decimal("1.5"),  # Simplified
            liquidation_price=Decimal("0.9"),  # Simplified
            allocation_weight=Decimal("1"),
        )

        cumulative_interest = Decimal("0")

        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]

            # Update rate if data available
            current_rate = position.borrow_apy
            if best_market.market_id in market_points:
                current_rate = market_points[best_market.market_id].borrow_apy

            updated_position = DebtPosition(
                market_id=position.market_id,
                market_name=position.market_name,
                collateral_amount=position.collateral_amount,
                borrow_amount=position.borrow_amount,
                borrow_apy=current_rate,
                health_factor=position.health_factor,
                liquidation_price=position.liquidation_price,
                allocation_weight=position.allocation_weight,
            )

            # Calculate interest
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                period_interest = config.total_debt * current_rate * Decimal(str(hours_elapsed / 8760))
                cumulative_interest += period_interest

            snapshot = RebalancingSnapshot(
                timestamp=ts,
                positions=[updated_position],
                total_debt=config.total_debt,
                total_collateral=config.required_collateral,
                weighted_borrow_apy=current_rate,
                cumulative_interest=cumulative_interest,
                cumulative_rebalance_cost=Decimal("0"),
                rebalanced=False,
                rebalance_trigger=None,
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
