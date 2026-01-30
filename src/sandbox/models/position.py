"""Simulated position model for sandbox strategies."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class SimulatedPosition:
    """
    Represents a simulated position in a Morpho market.

    For leverage loop wstETH/ETH:
    - supply_asset = wstETH (collateral)
    - borrow_asset = ETH (borrowed)
    - supply_amount = total wstETH deposited (after loops)
    - borrow_amount = total ETH borrowed
    """

    # Market identification
    market_id: str

    # Position amounts (in token units, not USD)
    supply_amount: Decimal          # Collateral deposited
    borrow_amount: Decimal          # Amount borrowed

    # Asset info
    supply_asset: str               # e.g., "wstETH"
    borrow_asset: str               # e.g., "ETH"

    # Entry info
    initial_capital: Decimal        # Original capital before leverage
    entry_price: Decimal            # Collateral/borrow price ratio at entry
    entry_timestamp: Optional[datetime] = None

    # Market parameters (snapshot at position creation)
    lltv: Decimal = Decimal("0")    # Liquidation LTV
    supply_apy: Decimal = Decimal("0")
    borrow_apy: Decimal = Decimal("0")

    @property
    def leverage(self) -> Decimal:
        """
        Effective leverage ratio.

        Leverage = Total Exposure / Initial Capital
        For leverage loop: supply_amount / initial_capital
        """
        if self.initial_capital == 0:
            return Decimal("1")
        return self.supply_amount / self.initial_capital

    @property
    def net_apy(self) -> Decimal:
        """
        Net APY considering leverage.

        Net APY = Supply APY * Leverage - Borrow APY * (Leverage - 1)

        Example at 3x leverage:
        - Supply 30 wstETH earning 4% = 1.2 wstETH/year
        - Borrow 20 ETH paying 2% = 0.4 ETH/year
        - Net on 10 initial = 0.8 / 10 = 8% net APY
        """
        if self.leverage <= 1:
            return self.supply_apy

        borrowed_ratio = self.leverage - 1
        return (self.supply_apy * self.leverage) - (self.borrow_apy * borrowed_ratio)

    def health_factor(self, current_price: Decimal) -> Decimal:
        """
        Calculate health factor at current price.

        HF = (Collateral Value * LLTV) / Borrow Value

        For wstETH/ETH:
        - Collateral Value = supply_amount * current_price (in ETH terms)
        - Borrow Value = borrow_amount (in ETH)

        Args:
            current_price: Current collateral/borrow price ratio

        Returns:
            Health factor (< 1.0 means liquidation)
        """
        if self.borrow_amount == 0:
            return Decimal("999")  # No borrow = infinite HF

        collateral_value = self.supply_amount * current_price
        max_borrow = collateral_value * self.lltv

        return max_borrow / self.borrow_amount

    def liquidation_price(self) -> Decimal:
        """
        Calculate price at which position gets liquidated (HF = 1.0).

        At liquidation: collateral_value * LLTV = borrow_value
        supply_amount * liq_price * LLTV = borrow_amount
        liq_price = borrow_amount / (supply_amount * LLTV)

        Returns:
            Liquidation price (collateral/borrow ratio)
        """
        if self.supply_amount == 0 or self.lltv == 0:
            return Decimal("0")

        return self.borrow_amount / (self.supply_amount * self.lltv)

    def pnl(self, current_price: Decimal, elapsed_days: Decimal) -> Decimal:
        """
        Calculate P&L in borrow asset terms.

        P&L components:
        1. Price appreciation: (current_price - entry_price) * supply_amount
        2. Supply yield: supply_amount * supply_apy * (days/365)
        3. Borrow cost: -borrow_amount * borrow_apy * (days/365)

        Args:
            current_price: Current collateral/borrow price ratio
            elapsed_days: Days since entry

        Returns:
            P&L in borrow asset terms
        """
        years = elapsed_days / Decimal("365")

        # Price change P&L (in borrow asset terms)
        price_pnl = (current_price - self.entry_price) * self.supply_amount

        # Yield P&L (autocompounded, simplified as linear for short periods)
        supply_yield = self.supply_amount * self.supply_apy * years * current_price
        borrow_cost = self.borrow_amount * self.borrow_apy * years

        return price_pnl + supply_yield - borrow_cost

    def pnl_percent(self, current_price: Decimal, elapsed_days: Decimal) -> Decimal:
        """P&L as percentage of initial capital."""
        if self.initial_capital == 0:
            return Decimal("0")

        pnl = self.pnl(current_price, elapsed_days)
        initial_value = self.initial_capital * self.entry_price

        return (pnl / initial_value) * 100

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "market_id": self.market_id,
            "supply_amount": str(self.supply_amount),
            "borrow_amount": str(self.borrow_amount),
            "supply_asset": self.supply_asset,
            "borrow_asset": self.borrow_asset,
            "initial_capital": str(self.initial_capital),
            "entry_price": str(self.entry_price),
            "entry_timestamp": self.entry_timestamp.isoformat() if self.entry_timestamp else None,
            "lltv": str(self.lltv),
            "supply_apy": str(self.supply_apy),
            "borrow_apy": str(self.borrow_apy),
            "leverage": str(self.leverage),
            "net_apy": str(self.net_apy),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulatedPosition":
        """Deserialize from dictionary."""
        return cls(
            market_id=data["market_id"],
            supply_amount=Decimal(data["supply_amount"]),
            borrow_amount=Decimal(data["borrow_amount"]),
            supply_asset=data["supply_asset"],
            borrow_asset=data["borrow_asset"],
            initial_capital=Decimal(data["initial_capital"]),
            entry_price=Decimal(data["entry_price"]),
            entry_timestamp=datetime.fromisoformat(data["entry_timestamp"]) if data.get("entry_timestamp") else None,
            lltv=Decimal(data.get("lltv", "0")),
            supply_apy=Decimal(data.get("supply_apy", "0")),
            borrow_apy=Decimal(data.get("borrow_apy", "0")),
        )
