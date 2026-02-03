"""Aave v3 protocol configuration."""

from src.protocols.aave.config import (
    AAVE_API_RATE_LIMIT,
    AAVE_API_RATE_WINDOW,
    AAVE_V3_API_URL,
    ETHEREUM_MAINNET,
)
from src.protocols.aave.queries import AaveQueries

__all__ = [
    "AAVE_API_RATE_LIMIT",
    "AAVE_API_RATE_WINDOW",
    "AAVE_V3_API_URL",
    "ETHEREUM_MAINNET",
    "AaveQueries",
]
