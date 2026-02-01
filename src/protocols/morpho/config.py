"""Morpho Blue protocol-specific configuration and constants."""

from decimal import Decimal

from src.core.constants.generic import SECONDS_PER_YEAR

# Morpho Blue AdaptiveCurveIRM parameters
# Reference: https://docs.morpho.org/morpho/concepts/irm
IRM_PARAMS = {
    # Target utilization (90%)
    "TARGET_UTILIZATION": Decimal("0.9"),
    # Speed of adaptation (per second)
    "ADJUSTMENT_SPEED": Decimal("50") / Decimal(str(SECONDS_PER_YEAR)),
    # Curve steepness parameters
    "CURVE_STEEPNESS": Decimal("4"),
    # Min/Max rate bounds
    "MIN_RATE_AT_TARGET": Decimal("0.001"),  # 0.1% APR
    "MAX_RATE_AT_TARGET": Decimal("2.0"),  # 200% APR
    # Initial rate at target
    "INITIAL_RATE_AT_TARGET": Decimal("0.04"),  # 4% APR
}

# GraphQL API rate limits
MORPHO_API_RATE_LIMIT = 5000  # requests per 5 minutes
MORPHO_API_RATE_WINDOW = 300  # seconds

# Morpho Blue contract addresses (Ethereum Mainnet)
MORPHO_BLUE_ADDRESS = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM_ADDRESS = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"

# Default API URL
MORPHO_API_URL = "https://blue-api.morpho.org/graphql"
