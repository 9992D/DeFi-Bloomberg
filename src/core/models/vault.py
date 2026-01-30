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


@dataclass
class VaultTimeseriesPoint:
    """Historical data point for vault charts."""

    timestamp: datetime
    apy: Decimal
    net_apy: Decimal
    total_assets: Decimal
    share_price: Optional[Decimal] = None


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
                    float(pct),
                    float(alloc.supply_assets_usd),
                ))

        # Sort by percentage descending
        result.sort(key=lambda x: x[1], reverse=True)
        return result
