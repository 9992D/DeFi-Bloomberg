"""Strategy configuration models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional


class StrategyType(Enum):
    """Available strategy types."""
    LEVERAGE_LOOP = "leverage_loop"
    REBALANCING = "rebalancing"
    YIELD_OPTIMIZER = "yield_optimizer"
    DELTA_NEUTRAL = "delta_neutral"


@dataclass
class StrategyConstraints:
    """
    Risk constraints for strategy execution.

    These define the boundaries within which the strategy operates.
    """

    # Leverage limits
    max_leverage: Decimal = Decimal("5.0")
    min_leverage: Decimal = Decimal("1.0")

    # Health factor limits
    min_health_factor: Decimal = Decimal("1.2")      # Minimum HF to maintain
    target_health_factor: Decimal = Decimal("1.5")   # Target HF for new positions
    emergency_health_factor: Decimal = Decimal("1.1")  # Trigger emergency deleverage

    # Position size limits
    max_position_size_usd: Decimal = Decimal("1000000")
    min_position_size_usd: Decimal = Decimal("100")

    # Rebalancing thresholds
    rebalance_threshold: Decimal = Decimal("0.05")   # 5% deviation triggers rebalance

    # Slippage (0 for wstETH/ETH)
    max_slippage: Decimal = Decimal("0.0")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "max_leverage": str(self.max_leverage),
            "min_leverage": str(self.min_leverage),
            "min_health_factor": str(self.min_health_factor),
            "target_health_factor": str(self.target_health_factor),
            "emergency_health_factor": str(self.emergency_health_factor),
            "max_position_size_usd": str(self.max_position_size_usd),
            "min_position_size_usd": str(self.min_position_size_usd),
            "rebalance_threshold": str(self.rebalance_threshold),
            "max_slippage": str(self.max_slippage),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConstraints":
        """Deserialize from dictionary."""
        return cls(
            max_leverage=Decimal(data.get("max_leverage", "5.0")),
            min_leverage=Decimal(data.get("min_leverage", "1.0")),
            min_health_factor=Decimal(data.get("min_health_factor", "1.2")),
            target_health_factor=Decimal(data.get("target_health_factor", "1.5")),
            emergency_health_factor=Decimal(data.get("emergency_health_factor", "1.1")),
            max_position_size_usd=Decimal(data.get("max_position_size_usd", "1000000")),
            min_position_size_usd=Decimal(data.get("min_position_size_usd", "100")),
            rebalance_threshold=Decimal(data.get("rebalance_threshold", "0.05")),
            max_slippage=Decimal(data.get("max_slippage", "0.0")),
        )


@dataclass
class StrategyConfig:
    """
    Configuration for a strategy instance.

    This defines what strategy to run and with what parameters.
    """

    # Identification
    name: str
    strategy_type: StrategyType

    # Target market/vault
    market_id: str

    # Capital
    initial_capital: Decimal          # In collateral asset units

    # Optional fields with defaults
    protocol: str = "morpho"          # For future multi-protocol support
    initial_capital_asset: str = ""   # e.g., "wstETH"

    # Strategy-specific parameters
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Risk constraints
    constraints: StrategyConstraints = field(default_factory=StrategyConstraints)

    # Simulation settings
    simulation_days: int = 90
    simulation_interval: str = "HOUR"  # HOUR, DAY, WEEK

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    description: str = ""

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a strategy parameter with default."""
        return self.parameters.get(key, default)

    def set_param(self, key: str, value: Any) -> None:
        """Set a strategy parameter."""
        self.parameters[key] = value
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "market_id": self.market_id,
            "protocol": self.protocol,
            "initial_capital": str(self.initial_capital),
            "initial_capital_asset": self.initial_capital_asset,
            "parameters": self.parameters,
            "constraints": self.constraints.to_dict(),
            "simulation_days": self.simulation_days,
            "simulation_interval": self.simulation_interval,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyConfig":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            strategy_type=StrategyType(data["strategy_type"]),
            market_id=data["market_id"],
            protocol=data.get("protocol", "morpho"),
            initial_capital=Decimal(data["initial_capital"]),
            initial_capital_asset=data.get("initial_capital_asset", ""),
            parameters=data.get("parameters", {}),
            constraints=StrategyConstraints.from_dict(data.get("constraints", {})),
            simulation_days=data.get("simulation_days", 90),
            simulation_interval=data.get("simulation_interval", "HOUR"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            description=data.get("description", ""),
        )


@dataclass
class LeverageLoopParams:
    """
    Parameters specific to leverage loop strategy.

    Usage:
        config.parameters = LeverageLoopParams(target_leverage=3.0).to_dict()
    """

    target_leverage: Decimal = Decimal("3.0")    # Target leverage ratio
    max_loops: int = 10                          # Max iterations for looping
    deleverage_at_hf: Decimal = Decimal("1.15")  # HF threshold to deleverage
    releverage_at_hf: Decimal = Decimal("1.8")   # HF threshold to add leverage

    def to_dict(self) -> dict:
        return {
            "target_leverage": str(self.target_leverage),
            "max_loops": self.max_loops,
            "deleverage_at_hf": str(self.deleverage_at_hf),
            "releverage_at_hf": str(self.releverage_at_hf),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LeverageLoopParams":
        return cls(
            target_leverage=Decimal(data.get("target_leverage", "3.0")),
            max_loops=int(data.get("max_loops", 10)),
            deleverage_at_hf=Decimal(data.get("deleverage_at_hf", "1.15")),
            releverage_at_hf=Decimal(data.get("releverage_at_hf", "1.8")),
        )
