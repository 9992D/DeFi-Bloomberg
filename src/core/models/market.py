"""Market and MarketState data models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


@dataclass
class MarketState:
    """Current state of a Morpho Blue market."""

    total_supply_assets: Decimal
    total_supply_shares: Decimal
    total_borrow_assets: Decimal
    total_borrow_shares: Decimal
    last_update: datetime
    fee: Decimal  # Protocol fee rate

    @property
    def utilization(self) -> Decimal:
        """Calculate current utilization rate."""
        if self.total_supply_assets == 0:
            return Decimal("0")
        return self.total_borrow_assets / self.total_supply_assets

    @property
    def available_liquidity(self) -> Decimal:
        """Calculate available liquidity for borrowing."""
        return self.total_supply_assets - self.total_borrow_assets

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "total_supply_assets": str(self.total_supply_assets),
            "total_supply_shares": str(self.total_supply_shares),
            "total_borrow_assets": str(self.total_borrow_assets),
            "total_borrow_shares": str(self.total_borrow_shares),
            "last_update": self.last_update.isoformat(),
            "fee": str(self.fee),
            "utilization": str(self.utilization),
            "available_liquidity": str(self.available_liquidity),
        }


@dataclass
class Market:
    """Morpho Blue market representation."""

    id: str  # Unique market identifier (hash)
    loan_asset: str  # Loan token address
    loan_asset_symbol: str
    loan_asset_decimals: int
    collateral_asset: str  # Collateral token address
    collateral_asset_symbol: str
    collateral_asset_decimals: int
    lltv: Decimal  # Liquidation LTV
    oracle: str  # Oracle address
    irm: str  # Interest Rate Model address

    # Creation date
    creation_timestamp: Optional[datetime] = None

    # Current rates (APY)
    supply_apy: Decimal = Decimal("0")
    borrow_apy: Decimal = Decimal("0")
    rate_at_target: Decimal = Decimal("0")

    # Asset prices (USD)
    loan_asset_price_usd: Decimal = Decimal("0")
    collateral_asset_price_usd: Decimal = Decimal("0")

    # Current state
    state: Optional[MarketState] = None

    # Timeseries data (populated on demand)
    timeseries: List["TimeseriesPoint"] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Human-readable market name."""
        return f"{self.collateral_asset_symbol}/{self.loan_asset_symbol}"

    @property
    def utilization(self) -> Decimal:
        """Get current utilization from state."""
        if self.state:
            return self.state.utilization
        return Decimal("0")

    @property
    def tvl(self) -> Decimal:
        """Total Value Locked in USD."""
        if not self.state or self.loan_asset_price_usd == 0:
            return Decimal("0")
        # Convert from raw units to token amount, then to USD
        token_amount = self.state.total_supply_assets / Decimal(10 ** self.loan_asset_decimals)
        return token_amount * self.loan_asset_price_usd

    @property
    def total_borrow_usd(self) -> Decimal:
        """Total borrow in USD."""
        if not self.state or self.loan_asset_price_usd == 0:
            return Decimal("0")
        token_amount = self.state.total_borrow_assets / Decimal(10 ** self.loan_asset_decimals)
        return token_amount * self.loan_asset_price_usd

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Market):
            return self.id == other.id
        return False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "loan_asset": self.loan_asset,
            "loan_asset_symbol": self.loan_asset_symbol,
            "loan_asset_decimals": self.loan_asset_decimals,
            "collateral_asset": self.collateral_asset,
            "collateral_asset_symbol": self.collateral_asset_symbol,
            "collateral_asset_decimals": self.collateral_asset_decimals,
            "lltv": str(self.lltv),
            "oracle": self.oracle,
            "irm": self.irm,
            "creation_timestamp": self.creation_timestamp.isoformat() if self.creation_timestamp else None,
            "supply_apy": str(self.supply_apy),
            "borrow_apy": str(self.borrow_apy),
            "rate_at_target": str(self.rate_at_target),
            "loan_asset_price_usd": str(self.loan_asset_price_usd),
            "collateral_asset_price_usd": str(self.collateral_asset_price_usd),
            "state": self.state.to_dict() if self.state else None,
            "name": self.name,
            "utilization": str(self.utilization),
            "tvl": str(self.tvl),
            "total_borrow_usd": str(self.total_borrow_usd),
        }
