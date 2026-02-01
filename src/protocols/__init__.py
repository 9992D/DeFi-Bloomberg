"""Protocol-specific implementations.

This module contains protocol-specific configurations, IRM implementations,
and GraphQL queries for supported DeFi protocols.

Currently supported:
- Morpho Blue (src.protocols.morpho)

Future protocols:
- Aave (planned)
- Euler (planned)
"""

# Note: We don't import morpho here to avoid circular imports
# Import specific modules as needed:
#   from src.protocols.morpho.config import IRM_PARAMS
#   from src.protocols.morpho.irm import AdaptiveCurveIRM
#   from src.protocols.morpho.queries import MorphoQueries
