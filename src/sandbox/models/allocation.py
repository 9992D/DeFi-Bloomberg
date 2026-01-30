"""Vault allocation simulation models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional, Any


class AllocationStrategy(Enum):
    """Allocation strategy types."""
    EQUAL = "equal"                    # 1/N to each market
    YIELD_WEIGHTED = "yield_weighted"  # Proportional to APY
    WATERFILL = "waterfill"            # Optimize to equalize marginal yields
    CUSTOM = "custom"                  # User-defined weights


@dataclass
class MarketAllocation:
    """Allocation to a single market at a point in time."""
    market_id: str
    market_name: str
    weight: Decimal           # 0-1, sum of all weights = 1
    amount: Decimal           # Actual amount allocated
    supply_apy: Decimal       # Current supply APY
    utilization: Decimal      # Current utilization


@dataclass
class AllocationSnapshot:
    """Complete allocation state at a point in time."""
    timestamp: datetime
    total_value: Decimal
    allocations: List[MarketAllocation]
    weighted_apy: Decimal     # Portfolio weighted APY
    
    # Performance since start
    cumulative_yield: Decimal
    cumulative_return_pct: Decimal
    
    # Events
    rebalanced: bool = False
    rebalance_cost: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_value": str(self.total_value),
            "allocations": [
                {
                    "market_id": a.market_id,
                    "market_name": a.market_name,
                    "weight": str(a.weight),
                    "amount": str(a.amount),
                    "supply_apy": str(a.supply_apy),
                    "utilization": str(a.utilization),
                }
                for a in self.allocations
            ],
            "weighted_apy": str(self.weighted_apy),
            "cumulative_yield": str(self.cumulative_yield),
            "cumulative_return_pct": str(self.cumulative_return_pct),
            "rebalanced": self.rebalanced,
            "rebalance_cost": str(self.rebalance_cost),
        }


@dataclass
class AllocationConfig:
    """Configuration for vault allocation simulation."""
    
    name: str
    market_ids: List[str]              # Markets to allocate across
    initial_capital: Decimal           # Starting capital (in USD or base asset)
    strategy: AllocationStrategy = AllocationStrategy.WATERFILL
    
    # Rebalancing
    rebalance_frequency_hours: int = 168  # Default: weekly (168h)
    rebalance_threshold: Decimal = Decimal("0.05")  # Rebalance if drift > 5%
    
    # Constraints
    min_allocation: Decimal = Decimal("0")      # Min weight per market (0-1)
    max_allocation: Decimal = Decimal("1")      # Max weight per market (0-1)
    
    # Simulation
    simulation_days: int = 90
    simulation_interval: str = "HOUR"
    
    # Custom weights (for CUSTOM strategy)
    custom_weights: Dict[str, Decimal] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "market_ids": self.market_ids,
            "initial_capital": str(self.initial_capital),
            "strategy": self.strategy.value,
            "rebalance_frequency_hours": self.rebalance_frequency_hours,
            "rebalance_threshold": str(self.rebalance_threshold),
            "min_allocation": str(self.min_allocation),
            "max_allocation": str(self.max_allocation),
            "simulation_days": self.simulation_days,
            "simulation_interval": self.simulation_interval,
            "custom_weights": {k: str(v) for k, v in self.custom_weights.items()},
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AllocationConfig":
        return cls(
            name=data["name"],
            market_ids=data["market_ids"],
            initial_capital=Decimal(data["initial_capital"]),
            strategy=AllocationStrategy(data.get("strategy", "waterfill")),
            rebalance_frequency_hours=data.get("rebalance_frequency_hours", 168),
            rebalance_threshold=Decimal(data.get("rebalance_threshold", "0.05")),
            min_allocation=Decimal(data.get("min_allocation", "0")),
            max_allocation=Decimal(data.get("max_allocation", "1")),
            simulation_days=data.get("simulation_days", 90),
            simulation_interval=data.get("simulation_interval", "HOUR"),
            custom_weights={k: Decimal(v) for k, v in data.get("custom_weights", {}).items()},
        )


@dataclass
class AllocationMetrics:
    """Aggregated metrics from allocation simulation."""
    
    # Returns
    total_return: Decimal
    total_return_pct: Decimal
    annualized_return: Decimal
    
    # Risk
    volatility: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    
    # Yield stats
    avg_weighted_apy: Decimal
    min_weighted_apy: Decimal
    max_weighted_apy: Decimal
    
    # Rebalancing
    rebalance_count: int
    total_rebalance_cost: Decimal
    
    # Comparison vs benchmark
    benchmark_return_pct: Decimal
    excess_return_pct: Decimal
    
    # Time
    simulation_days: int
    data_points: int

    def to_dict(self) -> dict:
        return {
            "total_return": str(self.total_return),
            "total_return_pct": str(self.total_return_pct),
            "annualized_return": str(self.annualized_return),
            "volatility": str(self.volatility),
            "sharpe_ratio": str(self.sharpe_ratio),
            "max_drawdown": str(self.max_drawdown),
            "avg_weighted_apy": str(self.avg_weighted_apy),
            "min_weighted_apy": str(self.min_weighted_apy),
            "max_weighted_apy": str(self.max_weighted_apy),
            "rebalance_count": self.rebalance_count,
            "total_rebalance_cost": str(self.total_rebalance_cost),
            "benchmark_return_pct": str(self.benchmark_return_pct),
            "excess_return_pct": str(self.excess_return_pct),
            "simulation_days": self.simulation_days,
            "data_points": self.data_points,
        }


@dataclass
class AllocationResult:
    """Complete result of allocation simulation."""
    
    config: AllocationConfig
    start_time: datetime
    end_time: datetime
    
    # Time series
    snapshots: List[AllocationSnapshot] = field(default_factory=list)
    
    # Benchmark (equal weight, no rebalancing)
    benchmark_snapshots: List[AllocationSnapshot] = field(default_factory=list)
    
    # Metrics
    metrics: Optional[AllocationMetrics] = None
    
    # Status
    success: bool = True
    error_message: str = ""
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    @property
    def duration_days(self) -> int:
        return (self.end_time - self.start_time).days
    
    @property
    def return_series(self) -> List[float]:
        """Extract return series for charting."""
        return [float(s.cumulative_return_pct) for s in self.snapshots]
    
    @property
    def benchmark_series(self) -> List[float]:
        """Extract benchmark return series."""
        return [float(s.cumulative_return_pct) for s in self.benchmark_snapshots]
    
    @property
    def apy_series(self) -> List[float]:
        """Extract weighted APY series."""
        return [float(s.weighted_apy) for s in self.snapshots]
    
    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "snapshots": [s.to_dict() for s in self.snapshots],
            "benchmark_snapshots": [s.to_dict() for s in self.benchmark_snapshots],
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
