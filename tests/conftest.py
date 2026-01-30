"""Pytest configuration and fixtures."""

import pytest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

from src.core.models import Market, MarketState, TimeseriesPoint


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_market() -> Market:
    """Create a sample market for testing."""
    return Market(
        id="0xc54d7acf14de29e0e5527cabd7a576506870346a78a11a6762e2cca66322ec41",
        loan_asset="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        loan_asset_symbol="USDC",
        loan_asset_decimals=6,
        collateral_asset="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        collateral_asset_symbol="WETH",
        collateral_asset_decimals=18,
        lltv=Decimal("0.86"),
        oracle="0x48F7E36EB6B826B2dF4B2E630B62Cd25e89E40e2",
        irm="0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC",
        supply_apy=Decimal("0.0523"),
        borrow_apy=Decimal("0.0847"),
        rate_at_target=Decimal("0.0412"),
        state=MarketState(
            total_supply_assets=Decimal("150000000"),
            total_supply_shares=Decimal("145000000"),
            total_borrow_assets=Decimal("127500000"),
            total_borrow_shares=Decimal("125000000"),
            last_update=datetime.now(timezone.utc),
            fee=Decimal("0.1"),
        ),
    )


@pytest.fixture
def sample_timeseries() -> list[TimeseriesPoint]:
    """Create sample timeseries data for testing."""
    import numpy as np
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    points = []

    # Generate 7 days of hourly data
    for i in range(168):
        ts = now - timedelta(hours=168 - i)

        # Simulate realistic rate behavior
        base_supply = 0.05
        base_borrow = 0.08
        base_util = 0.85

        # Add some variation
        noise = np.random.normal(0, 0.005)

        points.append(
            TimeseriesPoint(
                timestamp=ts,
                supply_apy=Decimal(str(max(0.01, base_supply + noise))),
                borrow_apy=Decimal(str(max(0.01, base_borrow + noise * 1.5))),
                utilization=Decimal(str(max(0.5, min(0.99, base_util + noise)))),
                rate_at_target=Decimal(str(max(0.01, 0.04 + noise * 0.1))),
                total_supply_assets=Decimal("150000000"),
                total_borrow_assets=Decimal("127500000"),
            )
        )

    return points


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    from unittest.mock import MagicMock
    from pathlib import Path

    settings = MagicMock()
    settings.morpho_api_url = "https://blue-api.morpho.org/graphql"
    settings.cache_dir = Path("/tmp/morpho_test_cache")
    settings.cache_ttl_seconds = 300
    settings.ui_refresh_interval = 60
    settings.risk_free_rate = 0.05
    settings.wallet_addresses = []
    settings.ensure_cache_dir.return_value = settings.cache_dir

    return settings
