"""Elasticity KPI calculator."""

from decimal import Decimal
from typing import List, Tuple

import numpy as np
from scipy import stats

from src.core.constants import DEFAULT_ELASTICITY_RANGE
from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType

from .base import BaseKPICalculator


class ElasticityCalculator(BaseKPICalculator):
    """
    Calculate rate elasticity around 90% utilization target.

    Elasticity measures how sensitive rates are to utilization changes
    near the target utilization (90%).

    Calculated via log-log regression: ln(rate) = α + β * ln(utilization)
    where β is the elasticity coefficient.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.ELASTICITY

    @property
    def min_data_points(self) -> int:
        return 15  # Minimum for regression

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        util_range: Tuple[float, float] = DEFAULT_ELASTICITY_RANGE,
        rate_type: str = "borrow",
        **kwargs,
    ) -> KPIResult:
        """
        Calculate rate elasticity near target utilization.

        Args:
            market: Market object
            timeseries: Historical data points
            util_range: Utilization range to consider (default 85%-95%)
            rate_type: Which rate to analyze ("borrow" or "supply")

        Returns:
            KPIResult with elasticity coefficient
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        try:
            # Extract utilization and rates
            utils = self.extract_values(timeseries, "utilization")
            field = "borrow_apy" if rate_type == "borrow" else "supply_apy"
            rates = self.extract_values(timeseries, field)

            if len(utils) != len(rates):
                return self._error_result(market, ValueError("Mismatched data lengths"))

            # Filter to utilization range
            utils_array = np.array(utils)
            rates_array = np.array(rates)

            mask = (utils_array >= util_range[0]) & (utils_array <= util_range[1])
            filtered_utils = utils_array[mask]
            filtered_rates = rates_array[mask]

            if len(filtered_utils) < 10:
                return KPIResult(
                    kpi_type=self.kpi_type,
                    market_id=market.id,
                    value=None,
                    status=KPIResult.KPIStatus.INSUFFICIENT_DATA if hasattr(KPIResult, 'KPIStatus') else 1,
                    error_message=f"Only {len(filtered_utils)} points in util range {util_range}",
                )

            # Filter out zero/negative values for log transformation
            valid_mask = (filtered_utils > 0) & (filtered_rates > 0)
            filtered_utils = filtered_utils[valid_mask]
            filtered_rates = filtered_rates[valid_mask]

            if len(filtered_utils) < 10:
                return self._error_result(
                    market,
                    ValueError("Insufficient valid data points for log transformation"),
                )

            # Log-log regression
            log_utils = np.log(filtered_utils)
            log_rates = np.log(filtered_rates)

            slope, intercept, r_value, p_value, std_err = stats.linregress(
                log_utils, log_rates
            )

            # The slope is the elasticity coefficient
            elasticity = Decimal(str(slope))

            return self._success_result(
                market=market,
                value=elasticity,
                window_hours=len(timeseries),
                metadata={
                    "util_range": list(util_range),
                    "rate_type": rate_type,
                    "data_points_in_range": len(filtered_utils),
                    "r_squared": float(r_value ** 2),
                    "p_value": float(p_value),
                    "std_error": float(std_err),
                    "intercept": float(intercept),
                },
            )

        except Exception as e:
            return self._error_result(market, e)
