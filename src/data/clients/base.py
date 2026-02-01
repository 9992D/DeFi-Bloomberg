"""Base protocol client interface.

Defines the abstract interface that all protocol clients must implement,
enabling a unified data pipeline that can work with multiple DeFi protocols.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any
from decimal import Decimal

from src.core.models import (
    Market,
    Position,
    TimeseriesPoint,
    Vault,
    VaultTimeseriesPoint,
)


class ProtocolType(Enum):
    """Supported DeFi protocol types."""

    MORPHO = "morpho"
    AAVE = "aave"      # Future
    EULER = "euler"    # Future


class ProtocolClient(ABC):
    """Abstract base class for protocol-specific API clients.

    All protocol clients must implement this interface to be compatible
    with the unified DataPipeline.
    """

    @property
    @abstractmethod
    def protocol_type(self) -> ProtocolType:
        """Return the protocol type for this client."""
        ...

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Return a human-readable protocol name."""
        ...

    @property
    @abstractmethod
    def supports_vaults(self) -> bool:
        """Return True if this protocol supports vault-like products."""
        ...

    # ========== MARKET METHODS ==========

    @abstractmethod
    async def get_markets(
        self,
        first: int = 50,
        skip: int = 0,
    ) -> List[Market]:
        """Fetch markets/pools from the protocol.

        Args:
            first: Maximum number of markets to fetch
            skip: Number of markets to skip (for pagination)

        Returns:
            List of Market objects
        """
        ...

    @abstractmethod
    async def get_market(self, market_id: str) -> Optional[Market]:
        """Fetch a single market by ID with detailed data.

        Args:
            market_id: The unique identifier for the market

        Returns:
            Market object or None if not found
        """
        ...

    @abstractmethod
    async def get_market_timeseries(
        self,
        market_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[TimeseriesPoint]:
        """Fetch historical timeseries data for a market.

        Args:
            market_id: The unique identifier for the market
            start_timestamp: Start of time range (unix timestamp)
            end_timestamp: End of time range (unix timestamp)
            interval: Data interval (HOUR, DAY, WEEK, MONTH)

        Returns:
            List of TimeseriesPoint objects sorted by timestamp
        """
        ...

    # ========== POSITION METHODS ==========

    @abstractmethod
    async def get_positions(
        self,
        user_address: str,
        first: int = 100,
    ) -> List[Position]:
        """Fetch positions for a user address.

        Args:
            user_address: Ethereum address of the user
            first: Maximum number of positions to fetch

        Returns:
            List of Position objects
        """
        ...

    # ========== RATE METHODS ==========

    async def get_rates(self, first: int = 50) -> Dict[str, Dict[str, Decimal]]:
        """Fetch lightweight rate data for all markets.

        This is an optional method for protocols that support
        fetching rates separately from full market data.

        Args:
            first: Maximum number of markets to fetch rates for

        Returns:
            Dict mapping market_id to rate data dict
        """
        return {}

    # ========== VAULT METHODS (Optional) ==========

    async def get_vaults(
        self,
        first: int = 50,
        skip: int = 0,
    ) -> List[Vault]:
        """Fetch vaults from the protocol.

        Override this method if the protocol supports vaults.

        Args:
            first: Maximum number of vaults to fetch
            skip: Number of vaults to skip (for pagination)

        Returns:
            List of Vault objects
        """
        return []

    async def get_vault(self, vault_id: str) -> Optional[Vault]:
        """Fetch a single vault by ID with detailed data.

        Override this method if the protocol supports vaults.

        Args:
            vault_id: The unique identifier for the vault

        Returns:
            Vault object or None if not found
        """
        return None

    async def get_vault_timeseries(
        self,
        vault_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[VaultTimeseriesPoint]:
        """Fetch historical timeseries data for a vault.

        Override this method if the protocol supports vaults.

        Args:
            vault_id: The unique identifier for the vault
            start_timestamp: Start of time range (unix timestamp)
            end_timestamp: End of time range (unix timestamp)
            interval: Data interval (HOUR, DAY, WEEK, MONTH)

        Returns:
            List of VaultTimeseriesPoint objects sorted by timestamp
        """
        return []

    # ========== LIFECYCLE ==========

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections and clean up resources."""
        ...
