"""Vault data models for Morpho MetaMorpho vaults."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


@dataclass
class VaultAllocation:
    """Allocation of vault assets to a specific market."""

    market_id: str
    loan_asset_symbol: str
    collateral_asset_symbol: Optional[str]  # None for idle market
    lltv: Decimal
    supply_assets: Decimal
    supply_assets_usd: Decimal
    supply_shares: Decimal

    @property
    def allocation_percent(self) -> Decimal:
        """Placeholder - calculated by Vault.get_allocation_percents()."""
        return Decimal("0")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "market_id": self.market_id,
            "loan_asset_symbol": self.loan_asset_symbol,
            "collateral_asset_symbol": self.collateral_asset_symbol,
            "lltv": str(self.lltv),
            "supply_assets": str(self.supply_assets),
            "supply_assets_usd": str(self.supply_assets_usd),
            "supply_shares": str(self.supply_shares),
        }


@dataclass
class VaultState:
    """Current state of a vault."""

    total_assets: Decimal
    total_assets_usd: Decimal
    total_supply: Decimal  # Total shares
    fee: Decimal
    share_price: Decimal
    share_price_usd: Decimal
    last_update: datetime
    allocation: List[VaultAllocation] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "total_assets": str(self.total_assets),
            "total_assets_usd": str(self.total_assets_usd),
            "total_supply": str(self.total_supply),
            "fee": str(self.fee),
            "share_price": str(self.share_price),
            "share_price_usd": str(self.share_price_usd),
            "last_update": self.last_update.isoformat(),
            "allocation": [a.to_dict() for a in self.allocation],
        }


@dataclass
class VaultTimeseriesPoint:
    """Historical data point for vault charts."""

    timestamp: datetime
    apy: Decimal
    net_apy: Decimal
    total_assets: Decimal
    share_price: Optional[Decimal] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "apy": str(self.apy),
            "net_apy": str(self.net_apy),
            "total_assets": str(self.total_assets),
            "share_price": str(self.share_price) if self.share_price else None,
        }


@dataclass
class Vault:
    """Morpho MetaMorpho vault."""

    id: str  # Vault address
    name: str
    symbol: str

    # Underlying asset
    asset_address: str
    asset_symbol: str
    asset_decimals: int
    asset_price_usd: Decimal

    # Yields
    apy: Decimal
    net_apy: Decimal

    # Optional fields with defaults
    creation_timestamp: Optional[datetime] = None
    state: Optional[VaultState] = None
    timeseries: List[VaultTimeseriesPoint] = field(default_factory=list)

    @property
    def tvl(self) -> Decimal:
        """Total Value Locked in USD."""
        if self.state:
            return self.state.total_assets_usd
        return Decimal("0")

    @property
    def share_price(self) -> Decimal:
        """Current share price."""
        if self.state:
            return self.state.share_price
        return Decimal("1")

    @property
    def total_shares(self) -> Decimal:
        """Total shares outstanding."""
        if self.state:
            return self.state.total_supply
        return Decimal("0")

    def get_allocation_percents(self) -> List[tuple]:
        """Get allocation percentages for each market."""
        if not self.state or not self.state.allocation:
            return []

        total = sum(a.supply_assets_usd for a in self.state.allocation)
        if total == 0:
            return []

        result = []
        for alloc in self.state.allocation:
            if alloc.supply_assets_usd > 0:
                pct = (alloc.supply_assets_usd / total) * 100
                collateral = alloc.collateral_asset_symbol or "Idle"
                result.append((
                    f"{alloc.loan_asset_symbol}/{collateral}",
                    pct,
                    alloc.supply_assets_usd,
                ))

        # Sort by percentage descending
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "symbol": self.symbol,
            "asset_address": self.asset_address,
            "asset_symbol": self.asset_symbol,
            "asset_decimals": self.asset_decimals,
            "asset_price_usd": str(self.asset_price_usd),
            "apy": str(self.apy),
            "net_apy": str(self.net_apy),
            "creation_timestamp": self.creation_timestamp.isoformat() if self.creation_timestamp else None,
            "state": self.state.to_dict() if self.state else None,
            "tvl": str(self.tvl),
            "share_price": str(self.share_price),
            "total_shares": str(self.total_shares),
        }
