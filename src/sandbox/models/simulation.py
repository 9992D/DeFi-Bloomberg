"""Simulation result models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from .position import SimulatedPosition
from src.data.sources.risk_free_rates import get_risk_free_rate_sync


@dataclass
class SimulationPoint:
    """
    A single point in time during simulation.

    Captures the state of the position and market at a specific timestamp.
    """

    timestamp: datetime

    # Position state
    supply_amount: Decimal
    borrow_amount: Decimal
    leverage: Decimal
    health_factor: Decimal

    # Market state
    collateral_price: Decimal       # Collateral/borrow price ratio
    supply_apy: Decimal
    borrow_apy: Decimal

    # Performance
    pnl: Decimal                    # Cumulative P&L in borrow asset
    pnl_percent: Decimal            # P&L as % of initial capital
    net_apy: Decimal                # Current net APY

    # Events
    liquidated: bool = False
    rebalanced: bool = False
    action: str = ""                # Description of action taken

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "supply_amount": str(self.supply_amount),
            "borrow_amount": str(self.borrow_amount),
            "leverage": str(self.leverage),
            "health_factor": str(self.health_factor),
            "collateral_price": str(self.collateral_price),
            "supply_apy": str(self.supply_apy),
            "borrow_apy": str(self.borrow_apy),
            "pnl": str(self.pnl),
            "pnl_percent": str(self.pnl_percent),
            "net_apy": str(self.net_apy),
            "liquidated": self.liquidated,
            "rebalanced": self.rebalanced,
            "action": self.action,
        }


@dataclass
class SimulationMetrics:
    """Aggregated metrics from a simulation run."""

    # Returns
    total_return: Decimal           # Total P&L in borrow asset
    total_return_percent: Decimal   # Total return as %
    annualized_return: Decimal      # Annualized return %

    # Risk metrics
    max_drawdown: Decimal           # Maximum drawdown %
    volatility: Decimal             # Annualized volatility of returns
    sharpe_ratio: Decimal           # Sharpe ratio (with dynamic risk-free rate)
    sortino_ratio: Decimal          # Sortino ratio (with dynamic risk-free rate)

    # Health factor stats
    avg_health_factor: Decimal
    min_health_factor: Decimal
    max_health_factor: Decimal

    # Events
    liquidation_count: int
    rebalance_count: int

    # Position stats
    avg_leverage: Decimal
    max_leverage: Decimal

    # Time
    simulation_days: int
    data_points: int

    # Risk-free rate used (with default for backward compatibility)
    risk_free_rate: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        return {
            "total_return": str(self.total_return),
            "total_return_percent": str(self.total_return_percent),
            "annualized_return": str(self.annualized_return),
            "max_drawdown": str(self.max_drawdown),
            "volatility": str(self.volatility),
            "sharpe_ratio": str(self.sharpe_ratio),
            "sortino_ratio": str(self.sortino_ratio),
            "risk_free_rate": str(self.risk_free_rate),
            "avg_health_factor": str(self.avg_health_factor),
            "min_health_factor": str(self.min_health_factor),
            "max_health_factor": str(self.max_health_factor),
            "liquidation_count": self.liquidation_count,
            "rebalance_count": self.rebalance_count,
            "avg_leverage": str(self.avg_leverage),
            "max_leverage": str(self.max_leverage),
            "simulation_days": self.simulation_days,
            "data_points": self.data_points,
        }


@dataclass
class SimulationResult:
    """
    Complete result of a strategy simulation.

    Contains the full time series and aggregated metrics.
    """

    # Configuration used
    strategy_name: str
    strategy_type: str
    market_id: str
    initial_capital: Decimal

    # Time range
    start_time: datetime
    end_time: datetime

    # Final position
    final_position: Optional[SimulatedPosition] = None

    # Loan asset for risk-free rate calculation (with defaults for backward compatibility)
    loan_asset_address: str = ""
    loan_asset_symbol: str = ""

    # Time series data
    points: List[SimulationPoint] = field(default_factory=list)

    # Aggregated metrics
    metrics: Optional[SimulationMetrics] = None

    # Status
    success: bool = True
    error_message: str = ""

    # Metadata
    created_at: Optional[datetime] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    @property
    def duration_days(self) -> int:
        """Duration of simulation in days."""
        return (self.end_time - self.start_time).days

    @property
    def pnl_series(self) -> List[float]:
        """Extract P&L series for charting."""
        return [float(p.pnl_percent) for p in self.points]

    @property
    def health_factor_series(self) -> List[float]:
        """Extract health factor series for charting."""
        return [float(p.health_factor) for p in self.points]

    @property
    def price_series(self) -> List[float]:
        """Extract price series for charting."""
        return [float(p.collateral_price) for p in self.points]

    @property
    def timestamps(self) -> List[datetime]:
        """Extract timestamps for charting."""
        return [p.timestamp for p in self.points]

    def calculate_metrics(self) -> SimulationMetrics:
        """Calculate aggregated metrics from points."""
        if not self.points:
            return SimulationMetrics(
                total_return=Decimal("0"),
                total_return_percent=Decimal("0"),
                annualized_return=Decimal("0"),
                max_drawdown=Decimal("0"),
                volatility=Decimal("0"),
                sharpe_ratio=Decimal("0"),
                sortino_ratio=Decimal("0"),
                avg_health_factor=Decimal("0"),
                min_health_factor=Decimal("0"),
                max_health_factor=Decimal("0"),
                liquidation_count=0,
                rebalance_count=0,
                avg_leverage=Decimal("0"),
                max_leverage=Decimal("0"),
                simulation_days=0,
                data_points=0,
            )

        import statistics

        # P&L metrics
        final_pnl = self.points[-1].pnl
        final_pnl_pct = self.points[-1].pnl_percent
        days = self.duration_days or 1
        annualized = ((1 + float(final_pnl_pct) / 100) ** (365 / days) - 1) * 100

        # Max drawdown
        peak_pnl = float(self.points[0].pnl_percent)
        max_dd = 0.0
        for p in self.points:
            pnl = float(p.pnl_percent)
            if pnl > peak_pnl:
                peak_pnl = pnl
            dd = peak_pnl - pnl
            if dd > max_dd:
                max_dd = dd

        # Volatility (of returns)
        pnl_values = [float(p.pnl_percent) for p in self.points]
        returns = []
        for i in range(1, len(pnl_values)):
            r = pnl_values[i] - pnl_values[i - 1]
            returns.append(r)

        vol = Decimal("0")
        sharpe = Decimal("0")
        sortino = Decimal("0")

        # Get dynamic risk-free rate based on loan asset
        risk_free_rate_decimal = 0.0
        if self.loan_asset_address or self.loan_asset_symbol:
            risk_free_rate_decimal, _ = get_risk_free_rate_sync(
                loan_asset_address=self.loan_asset_address,
                loan_asset_symbol=self.loan_asset_symbol,
            )
        risk_free_rate_pct = risk_free_rate_decimal * 100  # Convert to percentage

        if len(returns) > 1:
            vol = Decimal(str(statistics.stdev(returns)))
            ann_vol = vol * Decimal(str(365 ** 0.5))

            if ann_vol > 0:
                # Sharpe = (annualized return - risk-free rate) / volatility
                excess_return = annualized - risk_free_rate_pct
                sharpe = Decimal(str(excess_return)) / ann_vol

                # Sortino (downside only, below risk-free rate)
                downside = [r for r in returns if r < risk_free_rate_pct / 365]  # Daily risk-free
                if len(downside) > 1:
                    down_vol = Decimal(str(statistics.stdev(downside))) * Decimal(str(365 ** 0.5))
                    if down_vol > 0:
                        sortino = Decimal(str(excess_return)) / down_vol

        # Health factor stats
        hf_values = [float(p.health_factor) for p in self.points if p.health_factor < 100]
        avg_hf = Decimal(str(statistics.mean(hf_values))) if hf_values else Decimal("0")
        min_hf = Decimal(str(min(hf_values))) if hf_values else Decimal("0")
        max_hf = Decimal(str(max(hf_values))) if hf_values else Decimal("0")

        # Event counts
        liquidations = sum(1 for p in self.points if p.liquidated)
        rebalances = sum(1 for p in self.points if p.rebalanced)

        # Leverage stats
        leverage_values = [float(p.leverage) for p in self.points]
        avg_leverage = Decimal(str(statistics.mean(leverage_values)))
        max_leverage = Decimal(str(max(leverage_values)))

        self.metrics = SimulationMetrics(
            total_return=final_pnl,
            total_return_percent=final_pnl_pct,
            annualized_return=Decimal(str(annualized)),
            max_drawdown=Decimal(str(max_dd)),
            volatility=vol,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            risk_free_rate=Decimal(str(risk_free_rate_pct)),
            avg_health_factor=avg_hf,
            min_health_factor=min_hf,
            max_health_factor=max_hf,
            liquidation_count=liquidations,
            rebalance_count=rebalances,
            avg_leverage=avg_leverage,
            max_leverage=max_leverage,
            simulation_days=days,
            data_points=len(self.points),
        )

        return self.metrics

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "market_id": self.market_id,
            "initial_capital": str(self.initial_capital),
            "loan_asset_address": self.loan_asset_address,
            "loan_asset_symbol": self.loan_asset_symbol,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "final_position": self.final_position.to_dict() if self.final_position else None,
            "points": [p.to_dict() for p in self.points],
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "success": self.success,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "parameters": self.parameters,
        }
