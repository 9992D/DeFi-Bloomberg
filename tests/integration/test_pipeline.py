"""Integration tests for data pipeline."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.pipeline import DataPipeline
from src.data.sources.morpho_api import MorphoAPIClient
from src.data.cache.disk_cache import DiskCache
from src.core.models import Market, MarketState


class TestDataPipeline:
    """Integration tests for DataPipeline."""

    @pytest.fixture
    def mock_market(self):
        """Create a mock market."""
        return Market(
            id="0xtest123",
            loan_asset="0xloan",
            loan_asset_symbol="USDC",
            loan_asset_decimals=6,
            collateral_asset="0xcoll",
            collateral_asset_symbol="WETH",
            collateral_asset_decimals=18,
            lltv=Decimal("0.86"),
            oracle="0xoracle",
            irm="0xirm",
            supply_apy=Decimal("0.05"),
            borrow_apy=Decimal("0.08"),
            rate_at_target=Decimal("0.04"),
            state=MarketState(
                total_supply_assets=Decimal("1000000"),
                total_supply_shares=Decimal("1000000"),
                total_borrow_assets=Decimal("850000"),
                total_borrow_shares=Decimal("850000"),
                last_update=datetime.now(timezone.utc),
                fee=Decimal("0.1"),
            ),
        )

    @pytest.fixture
    def mock_api(self, mock_market):
        """Create a mock API client."""
        api = MagicMock(spec=MorphoAPIClient)
        api.get_markets = AsyncMock(return_value=[mock_market])
        api.get_market = AsyncMock(return_value=mock_market)
        api.get_market_timeseries = AsyncMock(return_value=[])
        api.get_positions = AsyncMock(return_value=[])
        api.close = AsyncMock()
        return api

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache."""
        cache = MagicMock(spec=DiskCache)
        cache.get = MagicMock(return_value=None)
        cache.set = MagicMock(return_value=True)
        cache.clear = MagicMock(return_value=0)
        cache.close = MagicMock()
        return cache

    @pytest.fixture
    def pipeline(self, mock_api, mock_cache):
        """Create a pipeline with mocked dependencies."""
        return DataPipeline(api_client=mock_api, cache=mock_cache)

    @pytest.mark.asyncio
    async def test_get_markets_first_call(self, pipeline, mock_api, mock_market):
        """Test fetching markets on first call."""
        markets = await pipeline.get_markets()

        assert len(markets) == 1
        assert markets[0].id == mock_market.id
        mock_api.get_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_markets_memory_cache_hit(self, pipeline, mock_api, mock_market):
        """Test that second call uses memory cache."""
        # First call
        await pipeline.get_markets()
        mock_api.get_markets.assert_called_once()

        # Second call should use memory cache
        markets = await pipeline.get_markets()
        assert len(markets) == 1
        # API should still only be called once
        mock_api.get_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_markets_force_refresh(self, pipeline, mock_api, mock_market):
        """Test force refresh bypasses memory cache."""
        # First call
        await pipeline.get_markets()

        # Force refresh
        markets = await pipeline.get_markets(force_refresh=True)

        assert len(markets) == 1
        # API should be called twice
        assert mock_api.get_markets.call_count == 2

    @pytest.mark.asyncio
    async def test_get_market(self, pipeline, mock_api, mock_market):
        """Test fetching single market."""
        market = await pipeline.get_market("0xtest123")

        assert market is not None
        assert market.id == mock_market.id

    @pytest.mark.asyncio
    async def test_get_market_from_memory_cache(self, pipeline, mock_api, mock_market):
        """Test fetching market from memory cache after loading markets."""
        # Load markets first
        await pipeline.get_markets()

        # Get single market - should use memory cache
        market = await pipeline.get_market("0xtest123")

        assert market is not None
        assert market.id == mock_market.id
        # get_market API should not be called since it's in memory
        mock_api.get_market.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_market_not_found(self, pipeline, mock_api):
        """Test fetching non-existent market."""
        mock_api.get_market.return_value = None

        market = await pipeline.get_market("nonexistent")

        assert market is None

    @pytest.mark.asyncio
    async def test_refresh_all(self, pipeline, mock_api, mock_market):
        """Test refresh all data."""
        results = await pipeline.refresh_all()

        assert "markets" in results
        assert results["markets"] == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self, pipeline):
        """Test clearing memory cache."""
        # Add some data to memory cache
        pipeline._timeseries_cache["test"] = []
        pipeline._timeseries_cache["test2"] = []

        count = pipeline.clear_cache()

        assert count == 2
        assert pipeline._markets_cache is None
        assert len(pipeline._timeseries_cache) == 0

    @pytest.mark.asyncio
    async def test_close(self, pipeline, mock_api, mock_cache):
        """Test closing pipeline."""
        await pipeline.close()

        mock_api.close.assert_called_once()
        mock_cache.close.assert_called_once()
