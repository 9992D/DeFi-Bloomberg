"""Volatility KPI calculator."""

from decimal import Decimal
from typing import List

import numpy as np

from src.core.constants import HOURS_PER_YEAR
from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType


from .base import BaseKPICalculator


class VolatilityCalculator(BaseKPICalculator):
    """
    Calculate annualized volatility of rates.

    Volatility = Rolling Std Dev × √(hours per year)

    Higher volatility indicates more rate instability.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.VOLATILITY

    @property
    def min_data_points(self) -> int:
        return 24  # 1 day of hourly data

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        window_hours: int = 168,  # 7 days
        rate_type: str = "supply",  # "supply" or "borrow"
        **kwargs,
    ) -> KPIResult:
        """
        Calculate annualized rate volatility.

        Args:
            market: Market object
            timeseries: Historical data points
            window_hours: Rolling window size in hours
            rate_type: Which rate to calculate volatility for

        Returns:
            KPIResult with annualized volatility
        """
        # Check data sufficiency
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        try:
            # Extract rates
            field = "supply_apy" if rate_type == "supply" else "borrow_apy"
            rates = self.extract_values(timeseries, field)

            if len(rates) < 2:
                return self._error_result(market, ValueError("Need at least 2 rate values"))

            # Filter out zero/near-zero rates (inactive periods)
            min_rate = 1e-6
            filtered_rates = [r for r in rates if r > min_rate]

            if len(filtered_rates) < 2:
                return self._error_result(
                    market, ValueError("Not enough non-zero rate values")
                )

            rates_array = np.array(filtered_rates)

            # Since APY is already an annual rate, std(APY) is the volatility
            # No annualization needed - APY values are already annualized
            volatility = np.std(rates_array, ddof=1)

            return self._success_result(
                market=market,
                value=Decimal(str(volatility)),
                window_hours=len(timeseries),
                metadata={
                    "rate_type": rate_type,
                    "data_points": len(filtered_rates),
                    "filtered_out": len(rates) - len(filtered_rates),
                    "mean_rate": float(np.mean(rates_array)),
                    "min_rate": float(np.min(rates_array)),
                    "max_rate": float(np.max(rates_array)),
                },
            )

        except Exception as e:
            return self._error_result(market, e)
