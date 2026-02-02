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

    # Asset addresses for precise matching
    collateral_address: str = ""
    loan_address: str = ""

    # Current rates
    borrow_apy: Decimal = Decimal("0")
    supply_apy: Decimal = Decimal("0")
    utilization: Decimal = Decimal("0")

    # Market params
    lltv: Decimal = Decimal("0")
    available_liquidity: Decimal = Decimal("0")  # How much can be borrowed
    total_borrow: Decimal = Decimal("0")
    tvl: Decimal = Decimal("0")

    # LLTV-based risk metrics
    effective_max_leverage: Decimal = Decimal("0")  # 1 / (1 - LLTV)
    safe_leverage_at_lltv: Decimal = Decimal("0")  # Conservative leverage given LLTV

    # Rate volatility (from historical data)
    rate_volatility_24h: Decimal = Decimal("0")  # Std dev of rates over 24h
    rate_trend: Decimal = Decimal("0")  # Positive = rising, negative = falling

    # Predicted rate change (from IRM analysis)
    predicted_rate_1d: Optional[Decimal] = None
    predicted_rate_7d: Optional[Decimal] = None

    # Score for ranking (lower = better)
    # Incorporates: rate, LLTV risk, utilization, liquidity
    score: Decimal = Decimal("0")
    rate_score: Decimal = Decimal("0")  # Pure rate component
    risk_score: Decimal = Decimal("0")  # LLTV/utilization risk component
    liquidity_score: Decimal = Decimal("0")  # Liquidity availability component

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "collateral_symbol": self.collateral_symbol,
            "loan_symbol": self.loan_symbol,
            "collateral_address": self.collateral_address,
            "loan_address": self.loan_address,
            "borrow_apy": str(self.borrow_apy),
            "supply_apy": str(self.supply_apy),
            "utilization": str(self.utilization),
            "lltv": str(self.lltv),
            "available_liquidity": str(self.available_liquidity),
            "total_borrow": str(self.total_borrow),
            "tvl": str(self.tvl),
            "effective_max_leverage": str(self.effective_max_leverage),
            "safe_leverage_at_lltv": str(self.safe_leverage_at_lltv),
            "rate_volatility_24h": str(self.rate_volatility_24h),
            "rate_trend": str(self.rate_trend),
            "predicted_rate_1d": str(self.predicted_rate_1d) if self.predicted_rate_1d else None,
            "predicted_rate_7d": str(self.predicted_rate_7d) if self.predicted_rate_7d else None,
            "score": str(self.score),
            "rate_score": str(self.rate_score),
            "risk_score": str(self.risk_score),
            "liquidity_score": str(self.liquidity_score),
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

    # LTV-based metrics
    current_ltv: Decimal = Decimal("0")
    distance_to_liquidation_pct: Decimal = Decimal("0")  # % drop before liquidation
    margin_call_price: Decimal = Decimal("0")  # Price at which HF < margin_call_threshold

    # Interest estimates
    estimated_daily_interest: Decimal = Decimal("0")
    estimated_monthly_interest: Decimal = Decimal("0")
    estimated_annual_interest: Decimal = Decimal("0")

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
            "current_ltv": str(self.current_ltv),
            "distance_to_liquidation_pct": str(self.distance_to_liquidation_pct),
            "margin_call_price": str(self.margin_call_price),
            "estimated_daily_interest": str(self.estimated_daily_interest),
            "estimated_monthly_interest": str(self.estimated_monthly_interest),
            "estimated_annual_interest": str(self.estimated_annual_interest),
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

    # Price tracking for dynamic backtest
    collateral_price: Decimal = Decimal("0")
    current_health_factor: Decimal = Decimal("0")
    margin_call_triggered: bool = False

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
            "collateral_price": str(self.collateral_price),
            "current_health_factor": str(self.current_health_factor),
            "margin_call_triggered": self.margin_call_triggered,
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


class RebalancingMode(Enum):
    """Rebalancing strategy modes."""
    STATIC_THRESHOLD = "static_threshold"  # Fixed rate threshold
    DYNAMIC_RATE = "dynamic_rate"          # Adapt threshold to rate volatility
    PREDICTIVE = "predictive"              # Use IRM predictions
    OPPORTUNITY_COST = "opportunity_cost"  # Rebalance when savings > costs


@dataclass
class RebalancingConfig:
    """Configuration for debt rebalancing optimization."""

    # Asset pair - prefer addresses for precise matching
    collateral_asset: str  # Address (0x...) or symbol as fallback
    borrow_asset: str      # Address (0x...) or symbol as fallback

    # LTV-based position sizing (replaces leverage)
    collateral_amount: Decimal  # Amount of collateral in tokens
    initial_ltv: Decimal        # Target LTV (0.70 = 70%)

    # Protocol (Morpho only for v1)
    protocol: str = "morpho"

    # Rebalancing mode
    rebalancing_mode: RebalancingMode = RebalancingMode.DYNAMIC_RATE

    # Rebalancing parameters
    rate_threshold_bps: Decimal = Decimal("10")  # Base rate diff threshold (in bps)
    min_allocation_pct: Decimal = Decimal("0.05")  # Min allocation per market
    max_allocation_pct: Decimal = Decimal("0.80")  # Max allocation per market

    # Dynamic rebalancing parameters
    utilization_alert_threshold: Decimal = Decimal("0.90")  # Alert when util > 90%
    min_savings_to_rebalance: Decimal = Decimal("10")  # Min $ savings to trigger
    lookback_periods: int = 24  # Hours to analyze for rate volatility

    # Risk constraints
    min_health_factor: Decimal = Decimal("1.2")  # Minimum HF to maintain
    margin_call_threshold: Decimal = Decimal("1.15")  # HF threshold for alerts

    # Cost estimates
    gas_cost_usd: Decimal = Decimal("5")  # Estimated gas per rebalance
    slippage_bps: Decimal = Decimal("5")  # Expected slippage in bps

    # Simulation
    simulation_days: int = 30
    simulation_interval: str = "HOUR"

    # Calculated fields
    @property
    def total_debt(self) -> Decimal:
        """Calculate borrow amount based on collateral and LTV.

        borrow_amount = collateral_amount * initial_ltv
        """
        return self.collateral_amount * self.initial_ltv

    @property
    def uses_address_matching(self) -> bool:
        """Check if config uses address-based matching."""
        return self.collateral_asset.startswith("0x") and self.borrow_asset.startswith("0x")

    def to_dict(self) -> dict:
        return {
            "collateral_asset": self.collateral_asset,
            "borrow_asset": self.borrow_asset,
            "collateral_amount": str(self.collateral_amount),
            "initial_ltv": str(self.initial_ltv),
            "total_debt": str(self.total_debt),
            "protocol": self.protocol,
            "rebalancing_mode": self.rebalancing_mode.value,
            "rate_threshold_bps": str(self.rate_threshold_bps),
            "min_allocation_pct": str(self.min_allocation_pct),
            "max_allocation_pct": str(self.max_allocation_pct),
            "utilization_alert_threshold": str(self.utilization_alert_threshold),
            "min_savings_to_rebalance": str(self.min_savings_to_rebalance),
            "lookback_periods": self.lookback_periods,
            "min_health_factor": str(self.min_health_factor),
            "margin_call_threshold": str(self.margin_call_threshold),
            "gas_cost_usd": str(self.gas_cost_usd),
            "slippage_bps": str(self.slippage_bps),
            "simulation_days": self.simulation_days,
            "simulation_interval": self.simulation_interval,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RebalancingConfig":
        return cls(
            collateral_asset=data["collateral_asset"],
            borrow_asset=data["borrow_asset"],
            collateral_amount=Decimal(data["collateral_amount"]),
            initial_ltv=Decimal(data["initial_ltv"]),
            protocol=data.get("protocol", "morpho"),
            rebalancing_mode=RebalancingMode(data.get("rebalancing_mode", "dynamic_rate")),
            rate_threshold_bps=Decimal(data.get("rate_threshold_bps", "10")),
            min_allocation_pct=Decimal(data.get("min_allocation_pct", "0.05")),
            max_allocation_pct=Decimal(data.get("max_allocation_pct", "0.80")),
            utilization_alert_threshold=Decimal(data.get("utilization_alert_threshold", "0.90")),
            min_savings_to_rebalance=Decimal(data.get("min_savings_to_rebalance", "10")),
            lookback_periods=data.get("lookback_periods", 24),
            min_health_factor=Decimal(data.get("min_health_factor", "1.2")),
            margin_call_threshold=Decimal(data.get("margin_call_threshold", "1.15")),
            gas_cost_usd=Decimal(data.get("gas_cost_usd", "5")),
            slippage_bps=Decimal(data.get("slippage_bps", "5")),
            simulation_days=data.get("simulation_days", 30),
            simulation_interval=data.get("simulation_interval", "HOUR"),
        )


@dataclass
class RiskSnapshot:
    """Risk state at a given price scenario."""
    price_change_pct: Decimal  # e.g., -0.20 for -20%
    collateral_price: Decimal
    health_factor: Decimal
    current_ltv: Decimal
    distance_to_liquidation_pct: Decimal
    is_liquidatable: bool = False
    is_margin_call: bool = False  # HF below margin_call_threshold

    def to_dict(self) -> dict:
        return {
            "price_change_pct": str(self.price_change_pct),
            "collateral_price": str(self.collateral_price),
            "health_factor": str(self.health_factor),
            "current_ltv": str(self.current_ltv),
            "distance_to_liquidation_pct": str(self.distance_to_liquidation_pct),
            "is_liquidatable": self.is_liquidatable,
            "is_margin_call": self.is_margin_call,
        }


@dataclass
class PositionSummary:
    """Complete summary of a debt position with risk analysis."""

    # Position info
    collateral_asset: str
    collateral_symbol: str
    collateral_amount: Decimal
    borrow_asset: str
    borrow_symbol: str
    borrow_amount: Decimal
    collateral_price: Decimal  # Current price of collateral in borrow asset terms

    # LTV metrics
    initial_ltv: Decimal
    current_ltv: Decimal
    max_ltv: Decimal  # LLTV from the market

    # Risk metrics
    health_factor: Decimal
    liquidation_price: Decimal
    distance_to_liquidation_pct: Decimal
    margin_call_price: Decimal
    margin_call_threshold: Decimal

    # Cost metrics
    borrow_apy: Decimal
    estimated_daily_interest: Decimal
    estimated_monthly_interest: Decimal
    estimated_annual_interest: Decimal

    # Price scenarios
    price_scenarios: List[RiskSnapshot] = field(default_factory=list)

    # Alerts
    alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "collateral_asset": self.collateral_asset,
            "collateral_symbol": self.collateral_symbol,
            "collateral_amount": str(self.collateral_amount),
            "borrow_asset": self.borrow_asset,
            "borrow_symbol": self.borrow_symbol,
            "borrow_amount": str(self.borrow_amount),
            "collateral_price": str(self.collateral_price),
            "initial_ltv": str(self.initial_ltv),
            "current_ltv": str(self.current_ltv),
            "max_ltv": str(self.max_ltv),
            "health_factor": str(self.health_factor),
            "liquidation_price": str(self.liquidation_price),
            "distance_to_liquidation_pct": str(self.distance_to_liquidation_pct),
            "margin_call_price": str(self.margin_call_price),
            "margin_call_threshold": str(self.margin_call_threshold),
            "borrow_apy": str(self.borrow_apy),
            "estimated_daily_interest": str(self.estimated_daily_interest),
            "estimated_monthly_interest": str(self.estimated_monthly_interest),
            "estimated_annual_interest": str(self.estimated_annual_interest),
            "price_scenarios": [s.to_dict() for s in self.price_scenarios],
            "alerts": self.alerts,
        }


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

    # Position summary with risk analysis
    position_summary: Optional[PositionSummary] = None

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

    @property
    def health_factor_series(self) -> List[float]:
        """Extract health factor series from simulation snapshots."""
        return [float(s.current_health_factor) for s in self.snapshots if s.current_health_factor > 0]

    @property
    def collateral_price_series(self) -> List[float]:
        """Extract collateral price series from simulation snapshots."""
        return [float(s.collateral_price) for s in self.snapshots if s.collateral_price > 0]

    @property
    def margin_call_count(self) -> int:
        """Count number of margin call events during simulation."""
        return sum(1 for s in self.snapshots if s.margin_call_triggered)

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
            "position_summary": self.position_summary.to_dict() if self.position_summary else None,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
