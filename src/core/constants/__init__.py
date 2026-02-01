"""Core constants module.

Re-exports all constants for backward compatibility and convenience.
"""

from src.core.constants.generic import (
    SECONDS_PER_YEAR,
    HOURS_PER_YEAR,
    WAD,
    RAY,
    DEFAULT_VOLATILITY_WINDOW,
    DEFAULT_SHARPE_WINDOW,
    DEFAULT_ELASTICITY_RANGE,
)

from src.core.constants.chains import (
    ETHEREUM_MAINNET_CHAIN_ID,
    ETHEREUM_GOERLI_CHAIN_ID,
    ETHEREUM_SEPOLIA_CHAIN_ID,
    ARBITRUM_ONE_CHAIN_ID,
    OPTIMISM_CHAIN_ID,
    BASE_CHAIN_ID,
    POLYGON_CHAIN_ID,
)

# Re-export Morpho-specific constants for backward compatibility
# These are now in src.protocols.morpho.config
from src.protocols.morpho.config import (
    IRM_PARAMS,
    MORPHO_API_RATE_LIMIT,
    MORPHO_API_RATE_WINDOW,
    MORPHO_BLUE_ADDRESS,
    ADAPTIVE_CURVE_IRM_ADDRESS,
)

__all__ = [
    # Generic
    "SECONDS_PER_YEAR",
    "HOURS_PER_YEAR",
    "WAD",
    "RAY",
    "DEFAULT_VOLATILITY_WINDOW",
    "DEFAULT_SHARPE_WINDOW",
    "DEFAULT_ELASTICITY_RANGE",
    # Chains
    "ETHEREUM_MAINNET_CHAIN_ID",
    "ETHEREUM_GOERLI_CHAIN_ID",
    "ETHEREUM_SEPOLIA_CHAIN_ID",
    "ARBITRUM_ONE_CHAIN_ID",
    "OPTIMISM_CHAIN_ID",
    "BASE_CHAIN_ID",
    "POLYGON_CHAIN_ID",
    # Morpho-specific (backward compatibility)
    "IRM_PARAMS",
    "MORPHO_API_RATE_LIMIT",
    "MORPHO_API_RATE_WINDOW",
    "MORPHO_BLUE_ADDRESS",
    "ADAPTIVE_CURVE_IRM_ADDRESS",
]
