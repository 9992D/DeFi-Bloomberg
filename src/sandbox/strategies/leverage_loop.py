"""Leverage Loop strategy implementation."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.sandbox.models import (
    SimulatedPosition,
    StrategyConfig,
    StrategyConstraints,
    SimulationResult,
    SimulationPoint,
)
from src.sandbox.models.strategy import LeverageLoopParams
from src.sandbox.data import DataAggregator
from src.sandbox.engine.risk import RiskCalculator
from src.sandbox.strategies.base import BaseStrategy


class LeverageLoopStrategy(BaseStrategy):
    """
    Leverage Loop Strategy for yield amplification.

    This strategy:
    1. Deposits collateral (e.g., wstETH)
    2. Borrows loan asset (e.g., ETH)
    3. Swaps borrowed asset back to collateral
    4. Re-deposits to increase exposure
    5. Repeats until target leverage is reached

    Profit comes from: collateral_yield > borrow_cost
    Risk: collateral depegs vs loan asset → liquidation

    Example wstETH/ETH at 3x:
    - Deposit 10 wstETH
    - Borrow ~20 ETH worth
    - Swap to ~17 wstETH
    - Re-deposit → total 27 wstETH
    - Continue until 30 wstETH, 20 ETH borrow
    - Net APY = 3 * supply_apy - 2 * borrow_apy
    """

    def __init__(self, config: StrategyConfig, data: DataAggregator):
        super().__init__(config, data)

        # Parse strategy-specific parameters
        params = LeverageLoopParams.from_dict(config.parameters)
        self.target_leverage = params.target_leverage
        self.max_loops = params.max_loops
        self.deleverage_at_hf = params.deleverage_at_hf
        self.releverage_at_hf = params.releverage_at_hf

        self.risk_calc = RiskCalculator()

    @property
    def params(self) -> LeverageLoopParams:
        """Get typed parameters."""
        return LeverageLoopParams.from_dict(self.config.parameters)

    async def build_position(
        self,
        capital: Decimal,
        entry_price: Decimal,
        supply_apy: Decimal,
        borrow_apy: Decimal,
        lltv: Decimal,
    ) -> SimulatedPosition:
        """
        Build leveraged position through looping.

        Args:
            capital: Initial capital in collateral asset (e.g., 10 wstETH)
            entry_price: Collateral/loan price (e.g., 1.15 wstETH/ETH)
            supply_apy: Current supply APY
            borrow_apy: Current borrow APY
            lltv: Market LLTV

        Returns:
            Simulated leveraged position
        """
        # Get market info for asset symbols
        market = await self.data.get_market(self.protocol, self.market_id)
        if not market:
            raise ValueError(f"Market not found: {self.market_id}")

        # Calculate leveraged position
        total_collateral, total_borrow = RiskCalculator.calculate_leverage_loop(
            initial_capital=capital,
            target_leverage=self.target_leverage,
            collateral_price=entry_price,
            lltv=lltv,
            max_loops=self.max_loops,
        )

        position = SimulatedPosition(
            market_id=self.market_id,
            supply_amount=total_collateral,
            borrow_amount=total_borrow,
            supply_asset=market.collateral_asset_symbol,
            borrow_asset=market.loan_asset_symbol,
            initial_capital=capital,
            entry_price=entry_price,
            entry_timestamp=datetime.now(tz=timezone.utc),
            lltv=lltv,
            supply_apy=supply_apy,
            borrow_apy=borrow_apy,
        )

        self._position = position
        return position

    def update_position(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
        supply_apy: Decimal,
        borrow_apy: Decimal,
    ) -> tuple[SimulatedPosition, str]:
        """
        Update position based on current conditions.

        Handles:
        - APY updates (for yield calculation)
        - Emergency deleverage if HF too low
        - Re-leverage if HF too high (optional)

        Args:
            position: Current position
            current_price: Current collateral/loan price
            supply_apy: Current supply APY
            borrow_apy: Current borrow APY

        Returns:
            Tuple of (updated position, action description)
        """
        # Update APYs
        position.supply_apy = supply_apy
        position.borrow_apy = borrow_apy

        # Calculate current health factor
        hf = position.health_factor(current_price)

        action = ""

        # Emergency deleverage if HF too low
        if hf < self.deleverage_at_hf and hf > Decimal("1.0"):
            position, action = self._deleverage(position, current_price)

        # Optional: re-leverage if HF too high
        elif hf > self.releverage_at_hf:
            position, action = self._releverage(position, current_price)

        self._position = position
        return position, action

    def _deleverage(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> tuple[SimulatedPosition, str]:
        """
        Reduce leverage to increase health factor.

        Process:
        1. Calculate how much to repay to reach target HF
        2. Withdraw collateral (reduces supply)
        3. Swap to loan asset
        4. Repay debt

        We target the constraint min_health_factor.
        """
        target_hf = self.config.constraints.target_health_factor
        current_hf = position.health_factor(current_price)

        if current_hf >= target_hf:
            return position, ""

        # Calculate required borrow reduction
        # New HF = (new_collateral * price * LLTV) / new_borrow
        # We want HF = target_hf
        #
        # If we repay X of borrow:
        # - Collateral reduces by X/price (swap to repay)
        # - Borrow reduces by X
        #
        # new_collateral = supply - X/price
        # new_borrow = borrow - X
        # target_hf = (supply - X/price) * price * LLTV / (borrow - X)
        # target_hf = (supply*price - X) * LLTV / (borrow - X)
        # target_hf * (borrow - X) = (supply*price - X) * LLTV
        # target_hf * borrow - target_hf * X = supply*price*LLTV - X*LLTV
        # target_hf * borrow - supply*price*LLTV = target_hf*X - X*LLTV
        # X = (target_hf * borrow - supply*price*LLTV) / (target_hf - LLTV)

        collateral_value = position.supply_amount * current_price
        numerator = target_hf * position.borrow_amount - collateral_value * position.lltv
        denominator = target_hf - position.lltv

        if denominator == 0:
            return position, ""

        repay_amount = numerator / denominator

        if repay_amount <= 0:
            return position, ""

        # Cap at current borrow (can't repay more than owed)
        repay_amount = min(repay_amount, position.borrow_amount * Decimal("0.5"))

        # Update position
        collateral_reduction = repay_amount / current_price
        new_supply = position.supply_amount - collateral_reduction
        new_borrow = position.borrow_amount - repay_amount

        position.supply_amount = new_supply
        position.borrow_amount = new_borrow

        new_hf = position.health_factor(current_price)
        action = f"Deleverage: repaid {float(repay_amount):.4f}, HF {float(current_hf):.2f}→{float(new_hf):.2f}"

        return position, action

    def _releverage(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> tuple[SimulatedPosition, str]:
        """
        Increase leverage when health factor is too high.

        This is optional - only if we want to maintain target leverage.
        For simplicity, we'll keep positions as-is when HF is high.
        """
        # For now, don't auto-releverage
        # Users can choose to maintain constant leverage or let it drift
        return position, ""

    def should_liquidate(
        self,
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> bool:
        """Check if position would be liquidated."""
        return RiskCalculator.is_liquidated(position, current_price)

    def simulate_point(
        self,
        position: SimulatedPosition,
        timestamp: datetime,
        current_price: Decimal,
        supply_apy: Decimal,
        borrow_apy: Decimal,
        start_time: datetime,
    ) -> SimulationPoint:
        """
        Create a simulation point for the current state.

        Args:
            position: Current position
            timestamp: Current timestamp
            current_price: Current price
            supply_apy: Current supply APY
            borrow_apy: Current borrow APY
            start_time: Simulation start time

        Returns:
            SimulationPoint
        """
        elapsed = (timestamp - start_time).total_seconds() / (24 * 3600)
        elapsed_days = Decimal(str(elapsed))

        # Update position with current APYs
        position, action = self.update_position(
            position, current_price, supply_apy, borrow_apy
        )

        # Check liquidation
        liquidated = self.should_liquidate(position, current_price)
        if liquidated:
            action = "LIQUIDATED"

        hf = position.health_factor(current_price)
        pnl = position.pnl(current_price, elapsed_days)
        pnl_pct = position.pnl_percent(current_price, elapsed_days)

        return SimulationPoint(
            timestamp=timestamp,
            supply_amount=position.supply_amount,
            borrow_amount=position.borrow_amount,
            leverage=position.leverage,
            health_factor=hf,
            collateral_price=current_price,
            supply_apy=supply_apy,
            borrow_apy=borrow_apy,
            pnl=pnl,
            pnl_percent=pnl_pct,
            net_apy=position.net_apy,
            liquidated=liquidated,
            rebalanced="Deleverage" in action,
            action=action,
        )

    def calculate_theoretical_apy(
        self,
        supply_apy: Decimal,
        borrow_apy: Decimal,
        leverage: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate theoretical net APY for given rates and leverage.

        Net APY = supply_apy * leverage - borrow_apy * (leverage - 1)

        Args:
            supply_apy: Supply APY (e.g., 0.04 for 4%)
            borrow_apy: Borrow APY
            leverage: Leverage ratio (default: target_leverage)

        Returns:
            Net APY
        """
        if leverage is None:
            leverage = self.target_leverage

        if leverage <= 1:
            return supply_apy

        return (supply_apy * leverage) - (borrow_apy * (leverage - 1))
