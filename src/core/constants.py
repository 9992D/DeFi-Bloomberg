"""Constants for Morpho Blue protocol calculations."""

from decimal import Decimal

# Time constants
SECONDS_PER_YEAR = 365.25 * 24 * 3600  # ~31,557,600
HOURS_PER_YEAR = 365.25 * 24  # 8766

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

# WAD constant (1e18) used in Morpho contracts
WAD = 10**18

# GraphQL API rate limits
MORPHO_API_RATE_LIMIT = 5000  # requests per 5 minutes
MORPHO_API_RATE_WINDOW = 300  # seconds

# Chain IDs
ETHEREUM_MAINNET_CHAIN_ID = 1

# Morpho Blue contract addresses (Ethereum Mainnet)
MORPHO_BLUE_ADDRESS = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM_ADDRESS = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"

# Default analytics parameters
DEFAULT_VOLATILITY_WINDOW = 168  # 7 days in hours
DEFAULT_SHARPE_WINDOW = 720  # 30 days in hours
DEFAULT_ELASTICITY_RANGE = (0.85, 0.95)  # Utilization range for elasticity calc
