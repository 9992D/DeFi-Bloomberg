"""Data layer for DeFi Protocol Tracker."""

from .pipeline import DataPipeline
from .cache.disk_cache import DiskCache, CacheKeys

# New multi-protocol clients
from .clients.base import ProtocolClient, ProtocolType
from .clients.registry import ProtocolClientRegistry, register_default_clients
from .clients.morpho import MorphoClient, MorphoParser

# Backward compatibility - deprecated
from .sources.morpho_api import MorphoAPIClient

__all__ = [
    # Core
    "DataPipeline",
    "DiskCache",
    "CacheKeys",
    # Multi-protocol
    "ProtocolClient",
    "ProtocolType",
    "ProtocolClientRegistry",
    "register_default_clients",
    "MorphoClient",
    "MorphoParser",
    # Deprecated
    "MorphoAPIClient",
]
