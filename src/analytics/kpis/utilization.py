"""Utilization-adjusted return KPI calculator."""

from decimal import Decimal
from typing import List

import numpy as np

from src.core.constants import IRM_PARAMS
from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType

from .base import BaseKPICalculator


class UtilAdjustedReturnCalculator(BaseKPICalculator):
    """
    Calculate utilization-adjusted return.

    Penalizes yield when utilization exceeds target (90%),
    as high utilization indicates withdrawal risk.

    Adjusted Return = APY × penalty(utilization)

    Where penalty smoothly decreases as util exceeds target.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.UTIL_ADJUSTED_RETURN

    @property
    def min_data_points(self) -> int:
        return 24  # 1 day of hourly data

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        target_util: float = None,
        penalty_steepness: float = 5.0,
        **kwargs,
    ) -> KPIResult:
        """
        Calculate utilization-adjusted return.

        Args:
            market: Market object
            timeseries: Historical data points
            target_util: Target utilization (default 0.9)
            penalty_steepness: How sharply to penalize above target

        Returns:
            KPIResult with adjusted return
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        if target_util is None:
            target_util = float(IRM_PARAMS["TARGET_UTILIZATION"])

        try:
            # Extract supply APYs and utilizations
            apys = self.extract_values(timeseries, "supply_apy")
            utils = self.extract_values(timeseries, "utilization")

            if len(apys) != len(utils):
                return self._error_result(market, ValueError("Mismatched data lengths"))

            apys_array = np.array(apys)
            utils_array = np.array(utils)

            # Calculate penalty for each point
            # Penalty = 1 / (1 + exp(steepness * (util - target)))
            # At util = target: penalty ≈ 0.5
            # Below target: penalty → 1
            # Above target: penalty → 0
            penalties = self._calculate_penalties(utils_array, target_util, penalty_steepness)

            # Calculate adjusted returns
            adjusted_returns = apys_array * penalties

            # Average adjusted return
            mean_adjusted = np.mean(adjusted_returns)
            mean_raw = np.mean(apys_array)
            mean_penalty = np.mean(penalties)

            # How much yield was "lost" due to high utilization
            yield_haircut = 1 - (mean_adjusted / (mean_raw + 1e-10))

            # Time spent above target
            time_above_target = np.mean(utils_array > target_util)

            # Current adjusted return
            if len(apys) > 0 and len(utils) > 0:
                current_penalty = self._calculate_penalty(utils_array[-1], target_util, penalty_steepness)
                current_adjusted = apys_array[-1] * current_penalty
            else:
                current_adjusted = mean_adjusted
                current_penalty = mean_penalty

            return self._success_result(
                market=market,
                value=Decimal(str(mean_adjusted)),
                window_hours=len(timeseries),
                metadata={
                    "raw_mean_apy": float(mean_raw),
                    "mean_penalty": float(mean_penalty),
                    "yield_haircut": float(yield_haircut),
                    "time_above_target_pct": float(time_above_target),
                    "target_utilization": float(target_util),
                    "current_utilization": float(utils_array[-1]) if len(utils_array) > 0 else None,
                    "current_penalty": float(current_penalty),
                    "current_adjusted_apy": float(current_adjusted),
                },
            )

        except Exception as e:
            return self._error_result(market, e)

    def _calculate_penalty(
        self,
        utilization: float,
        target: float,
        steepness: float,
    ) -> float:
        """Calculate penalty for a single utilization value."""
        # Sigmoid penalty function
        x = steepness * (utilization - target)
        # Avoid overflow
        if x > 100:
            return 0.0
        if x < -100:
            return 1.0
        return 1.0 / (1.0 + np.exp(x))

    def _calculate_penalties(
        self,
        utilizations: np.ndarray,
        target: float,
        steepness: float,
    ) -> np.ndarray:
        """Calculate penalties for array of utilization values."""
        x = steepness * (utilizations - target)
        # Clip to avoid overflow
        x = np.clip(x, -100, 100)
        return 1.0 / (1.0 + np.exp(x))
