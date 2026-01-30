"""Base KPI calculator interface."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType, KPIStatus


class BaseKPICalculator(ABC):
    """Abstract base class for KPI calculators."""

    @property
    @abstractmethod
    def kpi_type(self) -> KPIType:
        """Return the type of KPI this calculator produces."""
        pass

    @property
    def min_data_points(self) -> int:
        """Minimum number of data points required for calculation."""
        return 24  # 1 day of hourly data by default

    @abstractmethod
    def calculate(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        **kwargs,
    ) -> KPIResult:
        """
        Calculate the KPI for a market.

        Args:
            market: Market object with current state
            timeseries: Historical timeseries data
            **kwargs: Additional parameters

        Returns:
            KPIResult with calculated value and metadata
        """
        pass

    def _check_data_sufficiency(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
    ) -> Optional[KPIResult]:
        """
        Check if there's sufficient data for calculation.

        Returns KPIResult with INSUFFICIENT_DATA status if not enough data,
        None if data is sufficient.
        """
        if len(timeseries) < self.min_data_points:
            return KPIResult(
                kpi_type=self.kpi_type,
                market_id=market.id,
                value=None,
                status=KPIStatus.INSUFFICIENT_DATA,
                error_message=f"Need {self.min_data_points} data points, got {len(timeseries)}",
            )
        return None

    def _error_result(
        self,
        market: Market,
        error: Exception,
    ) -> KPIResult:
        """Create an error result."""
        return KPIResult(
            kpi_type=self.kpi_type,
            market_id=market.id,
            value=None,
            status=KPIStatus.ERROR,
            error_message=str(error),
        )

    def _success_result(
        self,
        market: Market,
        value: Decimal,
        window_hours: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> KPIResult:
        """Create a success result."""
        return KPIResult(
            kpi_type=self.kpi_type,
            market_id=market.id,
            value=value,
            status=KPIStatus.SUCCESS,
            window_hours=window_hours,
            metadata=metadata or {},
        )

    @staticmethod
    def extract_values(
        timeseries: List[TimeseriesPoint],
        field: str,
    ) -> List[float]:
        """Extract a list of values from timeseries."""
        values = []
        for point in timeseries:
            val = getattr(point, field, None)
            if val is not None:
                values.append(float(val))
        return values
