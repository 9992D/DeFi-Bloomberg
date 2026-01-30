"""Mean Reversion KPI calculator using Ornstein-Uhlenbeck model."""

from decimal import Decimal
from typing import List

import numpy as np
from scipy import stats
from scipy.optimize import minimize_scalar

from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType

from .base import BaseKPICalculator


class MeanReversionCalculator(BaseKPICalculator):
    """
    Calculate mean-reversion characteristics using Ornstein-Uhlenbeck model.

    The OU process: dX = θ(μ - X)dt + σdW

    Key metric: Half-life = ln(2) / θ
    This tells us how quickly rates revert to their long-term mean.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.MEAN_REVERSION

    @property
    def min_data_points(self) -> int:
        return 20  # Minimum for OU model estimation

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        rate_type: str = "supply",
        **kwargs,
    ) -> KPIResult:
        """
        Calculate mean-reversion half-life using OU model.

        Args:
            market: Market object
            timeseries: Historical data points
            rate_type: Which rate to analyze ("supply" or "borrow")

        Returns:
            KPIResult with half-life in hours
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        try:
            # Extract rates
            field = "supply_apy" if rate_type == "supply" else "borrow_apy"
            rates = self.extract_values(timeseries, field)

            if len(rates) < self.min_data_points:
                return self._error_result(
                    market, ValueError(f"Need {self.min_data_points} points, got {len(rates)}")
                )

            rates_array = np.array(rates)

            # Estimate OU parameters using regression method
            # X(t+1) - X(t) = θ(μ - X(t))Δt + noise
            # Rearranging: X(t+1) = (1 - θΔt)X(t) + θμΔt + noise

            # Assuming hourly data, Δt = 1
            X_t = rates_array[:-1]
            X_t1 = rates_array[1:]

            # OLS regression: X(t+1) = a + b*X(t)
            slope, intercept, r_value, p_value, std_err = stats.linregress(X_t, X_t1)

            # Extract OU parameters
            # b = 1 - θΔt => θ = (1 - b) / Δt
            # a = θμΔt => μ = a / (θΔt) = a / (1 - b)

            dt = 1.0  # 1 hour

            # Check if mean-reverting (0 < slope < 1)
            if slope >= 1 or slope <= 0:
                # Not mean-reverting
                return self._success_result(
                    market=market,
                    value=Decimal("inf"),  # Infinite half-life
                    window_hours=len(timeseries),
                    metadata={
                        "is_mean_reverting": False,
                        "slope": float(slope),
                        "r_squared": float(r_value ** 2),
                        "rate_type": rate_type,
                    },
                )

            theta = (1 - slope) / dt
            mu = intercept / (1 - slope) if abs(1 - slope) > 1e-10 else np.mean(rates_array)

            # Half-life = ln(2) / θ
            half_life = np.log(2) / theta

            # Estimate volatility of residuals
            residuals = X_t1 - (slope * X_t + intercept)
            sigma = np.std(residuals) / np.sqrt(dt)

            return self._success_result(
                market=market,
                value=Decimal(str(half_life)),
                window_hours=len(timeseries),
                metadata={
                    "is_mean_reverting": True,
                    "theta": float(theta),
                    "mu": float(mu),
                    "sigma": float(sigma),
                    "slope": float(slope),
                    "r_squared": float(r_value ** 2),
                    "p_value": float(p_value),
                    "rate_type": rate_type,
                    "current_vs_mean": float(rates_array[-1] - mu),
                },
            )

        except Exception as e:
            return self._error_result(market, e)

    @staticmethod
    def estimate_time_to_mean(
        current_rate: float,
        mu: float,
        theta: float,
        threshold_pct: float = 0.05,
    ) -> float:
        """
        Estimate time to converge within threshold of long-term mean.

        Args:
            current_rate: Current rate value
            mu: Long-term mean
            theta: Mean-reversion speed
            threshold_pct: Threshold as percent of distance

        Returns:
            Time in hours to reach threshold
        """
        if theta <= 0:
            return float("inf")

        distance = abs(current_rate - mu)
        target_distance = distance * threshold_pct

        # X(t) - μ = (X(0) - μ) * e^(-θt)
        # target = distance * e^(-θt)
        # t = -ln(target/distance) / θ

        if target_distance <= 0:
            return 0.0

        return -np.log(threshold_pct) / theta
