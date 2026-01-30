"""Risk-adjusted return KPI calculators (Sharpe, Sortino)."""

from decimal import Decimal
from typing import List

import numpy as np

from src.core.constants import HOURS_PER_YEAR
from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType
from config.settings import get_settings

from .base import BaseKPICalculator


class SharpeCalculator(BaseKPICalculator):
    """
    Calculate Sharpe Ratio for rate returns.

    Sharpe Ratio = (APY - Risk-free Rate) / σ

    Higher Sharpe indicates better risk-adjusted returns.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.SHARPE_RATIO

    @property
    def min_data_points(self) -> int:
        return 20  # Minimum for meaningful ratio calculation

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        risk_free_rate: float = None,
        **kwargs,
    ) -> KPIResult:
        """
        Calculate Sharpe Ratio.

        Args:
            market: Market object
            timeseries: Historical data points
            risk_free_rate: Annual risk-free rate (default from settings)

        Returns:
            KPIResult with Sharpe Ratio
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        if risk_free_rate is None:
            risk_free_rate = get_settings().risk_free_rate

        try:
            # Extract supply APYs
            apys = self.extract_values(timeseries, "supply_apy")

            if len(apys) < 2:
                return self._error_result(market, ValueError("Need at least 2 APY values"))

            apys_array = np.array(apys)

            # Calculate mean APY
            mean_apy = np.mean(apys_array)

            # Calculate standard deviation of APYs
            std_apy = np.std(apys_array, ddof=1)

            if std_apy < 1e-10:
                # No volatility - infinite Sharpe (cap it)
                sharpe = Decimal("10.0") if mean_apy > risk_free_rate else Decimal("0.0")
            else:
                # Sharpe = (return - Rf) / volatility
                excess_return = mean_apy - risk_free_rate
                sharpe = Decimal(str(excess_return / std_apy))

            return self._success_result(
                market=market,
                value=sharpe,
                window_hours=len(timeseries),
                metadata={
                    "mean_apy": float(mean_apy),
                    "std_apy": float(std_apy),
                    "risk_free_rate": float(risk_free_rate),
                    "excess_return": float(mean_apy - risk_free_rate),
                },
            )

        except Exception as e:
            return self._error_result(market, e)


class SortinoCalculator(BaseKPICalculator):
    """
    Calculate Sortino Ratio for rate returns.

    Sortino Ratio = (APY - Risk-free Rate) / σ_downside

    Only considers downside volatility, better for asymmetric returns.
    """

    @property
    def kpi_type(self) -> KPIType:
        return KPIType.SORTINO_RATIO

    @property
    def min_data_points(self) -> int:
        return 20  # Minimum for meaningful ratio calculation

    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        risk_free_rate: float = None,
        mar: float = None,  # Minimum Acceptable Return
        **kwargs,
    ) -> KPIResult:
        """
        Calculate Sortino Ratio.

        Args:
            market: Market object
            timeseries: Historical data points
            risk_free_rate: Annual risk-free rate (default from settings)
            mar: Minimum Acceptable Return (default = risk_free_rate)

        Returns:
            KPIResult with Sortino Ratio
        """
        insufficient = self._check_data_sufficiency(market, timeseries)
        if insufficient:
            return insufficient

        if risk_free_rate is None:
            risk_free_rate = get_settings().risk_free_rate

        if mar is None:
            mar = risk_free_rate

        try:
            # Extract supply APYs
            apys = self.extract_values(timeseries, "supply_apy")

            if len(apys) < 2:
                return self._error_result(market, ValueError("Need at least 2 APY values"))

            apys_array = np.array(apys)

            # Calculate mean APY
            mean_apy = np.mean(apys_array)

            # Calculate downside deviation
            # Only consider returns below MAR
            downside_returns = apys_array[apys_array < mar] - mar

            if len(downside_returns) == 0:
                # No downside - excellent Sortino (cap it)
                sortino = Decimal("10.0") if mean_apy > mar else Decimal("0.0")
                downside_std = 0.0
            else:
                downside_std = np.sqrt(np.mean(downside_returns ** 2))

                if downside_std < 1e-10:
                    sortino = Decimal("10.0") if mean_apy > mar else Decimal("0.0")
                else:
                    excess_return = mean_apy - risk_free_rate
                    sortino = Decimal(str(excess_return / downside_std))

            return self._success_result(
                market=market,
                value=sortino,
                window_hours=len(timeseries),
                metadata={
                    "mean_apy": float(mean_apy),
                    "downside_std": float(downside_std),
                    "risk_free_rate": float(risk_free_rate),
                    "mar": float(mar),
                    "downside_periods": len(downside_returns) if len(downside_returns) > 0 else 0,
                },
            )

        except Exception as e:
            return self._error_result(market, e)
