"""Generic constants for DeFi protocol calculations.

These constants are protocol-agnostic and can be used across different protocols.
"""

from decimal import Decimal

# Time constants
SECONDS_PER_YEAR = 365.25 * 24 * 3600  # ~31,557,600
HOURS_PER_YEAR = 365.25 * 24  # 8766

# Precision constants
WAD = 10**18  # Standard 18 decimal precision (used in Morpho, Aave, etc.)
RAY = 10**27  # 27 decimal precision (used in Aave)

# Default analytics parameters
DEFAULT_VOLATILITY_WINDOW = 168  # 7 days in hours
DEFAULT_SHARPE_WINDOW = 720  # 30 days in hours
DEFAULT_ELASTICITY_RANGE = (0.85, 0.95)  # Utilization range for elasticity calc
