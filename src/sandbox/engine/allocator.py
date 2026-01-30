"""Vault allocation simulator with rebalancing strategies."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import statistics

from src.sandbox.models.allocation import (
    AllocationConfig,
    AllocationStrategy,
    AllocationResult,
    AllocationSnapshot,
    AllocationMetrics,
    MarketAllocation,
)
from src.sandbox.data import DataAggregator
from src.core.models import Market, TimeseriesPoint

logger = logging.getLogger(__name__)


class AllocationSimulator:
    """
    Simulates vault allocation strategies across Morpho markets.
    
    Strategies:
    - EQUAL: 1/N allocation to each market
    - YIELD_WEIGHTED: Proportional to current APY
    - WATERFILL: Optimize to equalize marginal yields (like water filling containers)
    """
    
    def __init__(self, data: DataAggregator):
        self.data = data
        self._market_cache: Dict[str, Market] = {}
    
    async def run_simulation(
        self,
        config: AllocationConfig,
    ) -> AllocationResult:
        """
        Run allocation simulation over historical data.
        
        Args:
            config: Allocation configuration
            
        Returns:
            AllocationResult with time series and metrics
        """
        logger.info(f"Starting allocation simulation: {config.name}")
        
        # Fetch market data and timeseries for all markets
        markets_data = await self._fetch_markets_data(
            config.market_ids,
            config.simulation_days,
            config.simulation_interval,
        )
        
        if not markets_data:
            return AllocationResult(
                config=config,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                success=False,
                error_message="No market data available",
            )
        
        # Align timeseries across markets
        aligned_data = self._align_timeseries(markets_data)
        
        if not aligned_data:
            return AllocationResult(
                config=config,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow(),
                success=False,
                error_message="Could not align market timeseries",
            )
        
        timestamps = sorted(aligned_data.keys())
        start_time = timestamps[0]
        end_time = timestamps[-1]
        
        # Run strategy simulation
        snapshots = self._simulate_strategy(
            config=config,
            aligned_data=aligned_data,
            timestamps=timestamps,
        )
        
        # Run benchmark (equal weight, no rebalancing after initial)
        benchmark_snapshots = self._simulate_benchmark(
            config=config,
            aligned_data=aligned_data,
            timestamps=timestamps,
        )
        
        # Calculate metrics
        metrics = self._calculate_metrics(
            snapshots=snapshots,
            benchmark_snapshots=benchmark_snapshots,
            config=config,
        )
        
        result = AllocationResult(
            config=config,
            start_time=start_time,
            end_time=end_time,
            snapshots=snapshots,
            benchmark_snapshots=benchmark_snapshots,
            metrics=metrics,
            success=True,
        )
        
        logger.info(
            f"Simulation complete: {len(snapshots)} points, "
            f"return={float(metrics.total_return_pct):.2f}%"
        )
        
        return result
    
    async def _fetch_markets_data(
        self,
        market_ids: List[str],
        days: int,
        interval: str,
    ) -> Dict[str, Tuple[Market, List[TimeseriesPoint]]]:
        """Fetch market info and timeseries for all markets."""
        result = {}

        for market_id in market_ids:
            try:
                logger.info(f"Fetching market {market_id[:16]}...")
                market = await self.data.get_market("morpho", market_id)
                if not market:
                    logger.warning(f"Market not found: {market_id}")
                    continue

                logger.info(f"Fetching timeseries for {market.name}...")
                timeseries = await self.data.get_market_timeseries(
                    protocol="morpho",
                    market_id=market_id,
                    interval=interval,
                    days=days,
                )
                
                if timeseries:
                    result[market_id] = (market, timeseries)
                    self._market_cache[market_id] = market
                    logger.debug(f"Loaded {len(timeseries)} points for {market.name}")
                    
            except Exception as e:
                logger.error(f"Error fetching market {market_id}: {e}")
        
        return result
    
    def _align_timeseries(
        self,
        markets_data: Dict[str, Tuple[Market, List[TimeseriesPoint]]],
    ) -> Dict[datetime, Dict[str, TimeseriesPoint]]:
        """
        Align timeseries across markets by timestamp.
        
        Returns dict: timestamp -> {market_id -> TimeseriesPoint}
        """
        # Collect all timestamps
        all_timestamps = set()
        for market_id, (market, timeseries) in markets_data.items():
            for point in timeseries:
                all_timestamps.add(point.timestamp)
        
        # Build aligned data
        aligned = {}
        for ts in sorted(all_timestamps):
            points_at_ts = {}
            for market_id, (market, timeseries) in markets_data.items():
                # Find point at this timestamp
                for point in timeseries:
                    if point.timestamp == ts:
                        points_at_ts[market_id] = point
                        break
            
            # Only include timestamps where all markets have data
            if len(points_at_ts) == len(markets_data):
                aligned[ts] = points_at_ts
        
        return aligned
    
    def _simulate_strategy(
        self,
        config: AllocationConfig,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
    ) -> List[AllocationSnapshot]:
        """Run the allocation strategy simulation."""
        snapshots = []
        
        # Initial allocation
        current_weights = self._calculate_weights(
            config=config,
            market_points={mid: aligned_data[timestamps[0]][mid] for mid in config.market_ids},
        )
        
        total_value = config.initial_capital
        cumulative_yield = Decimal("0")
        last_rebalance = timestamps[0]
        
        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]
            
            # Check if rebalance needed
            should_rebalance = False
            if i > 0:
                hours_since_rebalance = (ts - last_rebalance).total_seconds() / 3600
                if hours_since_rebalance >= config.rebalance_frequency_hours:
                    should_rebalance = True
                    
                # Also check drift threshold
                current_apys = {mid: market_points[mid].supply_apy for mid in config.market_ids}
                if self._check_drift(current_weights, current_apys, config.rebalance_threshold):
                    should_rebalance = True
            
            # Rebalance if needed
            rebalance_cost = Decimal("0")
            if should_rebalance:
                new_weights = self._calculate_weights(
                    config=config,
                    market_points=market_points,
                )
                current_weights = new_weights
                last_rebalance = ts
                # Simplified: no gas cost for now
            
            # Calculate weighted APY
            weighted_apy = sum(
                current_weights.get(mid, Decimal("0")) * market_points[mid].supply_apy
                for mid in config.market_ids
            )
            
            # Calculate yield for this period (if not first point)
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                period_yield = total_value * weighted_apy * Decimal(str(hours_elapsed / 8760))
                cumulative_yield += period_yield
                total_value += period_yield
            
            # Build allocations
            allocations = []
            for mid in config.market_ids:
                weight = current_weights.get(mid, Decimal("0"))
                market = self._market_cache.get(mid)
                allocations.append(MarketAllocation(
                    market_id=mid,
                    market_name=market.name if market else mid[:16],
                    weight=weight,
                    amount=total_value * weight,
                    supply_apy=market_points[mid].supply_apy,
                    utilization=market_points[mid].utilization,
                ))
            
            # Calculate return
            return_pct = (total_value - config.initial_capital) / config.initial_capital * 100
            
            snapshot = AllocationSnapshot(
                timestamp=ts,
                total_value=total_value,
                allocations=allocations,
                weighted_apy=weighted_apy,
                cumulative_yield=cumulative_yield,
                cumulative_return_pct=return_pct,
                rebalanced=should_rebalance,
                rebalance_cost=rebalance_cost,
            )
            snapshots.append(snapshot)
        
        return snapshots
    
    def _simulate_benchmark(
        self,
        config: AllocationConfig,
        aligned_data: Dict[datetime, Dict[str, TimeseriesPoint]],
        timestamps: List[datetime],
    ) -> List[AllocationSnapshot]:
        """Simulate equal-weight benchmark without rebalancing."""
        snapshots = []
        
        # Fixed equal weights
        n_markets = len(config.market_ids)
        equal_weight = Decimal("1") / Decimal(str(n_markets))
        weights = {mid: equal_weight for mid in config.market_ids}
        
        # Track individual market values (they grow at different rates)
        market_values = {mid: config.initial_capital * equal_weight for mid in config.market_ids}
        cumulative_yield = Decimal("0")
        
        for i, ts in enumerate(timestamps):
            market_points = aligned_data[ts]
            
            # Calculate yield for each market (if not first point)
            if i > 0:
                hours_elapsed = (ts - timestamps[i-1]).total_seconds() / 3600
                for mid in config.market_ids:
                    market_yield = market_values[mid] * market_points[mid].supply_apy * Decimal(str(hours_elapsed / 8760))
                    market_values[mid] += market_yield
                    cumulative_yield += market_yield
            
            total_value = sum(market_values.values())
            
            # Current weights (will drift from equal due to different yields)
            current_weights = {mid: market_values[mid] / total_value for mid in config.market_ids}
            
            # Weighted APY based on current (drifted) weights
            weighted_apy = sum(
                current_weights[mid] * market_points[mid].supply_apy
                for mid in config.market_ids
            )
            
            # Build allocations
            allocations = []
            for mid in config.market_ids:
                market = self._market_cache.get(mid)
                allocations.append(MarketAllocation(
                    market_id=mid,
                    market_name=market.name if market else mid[:16],
                    weight=current_weights[mid],
                    amount=market_values[mid],
                    supply_apy=market_points[mid].supply_apy,
                    utilization=market_points[mid].utilization,
                ))
            
            return_pct = (total_value - config.initial_capital) / config.initial_capital * 100
            
            snapshot = AllocationSnapshot(
                timestamp=ts,
                total_value=total_value,
                allocations=allocations,
                weighted_apy=weighted_apy,
                cumulative_yield=cumulative_yield,
                cumulative_return_pct=return_pct,
                rebalanced=False,
            )
            snapshots.append(snapshot)
        
        return snapshots
    
    def _calculate_weights(
        self,
        config: AllocationConfig,
        market_points: Dict[str, TimeseriesPoint],
    ) -> Dict[str, Decimal]:
        """Calculate allocation weights based on strategy."""
        
        if config.strategy == AllocationStrategy.EQUAL:
            return self._equal_weights(config.market_ids)
        
        elif config.strategy == AllocationStrategy.YIELD_WEIGHTED:
            return self._yield_weighted(config, market_points)
        
        elif config.strategy == AllocationStrategy.WATERFILL:
            return self._waterfill_weights(config, market_points)
        
        elif config.strategy == AllocationStrategy.CUSTOM:
            return config.custom_weights
        
        else:
            return self._equal_weights(config.market_ids)
    
    def _equal_weights(self, market_ids: List[str]) -> Dict[str, Decimal]:
        """Equal 1/N weights."""
        n = len(market_ids)
        weight = Decimal("1") / Decimal(str(n))
        return {mid: weight for mid in market_ids}
    
    def _yield_weighted(
        self,
        config: AllocationConfig,
        market_points: Dict[str, TimeseriesPoint],
    ) -> Dict[str, Decimal]:
        """Weights proportional to APY."""
        apys = {mid: market_points[mid].supply_apy for mid in config.market_ids}
        total_apy = sum(apys.values())
        
        if total_apy == 0:
            return self._equal_weights(config.market_ids)
        
        weights = {}
        for mid in config.market_ids:
            raw_weight = apys[mid] / total_apy
            # Apply constraints
            weight = max(config.min_allocation, min(config.max_allocation, raw_weight))
            weights[mid] = weight
        
        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {mid: w / total for mid, w in weights.items()}
        
        return weights
    
    def _waterfill_weights(
        self,
        config: AllocationConfig,
        market_points: Dict[str, TimeseriesPoint],
    ) -> Dict[str, Decimal]:
        """
        Waterfilling allocation to equalize marginal yields.
        
        The idea: allocate more to higher-yielding markets until their
        marginal yield equals lower-yielding ones (like water filling containers).
        
        For supply markets without utilization-based rate curves,
        this simplifies to yield-weighted allocation.
        
        For markets with rate curves, more capital -> higher utilization -> 
        potentially different rates. We approximate by weighting more heavily
        to higher APY markets but with diminishing returns.
        """
        apys = {mid: market_points[mid].supply_apy for mid in config.market_ids}
        utils = {mid: market_points[mid].utilization for mid in config.market_ids}
        
        # Score = APY * (1 - utilization/2) to favor less utilized markets
        # This is a simplified waterfill heuristic
        scores = {}
        for mid in config.market_ids:
            apy = apys[mid]
            util = utils[mid]
            # Higher APY is good, lower utilization is good (room to grow)
            score = apy * (Decimal("1") + (Decimal("1") - util) * Decimal("0.5"))
            scores[mid] = max(score, Decimal("0.001"))  # Avoid zero
        
        total_score = sum(scores.values())
        
        weights = {}
        for mid in config.market_ids:
            raw_weight = scores[mid] / total_score
            # Apply constraints
            weight = max(config.min_allocation, min(config.max_allocation, raw_weight))
            weights[mid] = weight
        
        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {mid: w / total for mid, w in weights.items()}
        
        return weights
    
    def _check_drift(
        self,
        current_weights: Dict[str, Decimal],
        current_apys: Dict[str, Decimal],
        threshold: Decimal,
    ) -> bool:
        """Check if allocation has drifted enough to warrant rebalancing."""
        # Simple check: if any weight is far from optimal yield-weighted
        total_apy = sum(current_apys.values())
        if total_apy == 0:
            return False
        
        for mid, weight in current_weights.items():
            optimal = current_apys[mid] / total_apy
            if abs(weight - optimal) > threshold:
                return True
        
        return False
    
    def _calculate_metrics(
        self,
        snapshots: List[AllocationSnapshot],
        benchmark_snapshots: List[AllocationSnapshot],
        config: AllocationConfig,
    ) -> AllocationMetrics:
        """Calculate aggregated metrics."""
        if not snapshots:
            return AllocationMetrics(
                total_return=Decimal("0"),
                total_return_pct=Decimal("0"),
                annualized_return=Decimal("0"),
                volatility=Decimal("0"),
                sharpe_ratio=Decimal("0"),
                max_drawdown=Decimal("0"),
                avg_weighted_apy=Decimal("0"),
                min_weighted_apy=Decimal("0"),
                max_weighted_apy=Decimal("0"),
                rebalance_count=0,
                total_rebalance_cost=Decimal("0"),
                benchmark_return_pct=Decimal("0"),
                excess_return_pct=Decimal("0"),
                simulation_days=0,
                data_points=0,
            )
        
        # Returns
        total_return = snapshots[-1].cumulative_yield
        total_return_pct = snapshots[-1].cumulative_return_pct
        days = max(1, (snapshots[-1].timestamp - snapshots[0].timestamp).days)
        annualized = ((1 + float(total_return_pct) / 100) ** (365 / days) - 1) * 100
        
        # Volatility
        returns = [float(s.cumulative_return_pct) for s in snapshots]
        period_returns = [returns[i] - returns[i-1] for i in range(1, len(returns))]
        vol = Decimal(str(statistics.stdev(period_returns))) if len(period_returns) > 1 else Decimal("0")
        ann_vol = vol * Decimal(str((365 * 24) ** 0.5))  # Assuming hourly data
        
        # Sharpe
        sharpe = Decimal(str(annualized)) / ann_vol if ann_vol > 0 else Decimal("0")
        
        # Max drawdown
        peak = returns[0]
        max_dd = 0.0
        for r in returns:
            if r > peak:
                peak = r
            dd = peak - r
            if dd > max_dd:
                max_dd = dd
        
        # APY stats
        apys = [float(s.weighted_apy) for s in snapshots]
        avg_apy = Decimal(str(statistics.mean(apys)))
        min_apy = Decimal(str(min(apys)))
        max_apy = Decimal(str(max(apys)))
        
        # Rebalancing
        rebalance_count = sum(1 for s in snapshots if s.rebalanced)
        total_cost = sum(s.rebalance_cost for s in snapshots)
        
        # Benchmark comparison
        benchmark_return = benchmark_snapshots[-1].cumulative_return_pct if benchmark_snapshots else Decimal("0")
        excess = total_return_pct - benchmark_return
        
        return AllocationMetrics(
            total_return=total_return,
            total_return_pct=total_return_pct,
            annualized_return=Decimal(str(annualized)),
            volatility=vol,
            sharpe_ratio=sharpe,
            max_drawdown=Decimal(str(max_dd)),
            avg_weighted_apy=avg_apy,
            min_weighted_apy=min_apy,
            max_weighted_apy=max_apy,
            rebalance_count=rebalance_count,
            total_rebalance_cost=total_cost,
            benchmark_return_pct=benchmark_return,
            excess_return_pct=excess,
            simulation_days=days,
            data_points=len(snapshots),
        )
