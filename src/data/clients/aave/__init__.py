"""Aave v3 GraphQL client."""

from src.data.clients.aave.client import AaveClient
from src.data.clients.aave.parser import AaveParser

__all__ = [
    "AaveClient",
    "AaveParser",
]
