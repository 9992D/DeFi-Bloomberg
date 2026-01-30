"""IRM Evolution KPI calculator."""

from decimal import Decimal
from typing import List

import numpy as np
from scipy import stats

from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType

from .base import BaseKPICalculator


class IRMEvolutionCalculator(BaseKPICalculator):
    """
    Track the evolution of rateAtTarget over time.

    The AdaptiveCurveIRM adjusts rateAtTarget based on whether
    utilization is above or below the 90% target. This KPI tracks:
    - Current rateAtTarget
    - Trend direction and magnitude
    - Rate of change
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.IRM_EVOLUTION

    @property
    def min_data_points(self) -> int:
        return 24  # 1 day of hourly data

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        **kwargs,
    ) -> KPIResult:
        """
        Calculate IRM rateAtTarget evolution metrics.

        Args:
            market: Market object
            timeseries: Historical data points

        Returns:
            KPIResult with current rateAtTarget and trend info
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        try:
            # Extract rateAtTarget values
            rates_at_target = []
            timestamps = []

            for point in timeseries:
                if point.rate_at_target is not None:
                    rates_at_target.append(float(point.rate_at_target))
                    timestamps.append(point.timestamp.timestamp())

            if len(rates_at_target) < 2:
                # Use market's current rateAtTarget if available
                if market.rate_at_target and market.rate_at_target > 0:
                    return self._success_result(
                        market=market,
                        value=market.rate_at_target,
                        window_hours=len(timeseries),
                        metadata={
                            "trend": "unknown",
                            "source": "current_state",
                        },
                    )
                return self._error_result(
                    market, ValueError("No rateAtTarget data available")
                )

            rates_array = np.array(rates_at_target)
            times_array = np.array(timestamps)

            # Normalize time to hours from start
            times_normalized = (times_array - times_array[0]) / 3600

            # Linear regression to detect trend
            slope, intercept, r_value, p_value, std_err = stats.linregress(
                times_normalized, rates_array
            )

            # Current value (most recent)
            current_rate = rates_array[-1]
            initial_rate = rates_array[0]

            # Percent change
            pct_change = (current_rate - initial_rate) / (initial_rate + 1e-10)

            # Determine trend
            if abs(slope) < 1e-8:
                trend = "stable"
            elif slope > 0:
                trend = "increasing"
            else:
                trend = "decreasing"

            # Hours until significant change (1% change at current rate)
            if abs(slope) > 1e-10:
                hours_to_1pct = abs(0.01 * current_rate / slope)
            else:
                hours_to_1pct = float("inf")

            return self._success_result(
                market=market,
                value=Decimal(str(current_rate)),
                window_hours=len(timeseries),
                metadata={
                    "trend": trend,
                    "slope_per_hour": float(slope),
                    "initial_rate": float(initial_rate),
                    "pct_change": float(pct_change),
                    "r_squared": float(r_value ** 2),
                    "p_value": float(p_value),
                    "hours_to_1pct_change": float(hours_to_1pct) if hours_to_1pct != float("inf") else None,
                    "data_points": len(rates_array),
                },
            )

        except Exception as e:
            return self._error_result(market, e)
