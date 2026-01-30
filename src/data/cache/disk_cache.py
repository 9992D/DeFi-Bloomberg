"""SQLite-based disk cache with TTL support."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TypeVar, Generic, Callable
from dataclasses import asdict, is_dataclass

import diskcache

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DiskCache:
    """
    SQLite-based disk cache with TTL support.

    Uses diskcache for efficient persistent caching with automatic expiration.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        namespace: str = "morpho",
    ):
        self.settings = settings or get_settings()
        self.namespace = namespace
        self._cache: Optional[diskcache.Cache] = None

    def _get_cache(self) -> diskcache.Cache:
        """Get or create the cache instance."""
        if self._cache is None:
            cache_dir = self.settings.ensure_cache_dir() / self.namespace
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache = diskcache.Cache(str(cache_dir))
        return self._cache

    def _make_key(self, *parts: str) -> str:
        """Create a cache key from parts."""
        key = ":".join(str(p) for p in parts)
        return key

    def _make_hash_key(self, *parts: str) -> str:
        """Create a hashed cache key for long keys."""
        key = self._make_key(*parts)
        if len(key) > 200:
            # Hash long keys
            return hashlib.sha256(key.encode()).hexdigest()
        return key

    def _serialize(self, value: Any) -> Any:
        """Serialize a value for caching."""
        if is_dataclass(value) and not isinstance(value, type):
            return {
                "__dataclass__": type(value).__name__,
                "__module__": type(value).__module__,
                "data": asdict(value),
            }
        elif isinstance(value, list):
            return [self._serialize(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        elif isinstance(value, datetime):
            return {"__datetime__": value.isoformat()}
        elif hasattr(value, "__dict__"):
            return {
                "__class__": type(value).__name__,
                "__module__": type(value).__module__,
                "data": {k: self._serialize(v) for k, v in value.__dict__.items()},
            }
        return value

    def get(
        self,
        key: str,
        default: Optional[T] = None,
    ) -> Optional[T]:
        """
        Get a value from the cache.

        Args:
            key: Cache key
            default: Default value if not found or expired

        Returns:
            Cached value or default
        """
        try:
            cache = self._get_cache()
            value = cache.get(key, default=default)
            return value
        except Exception as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            return default

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = use default)

        Returns:
            True if successful
        """
        if ttl is None:
            ttl = self.settings.cache_ttl_seconds

        try:
            cache = self._get_cache()
            serialized = self._serialize(value)
            cache.set(key, serialized, expire=ttl)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if key existed and was deleted
        """
        try:
            cache = self._get_cache()
            return cache.delete(key)
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False

    def clear(self) -> int:
        """
        Clear all values from the cache.

        Returns:
            Number of items cleared
        """
        try:
            cache = self._get_cache()
            count = len(cache)
            cache.clear()
            return count
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return 0

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[int] = None,
    ) -> T:
        """
        Get a value from cache, or compute and cache it.

        Args:
            key: Cache key
            factory: Function to call if key not found
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value

        value = factory()
        self.set(key, value, ttl)
        return value

    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Async version of get_or_set.

        Args:
            key: Cache key
            factory: Async function to call if key not found
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value

        value = await factory()
        self.set(key, value, ttl)
        return value

    def stats(self) -> dict:
        """Get cache statistics."""
        try:
            cache = self._get_cache()
            return {
                "size": len(cache),
                "volume": cache.volume(),
                "directory": str(cache.directory),
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {}

    def close(self):
        """Close the cache connection."""
        if self._cache:
            self._cache.close()
            self._cache = None


class CacheKeys:
    """Standard cache key patterns."""

    @staticmethod
    def markets() -> str:
        return "markets:all"

    @staticmethod
    def market(market_id: str) -> str:
        return f"market:{market_id}"

    @staticmethod
    def market_timeseries(market_id: str, hours: int) -> str:
        return f"timeseries:{market_id}:{hours}h"

    @staticmethod
    def positions(user_address: str) -> str:
        return f"positions:{user_address.lower()}"

    @staticmethod
    def kpis(market_id: str) -> str:
        return f"kpis:{market_id}"

    @staticmethod
    def rates() -> str:
        return "rates:all"
