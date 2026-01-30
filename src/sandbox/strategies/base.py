"""Base strategy abstract class."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional

from src.sandbox.models import (
    SimulatedPosition,
    StrategyConfig,
    SimulationResult,
    SimulationPoint,
)
from src.sandbox.data import DataAggregator


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Strategies implement the logic for:
    - Building initial positions
    - Updating positions based on market conditions
    - Managing risk (deleverage, rebalance)
    """

    def __init__(self, config: StrategyConfig, data: DataAggregator):
        """
        Initialize strategy.

        Args:
            config: Strategy configuration
            data: Data aggregator for market access
        """
        self.config = config
        self.data = data
        self._position: Optional[SimulatedPosition] = None

    @property
    def name(self) -> str:
        """Strategy name."""
        return self.config.name

    @property
    def market_id(self) -> str:
        """Target market ID."""
        return self.config.market_id

    @property
    def protocol(self) -> str:
        """Protocol name."""
        return self.config.protocol

    @property
    def position(self) -> Optional[SimulatedPosition]:
        """Current simulated position."""
        return self._position

    @abstractmethod
    async def build_position(
        self,
        capital: Decimal,
        entry_price: Decimal,
        supply_apy: Decimal,
        borrow_apy: Decimal,
        lltv: Decimal,
    ) -> SimulatedPosition:
        """
        Build the initial position for this strategy.

        Args:
            capital: Initial capital in collateral asset
            entry_price: Collateral/loan price ratio
            supply_apy: Current supply APY
            borrow_apy: Current borrow APY
            lltv: Market LLTV

        Returns:
            Simulated position
        """
        pass

    @abstractmethod
    def update_position(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
        supply_apy: Decimal,
        borrow_apy: Decimal,
    ) -> tuple[SimulatedPosition, str]:
        """
        Update position based on current market conditions.

        This handles:
        - APY updates
        - Rebalancing if needed
        - Deleveraging if health factor too low

        Args:
            position: Current position
            current_price: Current collateral/loan price
            supply_apy: Current supply APY
            borrow_apy: Current borrow APY

        Returns:
            Tuple of (updated position, action taken)
        """
        pass

    @abstractmethod
    def should_liquidate(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> bool:
        """
        Check if position would be liquidated.

        Args:
            position: Current position
            current_price: Current price

        Returns:
            True if position is liquidated
        """
        pass

    def calculate_pnl(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
        elapsed_days: Decimal,
    ) -> Decimal:
        """
        Calculate P&L for position.

        Args:
            position: Current position
            current_price: Current price
            elapsed_days: Days since entry

        Returns:
            P&L in loan asset terms
        """
        return position.pnl(current_price, elapsed_days)

    def calculate_pnl_percent(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
        elapsed_days: Decimal,
    ) -> Decimal:
        """Calculate P&L as percentage of initial capital."""
        return position.pnl_percent(current_price, elapsed_days)

    async def get_market_info(self) -> dict:
        """Get current market information."""
        market = await self.data.get_market(self.protocol, self.market_id)
        if not market:
            raise ValueError(f"Market not found: {self.market_id}")

        return {
            "market_id": market.id,
            "name": market.name,
            "collateral_symbol": market.collateral_asset_symbol,
            "loan_symbol": market.loan_asset_symbol,
            "lltv": market.lltv,
            "supply_apy": market.supply_apy,
            "borrow_apy": market.borrow_apy,
            "tvl": market.tvl,
        }
