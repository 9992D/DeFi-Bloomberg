"""Data pipeline orchestration for DeFi Protocol Tracker.

Provides a unified interface for fetching data from multiple DeFi protocols
through protocol-specific clients.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config.settings import Settings, get_settings
from src.core.models import Market, Position, TimeseriesPoint, Vault, VaultTimeseriesPoint
from src.data.clients.base import ProtocolClient, ProtocolType
from src.data.clients.registry import ProtocolClientRegistry, register_default_clients
from src.data.cache.disk_cache import DiskCache

logger = logging.getLogger(__name__)


class DataPipeline:
    """Orchestrates data fetching from various DeFi protocol sources.

    Supports multiple protocols through the ProtocolClient interface,
    with per-protocol caching and a default protocol for backward compatibility.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        clients: Optional[Dict[ProtocolType, ProtocolClient]] = None,
        cache: Optional[DiskCache] = None,
        default_protocol: ProtocolType = ProtocolType.MORPHO,
    ):
        """Initialize the data pipeline.

        Args:
            settings: Application settings
            clients: Optional dict of protocol clients (if None, uses registry)
            cache: Optional disk cache instance
            default_protocol: Default protocol to use when none specified
        """
        self.settings = settings or get_settings()
        self._default_protocol = default_protocol
        self.cache = cache or DiskCache(self.settings)

        # Initialize clients from registry if not provided
        if clients is None:
            register_default_clients()
            self._clients = ProtocolClientRegistry.get_all_clients(self.settings)
        else:
            self._clients = clients

        # In-memory caches keyed by protocol
        self._markets_cache: Dict[ProtocolType, List[Market]] = {}
        self._timeseries_cache: Dict[str, List[TimeseriesPoint]] = {}
        self._vaults_cache: Dict[ProtocolType, List[Vault]] = {}
        self._vault_timeseries_cache: Dict[str, List[VaultTimeseriesPoint]] = {}

    def get_client(self, protocol: Optional[ProtocolType] = None) -> ProtocolClient:
        """Get the client for a specific protocol.

        Args:
            protocol: Protocol type (uses default if None)

        Returns:
            ProtocolClient instance for the specified protocol

        Raises:
            ValueError: If no client is available for the protocol
        """
        protocol = protocol or self._default_protocol
        if protocol not in self._clients:
            raise ValueError(
                f"No client available for protocol: {protocol.value}. "
                f"Available: {[p.value for p in self._clients.keys()]}"
            )
        return self._clients[protocol]

    @property
    def available_protocols(self) -> List[ProtocolType]:
        """Get list of available protocols."""
        return list(self._clients.keys())

    # ========== BACKWARD COMPATIBLE PROPERTY ==========

    @property
    def api(self) -> ProtocolClient:
        """Backward compatible access to the default API client.

        Deprecated: Use get_client() instead.
        """
        return self.get_client(self._default_protocol)

    # ========== MARKET METHODS ==========

    async def get_markets(
        self,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
        first: int = 50,
    ) -> List[Market]:
        """Get all markets for a protocol.

        Args:
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data
            first: Number of markets to fetch

        Returns:
            List of Market objects
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        if not force_refresh and protocol in self._markets_cache:
            logger.debug(f"Memory cache hit for {protocol.value} markets")
            return self._markets_cache[protocol]

        logger.info(f"Fetching markets from {client.protocol_name}")
        markets = await client.get_markets(first=first)
        self._markets_cache[protocol] = markets
        return markets

    async def get_market(
        self,
        market_id: str,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
    ) -> Optional[Market]:
        """Get a single market with details.

        Args:
            market_id: Market unique key
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Market object or None
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        # Check in-memory cache first
        if not force_refresh and protocol in self._markets_cache:
            for m in self._markets_cache[protocol]:
                if m.id == market_id:
                    return m

        logger.info(f"Fetching market {market_id} from {client.protocol_name}")
        return await client.get_market(market_id)

    async def get_market_timeseries(
        self,
        market_id: str,
        protocol: Optional[ProtocolType] = None,
        hours: Optional[int] = None,
        days: Optional[int] = None,
        interval: str = "DAY",
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        force_refresh: bool = False,
    ) -> List[TimeseriesPoint]:
        """Get timeseries data for a market.

        Args:
            market_id: Market unique key
            protocol: Protocol type (uses default if None)
            hours: Optional - filter to last N hours
            days: Optional - filter to last N days (default: 90)
            interval: Data interval - HOUR, DAY, WEEK (default: DAY)
            start_timestamp: Optional explicit start timestamp
            end_timestamp: Optional explicit end timestamp
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of TimeseriesPoint objects
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        # Build cache key from all parameters
        cache_key = f"{protocol.value}:{market_id}:{hours}:{days}:{interval}"

        if not force_refresh and cache_key in self._timeseries_cache:
            logger.debug(f"Memory cache hit for timeseries {market_id}")
            return self._timeseries_cache[cache_key]

        logger.info(f"Fetching timeseries for {market_id} (interval={interval})")

        # Calculate timestamps
        now = datetime.now(tz=timezone.utc)
        if end_timestamp is None:
            end_timestamp = int(now.timestamp())

        if start_timestamp is None:
            if hours is not None:
                start_timestamp = end_timestamp - (hours * 3600)
            elif days is not None:
                start_timestamp = end_timestamp - (days * 24 * 3600)
            else:
                # Default to 90 days
                start_timestamp = end_timestamp - (90 * 24 * 3600)

        timeseries = await client.get_market_timeseries(
            market_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            interval=interval,
        )

        if timeseries:
            self._timeseries_cache[cache_key] = timeseries

        return timeseries

    # ========== POSITION METHODS ==========

    async def get_positions(
        self,
        user_addresses: Optional[List[str]] = None,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
    ) -> List[Position]:
        """Get positions for tracked wallets.

        Args:
            user_addresses: Wallet addresses (None = use settings)
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of Position objects
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)
        addresses = user_addresses or self.settings.wallet_addresses

        if not addresses:
            logger.warning("No wallet addresses configured")
            return []

        all_positions = []

        for address in addresses:
            logger.info(f"Fetching positions for {address} from {client.protocol_name}")
            positions = await client.get_positions(address)
            all_positions.extend(positions)

        return all_positions

    # ========== VAULT METHODS ==========

    async def get_vaults(
        self,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
        first: int = 50,
    ) -> List[Vault]:
        """Get all vaults for a protocol.

        Args:
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data
            first: Number of vaults to fetch

        Returns:
            List of Vault objects
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        if not client.supports_vaults:
            logger.warning(f"{client.protocol_name} does not support vaults")
            return []

        if not force_refresh and protocol in self._vaults_cache:
            logger.debug(f"Memory cache hit for {protocol.value} vaults")
            return self._vaults_cache[protocol]

        logger.info(f"Fetching vaults from {client.protocol_name}")
        vaults = await client.get_vaults(first=first)
        self._vaults_cache[protocol] = vaults
        return vaults

    async def get_vault(
        self,
        vault_address: str,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
    ) -> Optional[Vault]:
        """Get a single vault with details.

        Args:
            vault_address: Vault address
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Vault object or None
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        if not client.supports_vaults:
            return None

        # Check in-memory cache first
        if not force_refresh and protocol in self._vaults_cache:
            for v in self._vaults_cache[protocol]:
                if v.id.lower() == vault_address.lower():
                    return v

        logger.info(f"Fetching vault {vault_address} from {client.protocol_name}")
        return await client.get_vault(vault_address)

    async def get_vault_timeseries(
        self,
        vault_address: str,
        protocol: Optional[ProtocolType] = None,
        force_refresh: bool = False,
    ) -> List[VaultTimeseriesPoint]:
        """Get timeseries data for a vault.

        Args:
            vault_address: Vault address
            protocol: Protocol type (uses default if None)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of VaultTimeseriesPoint objects
        """
        protocol = protocol or self._default_protocol
        client = self.get_client(protocol)

        if not client.supports_vaults:
            return []

        cache_key = f"{protocol.value}:{vault_address.lower()}"

        if not force_refresh and cache_key in self._vault_timeseries_cache:
            logger.debug(f"Memory cache hit for vault timeseries {vault_address}")
            return self._vault_timeseries_cache[cache_key]

        logger.info(f"Fetching timeseries for vault {vault_address}")
        timeseries = await client.get_vault_timeseries(vault_address)

        if timeseries:
            self._vault_timeseries_cache[cache_key] = timeseries

        return timeseries

    # ========== UTILITY METHODS ==========

    async def refresh_all(
        self,
        protocol: Optional[ProtocolType] = None,
    ) -> Dict[str, int]:
        """Refresh all data for a protocol.

        Args:
            protocol: Protocol type (uses default if None, or all if still None)

        Returns:
            Dict with counts of refreshed items
        """
        results = {"markets": 0, "positions": 0, "vaults": 0}
        protocol = protocol or self._default_protocol

        # Refresh markets
        markets = await self.get_markets(protocol=protocol, force_refresh=True)
        results["markets"] = len(markets)

        # Refresh positions
        positions = await self.get_positions(protocol=protocol, force_refresh=True)
        results["positions"] = len(positions)

        # Refresh vaults if supported
        client = self.get_client(protocol)
        if client.supports_vaults:
            vaults = await self.get_vaults(protocol=protocol, force_refresh=True)
            results["vaults"] = len(vaults)

        logger.info(f"Refreshed {protocol.value} data: {results}")
        return results

    def clear_cache(self, protocol: Optional[ProtocolType] = None) -> int:
        """Clear cached data.

        Args:
            protocol: Protocol to clear cache for (None = all protocols)

        Returns:
            Number of items cleared
        """
        count = 0

        if protocol is None:
            # Clear all
            count = (
                len(self._markets_cache)
                + len(self._timeseries_cache)
                + len(self._vaults_cache)
                + len(self._vault_timeseries_cache)
            )
            self._markets_cache.clear()
            self._timeseries_cache.clear()
            self._vaults_cache.clear()
            self._vault_timeseries_cache.clear()
        else:
            # Clear for specific protocol
            if protocol in self._markets_cache:
                del self._markets_cache[protocol]
                count += 1
            if protocol in self._vaults_cache:
                del self._vaults_cache[protocol]
                count += 1
            # Clear timeseries caches for this protocol
            ts_keys = [k for k in self._timeseries_cache if k.startswith(f"{protocol.value}:")]
            for k in ts_keys:
                del self._timeseries_cache[k]
                count += 1
            vts_keys = [k for k in self._vault_timeseries_cache if k.startswith(f"{protocol.value}:")]
            for k in vts_keys:
                del self._vault_timeseries_cache[k]
                count += 1

        logger.info(f"Cleared {count} cached items")
        return count

    async def close(self) -> None:
        """Close all connections."""
        # Close directly injected clients
        for client in self._clients.values():
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing client {client.protocol_name}: {e}")

        # Also close any clients in the registry
        await ProtocolClientRegistry.close_all()
        self.cache.close()
