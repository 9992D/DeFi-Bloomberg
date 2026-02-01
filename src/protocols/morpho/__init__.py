"""Morpho protocol-specific implementations.

Configuration: src.protocols.morpho.config
IRM Model: src.protocols.morpho.irm
GraphQL Queries: src.protocols.morpho.queries
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
]
