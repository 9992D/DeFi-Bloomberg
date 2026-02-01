"""Protocol clients module.

Provides unified interfaces for interacting with different DeFi protocols.
"""

from src.data.clients.base import ProtocolClient, ProtocolType
from src.data.clients.registry import (
    ProtocolClientRegistry,
    register_default_clients,
)

__all__ = [
    "ProtocolClient",
    "ProtocolType",
    "ProtocolClientRegistry",
    "register_default_clients",
]
