"""Position data model for user positions in Morpho Blue markets."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .market import Market


@dataclass
class Position:
    """User position in a Morpho Blue market."""

    market_id: str
    user: str  # Wallet address

    # Supply position
    supply_shares: Decimal = Decimal("0")
    supply_assets: Decimal = Decimal("0")

    # Borrow position
    borrow_shares: Decimal = Decimal("0")
    borrow_assets: Decimal = Decimal("0")

    # Collateral
    collateral: Decimal = Decimal("0")

    # Timestamps
    last_update: Optional[datetime] = None

    # Reference to market (populated after fetching)
    market: Optional[Market] = None

    @property
    def is_supplier(self) -> bool:
        """Check if user is a supplier."""
        return self.supply_assets > 0

    @property
    def is_borrower(self) -> bool:
        """Check if user is a borrower."""
        return self.borrow_assets > 0

    @property
    def net_position(self) -> Decimal:
        """Net position (supply - borrow)."""
        return self.supply_assets - self.borrow_assets

    @property
    def health_factor(self) -> Optional[Decimal]:
        """Calculate health factor if borrowing."""
        if not self.is_borrower or not self.market:
            return None
        if self.borrow_assets == 0:
            return None

        # Simplified health factor calculation
        # HF = (collateral * LLTV) / borrow
        max_borrow = self.collateral * self.market.lltv
        return max_borrow / self.borrow_assets if self.borrow_assets > 0 else None

    @property
    def liquidation_price(self) -> Optional[Decimal]:
        """Calculate liquidation price for collateral."""
        if not self.is_borrower or not self.market:
            return None
        if self.collateral == 0:
            return None

        # Price at which position gets liquidated
        # liquidation_price = borrow / (collateral * LLTV)
        return self.borrow_assets / (self.collateral * self.market.lltv)

    def __hash__(self):
        return hash((self.market_id, self.user))

    def __eq__(self, other):
        if isinstance(other, Position):
            return self.market_id == other.market_id and self.user == other.user
        return False
