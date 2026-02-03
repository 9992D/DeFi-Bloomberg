"""Morpho protocol-specific implementations.

Configuration: src.protocols.morpho.config
IRM Model: src.protocols.morpho.irm
GraphQL Queries: src.protocols.morpho.queries
Assets: src.protocols.morpho.assets
"""

# Export config constants directly (no circular import issues)
from .config import (
    IRM_PARAMS,
    MORPHO_API_RATE_LIMIT,
    MORPHO_API_RATE_WINDOW,
    MORPHO_BLUE_ADDRESS,
    ADAPTIVE_CURVE_IRM_ADDRESS,
    MORPHO_API_URL,
)

# Export asset addresses
from .assets import (
    COLLATERAL_ASSETS,
    BORROW_ASSETS,
    DEFAULT_COLLATERAL_ADDRESS,
    DEFAULT_BORROW_ADDRESS,
    get_asset_name,
)

# Lazy imports for modules that have potential circular dependencies
# Use: from src.protocols.morpho.irm import AdaptiveCurveIRM
# Use: from src.protocols.morpho.queries import MorphoQueries

__all__ = [
    "IRM_PARAMS",
    "MORPHO_API_RATE_LIMIT",
    "MORPHO_API_RATE_WINDOW",
    "MORPHO_BLUE_ADDRESS",
    "ADAPTIVE_CURVE_IRM_ADDRESS",
    "MORPHO_API_URL",
    "COLLATERAL_ASSETS",
    "BORROW_ASSETS",
    "DEFAULT_COLLATERAL_ADDRESS",
    "DEFAULT_BORROW_ADDRESS",
    "get_asset_name",
]
