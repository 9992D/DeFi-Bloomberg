"""KPI result data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class KPIType(Enum):
    """Types of KPIs calculated for markets."""

    VOLATILITY = "volatility"
    SHARPE_RATIO = "sharpe_ratio"
    SORTINO_RATIO = "sortino_ratio"
    ELASTICITY = "elasticity"
    IRM_EVOLUTION = "irm_evolution"
    MEAN_REVERSION = "mean_reversion"
    UTIL_ADJUSTED_RETURN = "util_adjusted_return"


class KPIStatus(Enum):
    """Status of KPI calculation."""

    SUCCESS = "success"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class KPIResult:
    """Result of a KPI calculation."""

    kpi_type: KPIType
    market_id: str
    value: Optional[Decimal]
    status: KPIStatus
    calculated_at: datetime = field(default_factory=_utcnow)

    # Additional context
    window_hours: Optional[int] = None  # Time window used for calculation
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if KPI was calculated successfully."""
        return self.status == KPIStatus.SUCCESS and self.value is not None

    @property
    def display_value(self) -> str:
        """Format value for display."""
        if not self.is_valid:
            return "N/A"

        if self.kpi_type == KPIType.VOLATILITY:
            return f"{self.value * 100:.2f}%"
        elif self.kpi_type in (KPIType.SHARPE_RATIO, KPIType.SORTINO_RATIO):
            return f"{self.value:.3f}"
        elif self.kpi_type == KPIType.ELASTICITY:
            return f"{self.value:.2f}"
        elif self.kpi_type == KPIType.IRM_EVOLUTION:
            return f"{self.value * 100:.2f}%"
        elif self.kpi_type == KPIType.MEAN_REVERSION:
            return f"{self.value:.1f}h"  # Half-life in hours
        elif self.kpi_type == KPIType.UTIL_ADJUSTED_RETURN:
            return f"{self.value * 100:.2f}%"
        else:
            return f"{self.value:.4f}"

    @property
    def signal(self) -> str:
        """Get signal indicator (positive/negative/neutral)."""
        if not self.is_valid:
            return "neutral"

        if self.kpi_type == KPIType.VOLATILITY:
            # Lower volatility is generally better
            return "positive" if self.value < Decimal("0.5") else "negative"
        elif self.kpi_type in (KPIType.SHARPE_RATIO, KPIType.SORTINO_RATIO):
            if self.value > Decimal("1"):
                return "positive"
            elif self.value < Decimal("0"):
                return "negative"
            return "neutral"
        elif self.kpi_type == KPIType.UTIL_ADJUSTED_RETURN:
            return "positive" if self.value > Decimal("0.05") else "neutral"

        return "neutral"


@dataclass
class MarketKPIs:
    """Collection of KPIs for a single market."""

    market_id: str
    kpis: Dict[KPIType, KPIResult] = field(default_factory=dict)
    calculated_at: datetime = field(default_factory=_utcnow)

    def get(self, kpi_type: KPIType) -> Optional[KPIResult]:
        """Get a specific KPI result."""
        return self.kpis.get(kpi_type)

    def add(self, result: KPIResult) -> None:
        """Add a KPI result."""
        self.kpis[result.kpi_type] = result

    @property
    def all_valid(self) -> bool:
        """Check if all KPIs were calculated successfully."""
        return all(kpi.is_valid for kpi in self.kpis.values())

    @property
    def valid_count(self) -> int:
        """Count of valid KPIs."""
        return sum(1 for kpi in self.kpis.values() if kpi.is_valid)
