"""Data pipeline orchestration for Morpho Tracker."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

from config.settings import Settings, get_settings
from src.core.models import Market, Position, TimeseriesPoint, Vault, VaultTimeseriesPoint
from src.data.sources.morpho_api import MorphoAPIClient
from src.data.cache.disk_cache import DiskCache, CacheKeys

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    Orchestrates data fetching from various sources.

    Note: Caching is disabled in POC mode to avoid serialization issues.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        api_client: Optional[MorphoAPIClient] = None,
        cache: Optional[DiskCache] = None,
    ):
        self.settings = settings or get_settings()
        self.api = api_client or MorphoAPIClient(self.settings)
        self.cache = cache or DiskCache(self.settings)

        # In-memory cache for current session
        self._markets_cache: Optional[List[Market]] = None
        self._timeseries_cache: Dict[str, List[TimeseriesPoint]] = {}
        self._vaults_cache: Optional[List[Vault]] = None
        self._vault_timeseries_cache: Dict[str, List[VaultTimeseriesPoint]] = {}

    async def get_markets(
        self,
        force_refresh: bool = False,
        first: int = 50,
    ) -> List[Market]:
        """
        Get all markets.

        Args:
            force_refresh: Skip cache and fetch fresh data
            first: Number of markets to fetch

        Returns:
            List of Market objects
        """
        if not force_refresh and self._markets_cache is not None:
            logger.debug(f"Memory cache hit for markets")
            return self._markets_cache

        logger.info("Fetching markets from API")
        markets = await self.api.get_markets(first=first)
        self._markets_cache = markets
        return markets

    async def get_market(
        self,
        market_id: str,
        force_refresh: bool = False,
    ) -> Optional[Market]:
        """
        Get a single market with details.

        Args:
            market_id: Market unique key
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Market object or None
        """
        # Check in-memory cache first
        if not force_refresh and self._markets_cache:
            for m in self._markets_cache:
                if m.id == market_id:
                    return m

        logger.info(f"Fetching market {market_id} from API")
        market = await self.api.get_market(market_id)
        return market

    async def get_market_timeseries(
        self,
        market_id: str,
        hours: Optional[int] = None,
        days: Optional[int] = None,
        interval: str = "DAY",
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        force_refresh: bool = False,
    ) -> List[TimeseriesPoint]:
        """
        Get timeseries data for a market.

        Args:
            market_id: Market unique key
            hours: Optional - filter to last N hours
            days: Optional - filter to last N days (default: 90)
            interval: Data interval - HOUR, DAY, WEEK (default: DAY)
            start_timestamp: Optional explicit start timestamp
            end_timestamp: Optional explicit end timestamp
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of TimeseriesPoint objects
        """
        # Build cache key from all parameters
        cache_key = f"{market_id}:{hours}:{days}:{interval}"

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

        timeseries = await self.api.get_market_timeseries(
            market_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            interval=interval,
        )

        if timeseries:
            self._timeseries_cache[cache_key] = timeseries

        return timeseries

    async def get_positions(
        self,
        user_addresses: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> List[Position]:
        """
        Get positions for tracked wallets.

        Args:
            user_addresses: Wallet addresses (None = use settings)
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of Position objects
        """
        addresses = user_addresses or self.settings.wallet_addresses

        if not addresses:
            logger.warning("No wallet addresses configured")
            return []

        all_positions = []

        for address in addresses:
            logger.info(f"Fetching positions for {address}")
            positions = await self.api.get_positions(address)
            all_positions.extend(positions)

        return all_positions

    async def refresh_all(self) -> Dict[str, int]:
        """
        Refresh all data.

        Returns:
            Dict with counts of refreshed items
        """
        results = {"markets": 0, "positions": 0}

        # Refresh markets
        markets = await self.get_markets(force_refresh=True)
        results["markets"] = len(markets)

        # Refresh positions
        positions = await self.get_positions(force_refresh=True)
        results["positions"] = len(positions)

        logger.info(f"Refreshed data: {results}")
        return results

    # ========== VAULT METHODS ==========

    async def get_vaults(
        self,
        force_refresh: bool = False,
        first: int = 50,
    ) -> List[Vault]:
        """
        Get all vaults.

        Args:
            force_refresh: Skip cache and fetch fresh data
            first: Number of vaults to fetch

        Returns:
            List of Vault objects
        """
        if not force_refresh and self._vaults_cache is not None:
            logger.debug("Memory cache hit for vaults")
            return self._vaults_cache

        logger.info("Fetching vaults from API")
        vaults = await self.api.get_vaults(first=first)
        self._vaults_cache = vaults
        return vaults

    async def get_vault(
        self,
        vault_address: str,
        force_refresh: bool = False,
    ) -> Optional[Vault]:
        """
        Get a single vault with details.

        Args:
            vault_address: Vault address
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Vault object or None
        """
        # Check in-memory cache first
        if not force_refresh and self._vaults_cache:
            for v in self._vaults_cache:
                if v.id.lower() == vault_address.lower():
                    return v

        logger.info(f"Fetching vault {vault_address} from API")
        vault = await self.api.get_vault(vault_address)
        return vault

    async def get_vault_timeseries(
        self,
        vault_address: str,
        force_refresh: bool = False,
    ) -> List[VaultTimeseriesPoint]:
        """
        Get timeseries data for a vault.

        Args:
            vault_address: Vault address
            force_refresh: Skip cache and fetch fresh data

        Returns:
            List of VaultTimeseriesPoint objects
        """
        cache_key = vault_address.lower()

        if not force_refresh and cache_key in self._vault_timeseries_cache:
            logger.debug(f"Memory cache hit for vault timeseries {vault_address}")
            return self._vault_timeseries_cache[cache_key]

        logger.info(f"Fetching timeseries for vault {vault_address}")
        timeseries = await self.api.get_vault_timeseries(vault_address)

        if timeseries:
            self._vault_timeseries_cache[cache_key] = timeseries

        return timeseries

    def clear_cache(self) -> int:
        """Clear all cached data."""
        count = len(self._timeseries_cache) + len(self._vault_timeseries_cache)
        self._markets_cache = None
        self._timeseries_cache.clear()
        self._vaults_cache = None
        self._vault_timeseries_cache.clear()
        logger.info(f"Cleared {count} cached items")
        return count

    async def close(self):
        """Close all connections."""
        await self.api.close()
        self.cache.close()
