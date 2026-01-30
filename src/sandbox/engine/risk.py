"""Risk calculation utilities for strategy simulation."""

from decimal import Decimal
from typing import Optional

from src.sandbox.models import SimulatedPosition


class RiskCalculator:
    """
    Calculator for position risk metrics.

    Handles health factor, liquidation price, and max borrow calculations.
    """

    @staticmethod
    def health_factor(
        collateral_amount: Decimal,
        collateral_price: Decimal,
        borrow_amount: Decimal,
        lltv: Decimal,
    ) -> Decimal:
        """
        Calculate health factor.

        HF = (Collateral Value * LLTV) / Borrow Value

        For wstETH/ETH:
        - Collateral Value = wstETH amount * wstETH/ETH price
        - Borrow Value = ETH amount

        Args:
            collateral_amount: Amount of collateral (e.g., wstETH)
            collateral_price: Price of collateral in loan asset (e.g., wstETH/ETH)
            borrow_amount: Amount borrowed (e.g., ETH)
            lltv: Liquidation LTV (e.g., 0.945)

        Returns:
            Health factor (< 1.0 means liquidation)
        """
        if borrow_amount == 0:
            return Decimal("999")

        collateral_value = collateral_amount * collateral_price
        max_borrow = collateral_value * lltv

        return max_borrow / borrow_amount

    @staticmethod
    def liquidation_price(
        collateral_amount: Decimal,
        borrow_amount: Decimal,
        lltv: Decimal,
    ) -> Decimal:
        """
        Calculate the price at which position gets liquidated.

        At liquidation: collateral_value * LLTV = borrow_amount
        collateral_amount * liq_price * LLTV = borrow_amount
        liq_price = borrow_amount / (collateral_amount * LLTV)

        Args:
            collateral_amount: Amount of collateral
            borrow_amount: Amount borrowed
            lltv: Liquidation LTV

        Returns:
            Liquidation price (collateral/loan ratio)
        """
        if collateral_amount == 0 or lltv == 0:
            return Decimal("0")

        return borrow_amount / (collateral_amount * lltv)

    @staticmethod
    def max_borrow(
        collateral_amount: Decimal,
        collateral_price: Decimal,
        lltv: Decimal,
        target_hf: Decimal = Decimal("1.5"),
    ) -> Decimal:
        """
        Calculate maximum borrow to achieve target health factor.

        HF = (collateral * price * LLTV) / borrow
        borrow = (collateral * price * LLTV) / target_HF

        Args:
            collateral_amount: Amount of collateral
            collateral_price: Current price
            lltv: Liquidation LTV
            target_hf: Target health factor (default 1.5)

        Returns:
            Maximum borrow amount
        """
        if target_hf == 0:
            return Decimal("0")

        collateral_value = collateral_amount * collateral_price
        return (collateral_value * lltv) / target_hf

    @staticmethod
    def required_collateral(
        borrow_amount: Decimal,
        collateral_price: Decimal,
        lltv: Decimal,
        target_hf: Decimal = Decimal("1.5"),
    ) -> Decimal:
        """
        Calculate required collateral for a given borrow at target HF.

        collateral = (borrow * target_HF) / (price * LLTV)

        Args:
            borrow_amount: Desired borrow amount
            collateral_price: Current price
            lltv: Liquidation LTV
            target_hf: Target health factor

        Returns:
            Required collateral amount
        """
        if collateral_price == 0 or lltv == 0:
            return Decimal("0")

        return (borrow_amount * target_hf) / (collateral_price * lltv)

    @staticmethod
    def leverage_from_hf(
        health_factor: Decimal,
        lltv: Decimal,
    ) -> Decimal:
        """
        Calculate effective leverage from health factor.

        For a leverage loop:
        - Leverage = 1 / (1 - borrow_ratio)
        - borrow_ratio = LLTV / HF
        - Leverage = 1 / (1 - LLTV/HF) = HF / (HF - LLTV)

        Args:
            health_factor: Current health factor
            lltv: Liquidation LTV

        Returns:
            Effective leverage
        """
        if health_factor <= lltv:
            return Decimal("999")  # Infinite/liquidated

        return health_factor / (health_factor - lltv)

    @staticmethod
    def hf_from_leverage(
        leverage: Decimal,
        lltv: Decimal,
    ) -> Decimal:
        """
        Calculate health factor from target leverage.

        HF = leverage * LLTV / (leverage - 1)

        Args:
            leverage: Target leverage
            lltv: Liquidation LTV

        Returns:
            Required health factor
        """
        if leverage <= 1:
            return Decimal("999")

        return (leverage * lltv) / (leverage - 1)

    @staticmethod
    def is_liquidated(
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> bool:
        """
        Check if position is liquidated at current price.

        Args:
            position: Position to check
            current_price: Current collateral/loan price

        Returns:
            True if liquidated (HF < 1.0)
        """
        hf = position.health_factor(current_price)
        return hf < Decimal("1.0")

    @staticmethod
    def distance_to_liquidation(
        position: SimulatedPosition,
        current_price: Decimal,
    ) -> Decimal:
        """
        Calculate price drop percentage until liquidation.

        Args:
            position: Current position
            current_price: Current price

        Returns:
            Percentage price drop to liquidation (0-100)
        """
        liq_price = position.liquidation_price()
        if current_price == 0:
            return Decimal("0")

        return ((current_price - liq_price) / current_price) * 100

    @staticmethod
    def calculate_leverage_loop(
        initial_capital: Decimal,
        target_leverage: Decimal,
        collateral_price: Decimal,
        lltv: Decimal,
        max_loops: int = 10,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate final position from leverage looping.

        Leverage loop process:
        1. Deposit initial capital as collateral
        2. Borrow up to LLTV
        3. Swap borrowed to collateral
        4. Re-deposit
        5. Repeat

        Args:
            initial_capital: Starting collateral amount
            target_leverage: Desired leverage
            collateral_price: Current collateral/loan price
            lltv: Liquidation LTV
            max_loops: Maximum iterations

        Returns:
            Tuple of (total_collateral, total_borrow)
        """
        # Calculate target position directly
        # For leverage L, we need:
        # total_collateral = initial_capital * L
        # total_borrow = initial_capital * (L - 1) / price
        #
        # This is because:
        # - We have initial_capital of collateral
        # - We borrow (L-1) * initial_capital worth (in loan terms)
        # - We convert to collateral and re-deposit

        total_collateral = initial_capital * target_leverage
        total_borrow = initial_capital * (target_leverage - 1) * collateral_price

        # Verify health factor is achievable
        hf = RiskCalculator.health_factor(
            total_collateral, collateral_price, total_borrow, lltv
        )

        if hf < Decimal("1.0"):
            # Target leverage too high, find max achievable
            # At HF = 1.0: collateral * price * LLTV = borrow
            # For leverage loop: borrow = (L-1) * capital * price
            # capital * L * price * LLTV = (L-1) * capital * price
            # L * LLTV = L - 1
            # L = 1 / (1 - LLTV)
            max_leverage = Decimal("1") / (Decimal("1") - lltv)
            # Use 90% of max for safety
            safe_leverage = Decimal("1") + (max_leverage - 1) * Decimal("0.9")

            total_collateral = initial_capital * safe_leverage
            total_borrow = initial_capital * (safe_leverage - 1) * collateral_price

        return total_collateral, total_borrow
