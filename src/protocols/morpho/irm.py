"""AdaptiveCurveIRM calculations for Morpho Blue."""

from decimal import Decimal
from typing import Tuple, List

from src.core.constants import IRM_PARAMS, SECONDS_PER_YEAR


class AdaptiveCurveIRM:
    """
    AdaptiveCurveIRM implementation for Morpho Blue.

    The AdaptiveCurveIRM adjusts the rate at target utilization based on
    whether actual utilization is above or below the target (90%).

    Reference: https://docs.morpho.org/morpho/concepts/irm
    """

    def __init__(
        self,
        target_utilization: Decimal = IRM_PARAMS["TARGET_UTILIZATION"],
        curve_steepness: Decimal = IRM_PARAMS["CURVE_STEEPNESS"],
        adjustment_speed: Decimal = IRM_PARAMS["ADJUSTMENT_SPEED"],
    ):
        self.target_utilization = target_utilization
        self.curve_steepness = curve_steepness
        self.adjustment_speed = adjustment_speed

    def calculate_borrow_rate(
        self,
        utilization: Decimal,
        rate_at_target: Decimal,
    ) -> Decimal:
        """
        Calculate the borrow rate for a given utilization.

        The curve is exponential:
        - Below target: rate = rateAtTarget * (utilization / targetUtil)^steepness
        - Above target: rate = rateAtTarget * (steepness)^((util - target) / (1 - target))

        Args:
            utilization: Current utilization (0-1)
            rate_at_target: Current rate at target utilization

        Returns:
            Borrow rate (APR)
        """
        if utilization <= Decimal("0"):
            return Decimal("0")

        if utilization >= Decimal("1"):
            # At 100% utilization, return max rate
            return rate_at_target * (self.curve_steepness ** 4)

        if utilization <= self.target_utilization:
            # Below target: linear-ish increase
            ratio = utilization / self.target_utilization
            return rate_at_target * ratio
        else:
            # Above target: exponential increase
            excess = (utilization - self.target_utilization) / (
                Decimal("1") - self.target_utilization
            )
            multiplier = self.curve_steepness ** excess
            return rate_at_target * multiplier

    def calculate_supply_rate(
        self,
        utilization: Decimal,
        borrow_rate: Decimal,
        fee: Decimal = Decimal("0"),
    ) -> Decimal:
        """
        Calculate supply rate from borrow rate and utilization.

        supply_rate = borrow_rate * utilization * (1 - fee)

        Args:
            utilization: Current utilization (0-1)
            borrow_rate: Current borrow rate
            fee: Protocol fee rate

        Returns:
            Supply rate (APR)
        """
        return borrow_rate * utilization * (Decimal("1") - fee)

    def predict_rate_at_target_evolution(
        self,
        current_rate_at_target: Decimal,
        utilization: Decimal,
        time_delta_seconds: int,
    ) -> Decimal:
        """
        Predict how rateAtTarget will evolve over time.

        The rate adjusts based on whether utilization is above or below target.

        Args:
            current_rate_at_target: Current rate at target
            utilization: Current utilization
            time_delta_seconds: Time period in seconds

        Returns:
            Predicted rate at target after time_delta
        """
        if utilization > self.target_utilization:
            # Above target: rate increases
            adjustment = (
                self.adjustment_speed
                * Decimal(str(time_delta_seconds))
                * (utilization - self.target_utilization)
            )
            new_rate = current_rate_at_target * (Decimal("1") + adjustment)
        else:
            # Below target: rate decreases
            adjustment = (
                self.adjustment_speed
                * Decimal(str(time_delta_seconds))
                * (self.target_utilization - utilization)
            )
            new_rate = current_rate_at_target * (Decimal("1") - adjustment)

        # Clamp to min/max bounds
        return max(
            IRM_PARAMS["MIN_RATE_AT_TARGET"],
            min(IRM_PARAMS["MAX_RATE_AT_TARGET"], new_rate),
        )

    def generate_rate_curve(
        self,
        rate_at_target: Decimal,
        fee: Decimal = Decimal("0"),
        num_points: int = 100,
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        Generate the full rate curve for visualization.

        Args:
            rate_at_target: Current rate at target
            fee: Protocol fee rate
            num_points: Number of points to generate

        Returns:
            Tuple of (utilizations, borrow_rates, supply_rates) as float lists
        """
        utilizations = []
        borrow_rates = []
        supply_rates = []

        for i in range(num_points + 1):
            util = Decimal(str(i)) / Decimal(str(num_points))
            borrow = self.calculate_borrow_rate(util, rate_at_target)
            supply = self.calculate_supply_rate(util, borrow, fee)

            utilizations.append(float(util))
            borrow_rates.append(float(borrow))
            supply_rates.append(float(supply))

        return utilizations, borrow_rates, supply_rates

    @staticmethod
    def apr_to_apy(apr: Decimal, compounding_periods: int = 365) -> Decimal:
        """
        Convert APR to APY with given compounding periods.

        APY = (1 + APR/n)^n - 1

        Args:
            apr: Annual Percentage Rate
            compounding_periods: Number of compounding periods per year

        Returns:
            Annual Percentage Yield
        """
        if apr <= Decimal("0"):
            return Decimal("0")

        rate_per_period = apr / Decimal(str(compounding_periods))
        return (Decimal("1") + rate_per_period) ** compounding_periods - Decimal("1")

    @staticmethod
    def apy_to_apr(apy: Decimal, compounding_periods: int = 365) -> Decimal:
        """
        Convert APY to APR with given compounding periods.

        APR = n * ((1 + APY)^(1/n) - 1)

        Args:
            apy: Annual Percentage Yield
            compounding_periods: Number of compounding periods per year

        Returns:
            Annual Percentage Rate
        """
        if apy <= Decimal("0"):
            return Decimal("0")

        n = Decimal(str(compounding_periods))
        # Using float for exponentiation, then back to Decimal
        rate_per_period = (float(Decimal("1") + apy) ** (1 / float(n))) - 1
        return Decimal(str(rate_per_period)) * n
