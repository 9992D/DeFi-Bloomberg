"""Unit tests for MorphoAPIClient."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.sources.morpho_api import MorphoAPIClient
from src.core.models import Market, Position, TimeseriesPoint


class TestMorphoAPIClient:
    """Tests for MorphoAPIClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return MorphoAPIClient()

    @pytest.fixture
    def mock_market_data(self):
        """Sample market data from API."""
        return {
            "uniqueKey": "0x123abc",
            "lltv": "860000000000000000",  # 0.86 in WAD format
            "oracleAddress": "0xoracle",
            "irmAddress": "0xirm",
            "loanAsset": {
                "address": "0xloan",
                "symbol": "USDC",
                "decimals": 6,
                "priceUsd": "1.0",
            },
            "collateralAsset": {
                "address": "0xcoll",
                "symbol": "WETH",
                "decimals": 18,
                "priceUsd": "3000.0",
            },
            "state": {
                "borrowApy": "0.05",
                "supplyApy": "0.04",
                "fee": "0.1",
                "utilization": "0.85",
                "borrowAssets": "1000000",
                "supplyAssets": "1176470",
                "borrowShares": "1000000",
                "supplyShares": "1100000",
                "rateAtUTarget": "0.04",
                "timestamp": 1700000000,
            },
        }

    def test_parse_decimal_none(self, client):
        """Test parsing None value."""
        result = client._parse_decimal(None)
        assert result == Decimal("0")

    def test_parse_decimal_string(self, client):
        """Test parsing string value."""
        result = client._parse_decimal("0.123")
        assert result == Decimal("0.123")

    def test_parse_decimal_int(self, client):
        """Test parsing integer value."""
        result = client._parse_decimal(100)
        assert result == Decimal("100")

    def test_parse_timestamp_int(self, client):
        """Test parsing Unix timestamp."""
        ts = 1700000000
        result = client._parse_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_parse_timestamp_iso(self, client):
        """Test parsing ISO format timestamp."""
        iso = "2024-01-01T00:00:00Z"
        result = client._parse_timestamp(iso)
        assert isinstance(result, datetime)

    def test_parse_market(self, client, mock_market_data):
        """Test parsing market data."""
        market = client._parse_market(mock_market_data)

        assert isinstance(market, Market)
        assert market.id == "0x123abc"
        assert market.loan_asset_symbol == "USDC"
        assert market.collateral_asset_symbol == "WETH"
        assert market.lltv == Decimal("0.86")
        assert market.supply_apy == Decimal("0.04")
        assert market.borrow_apy == Decimal("0.05")
        assert market.state is not None
        # Utilization is computed from borrow/supply, approximately 0.85
        assert Decimal("0.84") < market.state.utilization < Decimal("0.86")

    def test_parse_market_empty_state(self, client, mock_market_data):
        """Test parsing market with empty state."""
        mock_market_data["state"] = None
        market = client._parse_market(mock_market_data)

        assert market.state is None
        assert market.supply_apy == Decimal("0")

    def test_parse_position(self, client):
        """Test parsing position data."""
        data = {
            "market": {"uniqueKey": "0x123"},
            "user": {"address": "0xuser"},
            "state": {
                "supplyShares": "1000",
                "supplyAssets": "1000",
                "borrowShares": "0",
                "borrowAssets": "0",
                "collateral": "0",
                "timestamp": 1700000000,
            },
        }

        position = client._parse_position(data)

        assert isinstance(position, Position)
        assert position.market_id == "0x123"
        assert position.user == "0xuser"
        assert position.supply_assets == Decimal("1000")
        assert position.is_supplier is True
        assert position.is_borrower is False

    def test_parse_historical_state(self, client):
        """Test parsing historical state data with {x, y} format."""
        data = {
            "supplyApy": [
                {"x": 1700000000, "y": "0.04"},
                {"x": 1700003600, "y": "0.045"},
            ],
            "borrowApy": [
                {"x": 1700000000, "y": "0.05"},
                {"x": 1700003600, "y": "0.055"},
            ],
            "utilization": [
                {"x": 1700000000, "y": "0.85"},
                {"x": 1700003600, "y": "0.86"},
            ],
            "rateAtTarget": [
                {"x": 1700000000, "y": "0.04"},
                {"x": 1700003600, "y": "0.04"},
            ],
        }

        points = client._parse_historical_state(data)

        assert len(points) == 2
        assert isinstance(points[0], TimeseriesPoint)
        assert points[0].supply_apy == Decimal("0.04")
        assert points[0].borrow_apy == Decimal("0.05")
        assert points[0].utilization == Decimal("0.85")
        assert points[1].supply_apy == Decimal("0.045")

    @pytest.mark.asyncio
    async def test_get_markets(self, client, mock_market_data):
        """Test fetching markets."""
        mock_response = {
            "markets": {
                "items": [mock_market_data],
            }
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            markets = await client.get_markets(first=10)

            assert len(markets) == 1
            assert markets[0].id == "0x123abc"
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_market(self, client, mock_market_data):
        """Test fetching single market."""
        mock_response = {
            "marketByUniqueKey": mock_market_data,
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            market = await client.get_market("0x123abc")

            assert market is not None
            assert market.id == "0x123abc"

    @pytest.mark.asyncio
    async def test_get_market_not_found(self, client):
        """Test fetching non-existent market."""
        mock_response = {"marketByUniqueKey": None}

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            market = await client.get_market("nonexistent")

            assert market is None

    @pytest.mark.asyncio
    async def test_get_positions(self, client):
        """Test fetching user positions."""
        mock_response = {
            "positions": {
                "items": [
                    {
                        "market": {"uniqueKey": "0x123"},
                        "user": {"address": "0xuser"},
                        "state": {
                            "supplyShares": "1000",
                            "supplyAssets": "1000",
                            "borrowShares": "0",
                            "borrowAssets": "0",
                            "collateral": "0",
                            "timestamp": 1700000000,
                        },
                    }
                ],
            }
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            positions = await client.get_positions("0xuser")

            assert len(positions) == 1
            assert positions[0].user == "0xuser"
