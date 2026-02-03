"""Timeseries data models for historical market data."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class TimeseriesPoint:
    """A single point in market timeseries data."""

    timestamp: datetime

    # Rates (APY)
    supply_apy: Decimal
    borrow_apy: Decimal

    # Utilization
    utilization: Decimal

    # IRM state
    rate_at_target: Optional[Decimal] = None

    # Volumes (optional)
    total_supply_assets: Optional[Decimal] = None
    total_borrow_assets: Optional[Decimal] = None

    # Price data (optional)
    collateral_price_usd: Optional[Decimal] = None
    loan_price_usd: Optional[Decimal] = None

    def __lt__(self, other):
        """Enable sorting by timestamp."""
        if isinstance(other, TimeseriesPoint):
            return self.timestamp < other.timestamp
        return NotImplemented

    def __hash__(self):
        return hash(self.timestamp)

    def __eq__(self, other):
        if isinstance(other, TimeseriesPoint):
            return self.timestamp == other.timestamp
        return False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "supply_apy": str(self.supply_apy),
            "borrow_apy": str(self.borrow_apy),
            "utilization": str(self.utilization),
            "rate_at_target": str(self.rate_at_target) if self.rate_at_target else None,
            "total_supply_assets": str(self.total_supply_assets) if self.total_supply_assets else None,
            "total_borrow_assets": str(self.total_borrow_assets) if self.total_borrow_assets else None,
            "collateral_price_usd": str(self.collateral_price_usd) if self.collateral_price_usd else None,
            "loan_price_usd": str(self.loan_price_usd) if self.loan_price_usd else None,
        }


@dataclass
class AggregatedTimeseries:
    """Aggregated timeseries data for a market."""

    market_id: str
    points: list[TimeseriesPoint]
    start_time: datetime
    end_time: datetime
    interval_hours: int  # Granularity of data

    @property
    def supply_apys(self) -> list[Decimal]:
        """Extract supply APYs from points."""
        return [p.supply_apy for p in self.points]

    @property
    def borrow_apys(self) -> list[Decimal]:
        """Extract borrow APYs from points."""
        return [p.borrow_apy for p in self.points]

    @property
    def utilizations(self) -> list[Decimal]:
        """Extract utilization rates from points."""
        return [p.utilization for p in self.points]

    @property
    def timestamps(self) -> list[datetime]:
        """Extract timestamps from points."""
        return [p.timestamp for p in self.points]

    def filter_by_time_range(
        self, start: datetime, end: datetime
    ) -> "AggregatedTimeseries":
        """Filter points to a specific time range."""
        filtered = [p for p in self.points if start <= p.timestamp <= end]
        return AggregatedTimeseries(
            market_id=self.market_id,
            points=filtered,
            start_time=start,
            end_time=end,
            interval_hours=self.interval_hours,
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "market_id": self.market_id,
            "points": [p.to_dict() for p in self.points],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "interval_hours": self.interval_hours,
        }
