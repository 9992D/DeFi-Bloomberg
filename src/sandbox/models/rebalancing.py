"""Debt rebalancing optimization models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional


class RebalancingTrigger(Enum):
    """Triggers for rebalancing."""
    RATE_DIFF = "rate_diff"        # Rate differential exceeds threshold
    TIME_BASED = "time_based"       # Periodic rebalancing
    HEALTH_FACTOR = "health_factor"  # Health factor below threshold


@dataclass
class MarketDebtInfo:
    """Market information for debt comparison."""
    market_id: str
    market_name: str
    collateral_symbol: str
    loan_symbol: str

    # Current rates
    borrow_apy: Decimal
    supply_apy: Decimal
    utilization: Decimal

    # Market params
    lltv: Decimal
    available_liquidity: Decimal  # How much can be borrowed
    total_borrow: Decimal
    tvl: Decimal

    # Predicted rate change (from IRM analysis)
    predicted_rate_1d: Optional[Decimal] = None
    predicted_rate_7d: Optional[Decimal] = None

    # Score for ranking (lower = better)
    score: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "collateral_symbol": self.collateral_symbol,
            "loan_symbol": self.loan_symbol,
            "borrow_apy": str(self.borrow_apy),
            "supply_apy": str(self.supply_apy),
            "utilization": str(self.utilization),
            "lltv": str(self.lltv),
            "available_liquidity": str(self.available_liquidity),
            "total_borrow": str(self.total_borrow),
            "tvl": str(self.tvl),
            "predicted_rate_1d": str(self.predicted_rate_1d) if self.predicted_rate_1d else None,
            "predicted_rate_7d": str(self.predicted_rate_7d) if self.predicted_rate_7d else None,
            "score": str(self.score),
        }


@dataclass
class DebtPosition:
    """Current debt position in a market."""
    market_id: str
    market_name: str

    collateral_amount: Decimal
    borrow_amount: Decimal

    # Current rates
    borrow_apy: Decimal

    # Risk metrics
    health_factor: Decimal
    liquidation_price: Decimal

    # Weight in portfolio (0-1)
    allocation_weight: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "collateral_amount": str(self.collateral_amount),
            "borrow_amount": str(self.borrow_amount),
            "borrow_apy": str(self.borrow_apy),
            "health_factor": str(self.health_factor),
            "liquidation_price": str(self.liquidation_price),
            "allocation_weight": str(self.allocation_weight),
        }


@dataclass
class RebalancingOpportunity:
    """A rebalancing recommendation with cost/benefit analysis."""
    trigger: RebalancingTrigger

    # Source and destination
    from_market_id: str
    from_market_name: str
    to_market_id: str
    to_market_name: str

    # Amounts to move
    debt_amount: Decimal
    collateral_amount: Decimal

    # Rates
    from_rate: Decimal
    to_rate: Decimal
    rate_diff_bps: Decimal  # Basis points savings

    # Cost analysis
    estimated_gas_cost: Decimal  # In USD
    estimated_slippage_cost: Decimal  # In USD
    total_cost: Decimal

    # Benefit analysis
    annual_savings: Decimal  # In loan asset
    monthly_savings: Decimal
    daily_savings: Decimal

    # Breakeven
    breakeven_days: Decimal
    net_benefit_30d: Decimal

    # Score (higher = better opportunity)
    opportunity_score: Decimal = Decimal("0")

    @property
    def is_profitable_30d(self) -> bool:
        """Check if opportunity is profitable within 30 days."""
        return self.net_benefit_30d > 0

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger.value,
            "from_market_id": self.from_market_id,
            "from_market_name": self.from_market_name,
            "to_market_id": self.to_market_id,
            "to_market_name": self.to_market_name,
            "debt_amount": str(self.debt_amount),
            "collateral_amount": str(self.collateral_amount),
            "from_rate": str(self.from_rate),
            "to_rate": str(self.to_rate),
            "rate_diff_bps": str(self.rate_diff_bps),
            "estimated_gas_cost": str(self.estimated_gas_cost),
            "estimated_slippage_cost": str(self.estimated_slippage_cost),
            "total_cost": str(self.total_cost),
            "annual_savings": str(self.annual_savings),
            "monthly_savings": str(self.monthly_savings),
            "daily_savings": str(self.daily_savings),
            "breakeven_days": str(self.breakeven_days),
            "net_benefit_30d": str(self.net_benefit_30d),
            "opportunity_score": str(self.opportunity_score),
        }


@dataclass
class RebalancingSnapshot:
    """Snapshot of debt position during simulation."""
    timestamp: datetime

    # Position state
    positions: List[DebtPosition]
    total_debt: Decimal
    total_collateral: Decimal

    # Rates
    weighted_borrow_apy: Decimal

    # Cumulative costs
    cumulative_interest: Decimal
    cumulative_rebalance_cost: Decimal

    # Events
    rebalanced: bool = False
    rebalance_trigger: Optional[RebalancingTrigger] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "positions": [p.to_dict() for p in self.positions],
            "total_debt": str(self.total_debt),
            "total_collateral": str(self.total_collateral),
            "weighted_borrow_apy": str(self.weighted_borrow_apy),
            "cumulative_interest": str(self.cumulative_interest),
            "cumulative_rebalance_cost": str(self.cumulative_rebalance_cost),
            "rebalanced": self.rebalanced,
            "rebalance_trigger": self.rebalance_trigger.value if self.rebalance_trigger else None,
        }


@dataclass
class RebalancingMetrics:
    """Aggregated metrics from rebalancing simulation."""

    # Interest costs
    total_interest_paid: Decimal
    benchmark_interest_paid: Decimal  # Static position interest
    interest_savings: Decimal
    interest_savings_pct: Decimal

    # Rates
    avg_weighted_borrow_apy: Decimal
    min_weighted_borrow_apy: Decimal
    max_weighted_borrow_apy: Decimal
    benchmark_avg_borrow_apy: Decimal

    # Rebalancing activity
    rebalance_count: int
    total_rebalance_cost: Decimal
    avg_rate_diff_trigger_bps: Decimal

    # Net benefit
    net_savings: Decimal  # After rebalancing costs
    net_savings_annualized: Decimal

    # Time
    simulation_days: int
    data_points: int

    def to_dict(self) -> dict:
        return {
            "total_interest_paid": str(self.total_interest_paid),
            "benchmark_interest_paid": str(self.benchmark_interest_paid),
            "interest_savings": str(self.interest_savings),
            "interest_savings_pct": str(self.interest_savings_pct),
            "avg_weighted_borrow_apy": str(self.avg_weighted_borrow_apy),
            "min_weighted_borrow_apy": str(self.min_weighted_borrow_apy),
            "max_weighted_borrow_apy": str(self.max_weighted_borrow_apy),
            "benchmark_avg_borrow_apy": str(self.benchmark_avg_borrow_apy),
            "rebalance_count": self.rebalance_count,
            "total_rebalance_cost": str(self.total_rebalance_cost),
            "avg_rate_diff_trigger_bps": str(self.avg_rate_diff_trigger_bps),
            "net_savings": str(self.net_savings),
            "net_savings_annualized": str(self.net_savings_annualized),
            "simulation_days": self.simulation_days,
            "data_points": self.data_points,
        }


@dataclass
class RebalancingConfig:
    """Configuration for debt rebalancing optimization."""

    # Asset pair
    collateral_asset: str  # e.g., "wstETH"
    borrow_asset: str      # e.g., "WETH"

    # Position size
    total_debt: Decimal    # Total debt to allocate
    target_leverage: Decimal  # Target leverage ratio

    # Protocol (Morpho only for v1)
    protocol: str = "morpho"

    # Rebalancing parameters
    rate_threshold_bps: Decimal = Decimal("10")  # Min rate diff to trigger (in bps)
    min_allocation_pct: Decimal = Decimal("0.05")  # Min allocation per market
    max_allocation_pct: Decimal = Decimal("0.80")  # Max allocation per market

    # Cost estimates
    gas_cost_usd: Decimal = Decimal("5")  # Estimated gas per rebalance
    slippage_bps: Decimal = Decimal("5")  # Expected slippage in bps

    # Simulation
    simulation_days: int = 30
    simulation_interval: str = "HOUR"

    # Calculated fields
    @property
    def required_collateral(self) -> Decimal:
        """Calculate collateral required for leverage target.

        For leverage L:
        - collateral = debt / (L - 1)
        """
        if self.target_leverage <= 1:
            return self.total_debt
        return self.total_debt / (self.target_leverage - 1)

    def to_dict(self) -> dict:
        return {
            "collateral_asset": self.collateral_asset,
            "borrow_asset": self.borrow_asset,
            "total_debt": str(self.total_debt),
            "target_leverage": str(self.target_leverage),
            "protocol": self.protocol,
            "rate_threshold_bps": str(self.rate_threshold_bps),
            "min_allocation_pct": str(self.min_allocation_pct),
            "max_allocation_pct": str(self.max_allocation_pct),
            "gas_cost_usd": str(self.gas_cost_usd),
            "slippage_bps": str(self.slippage_bps),
            "simulation_days": self.simulation_days,
            "simulation_interval": self.simulation_interval,
            "required_collateral": str(self.required_collateral),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RebalancingConfig":
        return cls(
            collateral_asset=data["collateral_asset"],
            borrow_asset=data["borrow_asset"],
            total_debt=Decimal(data["total_debt"]),
            target_leverage=Decimal(data["target_leverage"]),
            protocol=data.get("protocol", "morpho"),
            rate_threshold_bps=Decimal(data.get("rate_threshold_bps", "10")),
            min_allocation_pct=Decimal(data.get("min_allocation_pct", "0.05")),
            max_allocation_pct=Decimal(data.get("max_allocation_pct", "0.80")),
            gas_cost_usd=Decimal(data.get("gas_cost_usd", "5")),
            slippage_bps=Decimal(data.get("slippage_bps", "5")),
            simulation_days=data.get("simulation_days", 30),
            simulation_interval=data.get("simulation_interval", "HOUR"),
        )


@dataclass
class RebalancingResult:
    """Complete result of debt rebalancing optimization."""

    config: RebalancingConfig
    start_time: datetime
    end_time: datetime

    # Available markets
    available_markets: List[MarketDebtInfo] = field(default_factory=list)

    # Optimal allocation
    optimal_allocation: Dict[str, Decimal] = field(default_factory=dict)
    optimal_positions: List[DebtPosition] = field(default_factory=list)

    # Rebalancing opportunities
    opportunities: List[RebalancingOpportunity] = field(default_factory=list)

    # Simulation results
    snapshots: List[RebalancingSnapshot] = field(default_factory=list)
    benchmark_snapshots: List[RebalancingSnapshot] = field(default_factory=list)

    # Metrics
    metrics: Optional[RebalancingMetrics] = None

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
    def borrow_apy_series(self) -> List[float]:
        """Extract weighted borrow APY series for charting."""
        return [float(s.weighted_borrow_apy) for s in self.snapshots]

    @property
    def benchmark_apy_series(self) -> List[float]:
        """Extract benchmark borrow APY series."""
        return [float(s.weighted_borrow_apy) for s in self.benchmark_snapshots]

    @property
    def cumulative_interest_series(self) -> List[float]:
        """Extract cumulative interest series."""
        return [float(s.cumulative_interest) for s in self.snapshots]

    @property
    def benchmark_interest_series(self) -> List[float]:
        """Extract benchmark cumulative interest series."""
        return [float(s.cumulative_interest) for s in self.benchmark_snapshots]

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "available_markets": [m.to_dict() for m in self.available_markets],
            "optimal_allocation": {k: str(v) for k, v in self.optimal_allocation.items()},
            "optimal_positions": [p.to_dict() for p in self.optimal_positions],
            "opportunities": [o.to_dict() for o in self.opportunities],
            "snapshots": [s.to_dict() for s in self.snapshots],
            "benchmark_snapshots": [s.to_dict() for s in self.benchmark_snapshots],
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
