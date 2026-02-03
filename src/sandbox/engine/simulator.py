"""Strategy simulation engine."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from src.sandbox.models import (
    SimulatedPosition,
    StrategyConfig,
    SimulationResult,
    SimulationPoint,
)
from src.sandbox.data import DataAggregator, MarketSnapshot
from src.sandbox.strategies.base import BaseStrategy
from src.sandbox.strategies.leverage_loop import LeverageLoopStrategy

logger = logging.getLogger(__name__)


class StrategySimulator:
    """
    Engine for running strategy simulations over historical data.

    Takes a strategy and market data, then simulates the strategy
    performance over time, tracking P&L, health factor, and events.
    """

    def __init__(self, data: DataAggregator):
        """
        Initialize simulator.

        Args:
            data: Data aggregator for market access
        """
        self.data = data

    def _create_strategy(self, config: StrategyConfig) -> BaseStrategy:
        """Create strategy instance from config."""
        from src.sandbox.models import StrategyType

        if config.strategy_type == StrategyType.LEVERAGE_LOOP:
            return LeverageLoopStrategy(config, self.data)
        else:
            raise ValueError(f"Unknown strategy type: {config.strategy_type}")

    async def run_simulation(
        self,
        config: StrategyConfig,
        days: Optional[int] = None,
        interval: str = "HOUR",
    ) -> SimulationResult:
        """
        Run a strategy simulation over historical data.

        Args:
            config: Strategy configuration
            days: Number of days to simulate (default from config)
            interval: Data interval (HOUR, DAY)

        Returns:
            SimulationResult with full time series and metrics
        """
        days = days or config.simulation_days
        interval = interval or config.simulation_interval

        logger.info(f"Starting simulation: {config.name}, {days} days, {interval} interval")

        # Get market info for loan asset (needed for risk-free rate)
        market = await self.data.get_market(config.protocol, config.market_id)
        loan_asset_address = market.loan_asset if market else ""
        loan_asset_symbol = market.loan_asset_symbol if market else ""

        # Get market snapshots
        snapshots = await self.data.get_market_snapshots(
            protocol=config.protocol,
            market_id=config.market_id,
            interval=interval,
            days=days,
        )

        if not snapshots:
            return SimulationResult(
                strategy_name=config.name,
                strategy_type=config.strategy_type.value,
                market_id=config.market_id,
                initial_capital=config.initial_capital,
                loan_asset_address=loan_asset_address,
                loan_asset_symbol=loan_asset_symbol,
                start_time=datetime.now(tz=timezone.utc),
                end_time=datetime.now(tz=timezone.utc),
                success=False,
                error_message="No market data available",
            )

        # Create strategy
        strategy = self._create_strategy(config)

        # Build initial position at first snapshot
        first_snapshot = snapshots[0]
        try:
            position = await strategy.build_position(
                capital=config.initial_capital,
                entry_price=first_snapshot.collateral_price,
                supply_apy=first_snapshot.supply_apy,
                borrow_apy=first_snapshot.borrow_apy,
                lltv=first_snapshot.lltv,
            )
        except Exception as e:
            logger.error(f"Failed to build position: {e}")
            return SimulationResult(
                strategy_name=config.name,
                strategy_type=config.strategy_type.value,
                market_id=config.market_id,
                initial_capital=config.initial_capital,
                loan_asset_address=loan_asset_address,
                loan_asset_symbol=loan_asset_symbol,
                start_time=first_snapshot.timestamp,
                end_time=snapshots[-1].timestamp,
                success=False,
                error_message=f"Failed to build position: {e}",
            )

        # Run simulation
        points: List[SimulationPoint] = []
        start_time = first_snapshot.timestamp
        liquidated = False

        for snapshot in snapshots:
            if liquidated:
                # Position was liquidated, stop simulation
                break

            # Create simulation point
            point = strategy.simulate_point(
                position=position,
                timestamp=snapshot.timestamp,
                current_price=snapshot.collateral_price,
                supply_apy=snapshot.supply_apy,
                borrow_apy=snapshot.borrow_apy,
                start_time=start_time,
            )

            points.append(point)

            if point.liquidated:
                liquidated = True
                logger.warning(f"Position liquidated at {snapshot.timestamp}")

            # Update position reference (may have been modified by strategy)
            position = strategy.position

        # Build result
        result = SimulationResult(
            strategy_name=config.name,
            strategy_type=config.strategy_type.value,
            market_id=config.market_id,
            initial_capital=config.initial_capital,
            loan_asset_address=loan_asset_address,
            loan_asset_symbol=loan_asset_symbol,
            start_time=start_time,
            end_time=points[-1].timestamp if points else start_time,
            final_position=position,
            points=points,
            success=True,
            parameters=config.parameters,
        )

        # Calculate metrics
        result.calculate_metrics()

        logger.info(
            f"Simulation complete: {len(points)} points, "
            f"return={float(result.metrics.total_return_percent):.2f}%"
        )

        return result

    async def run_parameter_sweep(
        self,
        base_config: StrategyConfig,
        param_name: str,
        param_values: List[Decimal],
        days: Optional[int] = None,
        interval: str = "HOUR",
    ) -> List[SimulationResult]:
        """
        Run simulations across different parameter values.

        Useful for finding optimal parameters.

        Args:
            base_config: Base strategy configuration
            param_name: Parameter to sweep (e.g., "target_leverage")
            param_values: Values to test
            days: Simulation days
            interval: Data interval

        Returns:
            List of SimulationResult for each parameter value
        """
        results = []

        for value in param_values:
            # Create config with modified parameter
            config = StrategyConfig.from_dict(base_config.to_dict())
            config.parameters[param_name] = str(value)
            config.name = f"{base_config.name} ({param_name}={value})"

            result = await self.run_simulation(config, days, interval)
            results.append(result)

        return results

    async def compare_strategies(
        self,
        configs: List[StrategyConfig],
        days: Optional[int] = None,
        interval: str = "HOUR",
    ) -> List[SimulationResult]:
        """
        Run and compare multiple strategies.

        Args:
            configs: List of strategy configurations
            days: Simulation days (applied to all)
            interval: Data interval

        Returns:
            List of SimulationResult for comparison
        """
        results = []

        for config in configs:
            result = await self.run_simulation(config, days, interval)
            results.append(result)

        return results

    def format_comparison(self, results: List[SimulationResult]) -> str:
        """
        Format comparison of simulation results.

        Args:
            results: List of simulation results

        Returns:
            Formatted comparison string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("STRATEGY COMPARISON")
        lines.append("=" * 80)
        lines.append("")

        # Header
        header = f"{'Strategy':<30} {'Return':>10} {'APY':>10} {'Sharpe':>8} {'MaxDD':>8} {'MinHF':>8}"
        lines.append(header)
        lines.append("-" * 80)

        for r in results:
            if not r.success or not r.metrics:
                lines.append(f"{r.strategy_name:<30} {'FAILED':>10}")
                continue

            m = r.metrics
            line = (
                f"{r.strategy_name:<30} "
                f"{float(m.total_return_percent):>9.2f}% "
                f"{float(m.annualized_return):>9.2f}% "
                f"{float(m.sharpe_ratio):>8.2f} "
                f"{float(m.max_drawdown):>7.2f}% "
                f"{float(m.min_health_factor):>8.2f}"
            )
            lines.append(line)

        lines.append("=" * 80)
        return "\n".join(lines)
