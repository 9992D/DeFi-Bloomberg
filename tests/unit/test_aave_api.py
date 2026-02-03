"""Unit tests for Aave v3 API client and parser."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.data.clients.aave.parser import AaveParser
from src.data.clients.aave.client import AaveClient
from src.core.models import Market, Position, TimeseriesPoint


class TestAaveParser:
    """Tests for AaveParser."""

    @pytest.fixture
    def parser(self):
        """Create a test parser."""
        return AaveParser()

    def test_parse_decimal_none(self, parser):
        """Test parsing None value."""
        result = parser.parse_decimal(None)
        assert result == Decimal("0")

    def test_parse_decimal_string(self, parser):
        """Test parsing string value."""
        result = parser.parse_decimal("0.123")
        assert result == Decimal("0.123")

    def test_parse_decimal_int(self, parser):
        """Test parsing integer value."""
        result = parser.parse_decimal(100)
        assert result == Decimal("100")

    def test_parse_decimal_invalid(self, parser):
        """Test parsing invalid value."""
        result = parser.parse_decimal("invalid")
        assert result == Decimal("0")

    def test_parse_timestamp_int(self, parser):
        """Test parsing Unix timestamp."""
        ts = 1700000000
        result = parser.parse_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_parse_timestamp_iso(self, parser):
        """Test parsing ISO format timestamp."""
        iso = "2024-01-01T00:00:00Z"
        result = parser.parse_timestamp(iso)
        assert isinstance(result, datetime)


class TestAaveParserReserve:
    """Tests for AaveParser reserve parsing."""

    @pytest.fixture
    def parser(self):
        return AaveParser()

    @pytest.fixture
    def mock_reserve_data(self):
        """Sample reserve data from Aave official API."""
        return {
            "underlyingToken": {
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "symbol": "USDC",
                "name": "USD Coin",
                "decimals": 6,
            },
            "usdExchangeRate": "1.0001",
            "supplyInfo": {
                "apy": {"value": "0.0312"},  # 3.12% APY
                "maxLTV": {"value": "0.80"},  # 80%
                "liquidationThreshold": {"value": "0.85"},  # 85%
                "total": {"value": "1500000000"},  # 1.5B USDC
                "canBeCollateral": True,
            },
            "borrowInfo": {
                "apy": {"value": "0.0456"},  # 4.56% APY
                "total": {
                    "amount": {"value": "1200000000"},
                    "usd": "1200120000",
                },
                "utilizationRate": {"value": "0.80"},  # 80%
                "availableLiquidity": {
                    "amount": {"value": "300000000"},
                    "usd": "300030000",
                },
            },
            "isFrozen": False,
            "isPaused": False,
        }

    def test_parse_reserve_to_market(self, parser, mock_reserve_data):
        """Test parsing reserve data to Market model."""
        market = parser.parse_reserve_to_market(
            mock_reserve_data, "AaveV3Ethereum", 1
        )

        assert isinstance(market, Market)
        assert market.id == "1-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        assert market.loan_asset_symbol == "USDC"
        assert market.loan_asset_decimals == 6
        assert market.collateral_asset_symbol == "MULTI"
        assert market.lltv == Decimal("0.85")
        assert market.supply_apy == Decimal("0.0312")
        assert market.borrow_apy == Decimal("0.0456")
        assert market.loan_asset_price_usd == Decimal("1.0001")
        assert market.state is not None

    def test_parse_reserve_state(self, parser, mock_reserve_data):
        """Test parsing reserve state."""
        market = parser.parse_reserve_to_market(
            mock_reserve_data, "AaveV3Ethereum", 1
        )

        # Total supply in raw units (with decimals)
        expected_supply = Decimal("1500000000") * Decimal(10 ** 6)
        assert market.state.total_supply_assets == expected_supply

        expected_borrow = Decimal("1200000000") * Decimal(10 ** 6)
        assert market.state.total_borrow_assets == expected_borrow

    def test_parse_reserve_no_borrow_info(self, parser, mock_reserve_data):
        """Test parsing reserve without borrow info (non-borrowable asset)."""
        mock_reserve_data["borrowInfo"] = None
        market = parser.parse_reserve_to_market(
            mock_reserve_data, "AaveV3Ethereum", 1
        )

        assert market.borrow_apy == Decimal("0")
        assert market.state.total_borrow_assets == Decimal("0")


class TestAaveParserPosition:
    """Tests for AaveParser position parsing."""

    @pytest.fixture
    def parser(self):
        return AaveParser()

    @pytest.fixture
    def mock_user_reserve(self):
        """Sample user reserve data from Aave official API."""
        return {
            "underlyingToken": {
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "symbol": "USDC",
                "decimals": 6,
            },
            "userState": {
                "suppliedAmount": {
                    "amount": {"value": "10000"},  # 10,000 USDC
                    "usd": "10001",
                },
                "borrowedAmount": {
                    "amount": {"value": "0"},
                    "usd": "0",
                },
                "collateralEnabled": True,
            },
        }

    def test_parse_position_supply_only(self, parser, mock_user_reserve):
        """Test parsing position with supply only."""
        position = parser.parse_user_reserve_to_position(mock_user_reserve, 1)

        assert isinstance(position, Position)
        assert position.market_id == "1-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        expected_supply = Decimal("10000") * Decimal(10 ** 6)
        assert position.supply_assets == expected_supply
        assert position.borrow_assets == Decimal("0")
        assert position.collateral == expected_supply  # Collateral enabled

    def test_parse_position_no_collateral(self, parser, mock_user_reserve):
        """Test parsing position without collateral enabled."""
        mock_user_reserve["userState"]["collateralEnabled"] = False
        position = parser.parse_user_reserve_to_position(mock_user_reserve, 1)

        assert position.collateral == Decimal("0")

    def test_parse_position_no_user_state(self, parser, mock_user_reserve):
        """Test parsing position without user state."""
        mock_user_reserve["userState"] = None
        position = parser.parse_user_reserve_to_position(mock_user_reserve, 1)

        assert position is None

    def test_parse_position_zero_balance(self, parser, mock_user_reserve):
        """Test parsing position with zero balance."""
        mock_user_reserve["userState"]["suppliedAmount"]["amount"]["value"] = "0"
        position = parser.parse_user_reserve_to_position(mock_user_reserve, 1)

        assert position is None


class TestAaveParserTimeseries:
    """Tests for AaveParser timeseries parsing."""

    @pytest.fixture
    def parser(self):
        return AaveParser()

    def test_parse_history_empty(self, parser):
        """Test parsing empty history."""
        points = parser.parse_history_to_timeseries([])
        assert points == []


class TestAaveClientTimeseries:
    """Tests for AaveClient timeseries functionality."""

    @pytest.fixture
    def client(self):
        return AaveClient()

    def test_get_time_window_day(self, client):
        """Test time window mapping for 1 day."""
        assert client._get_time_window(1) == "LAST_DAY"
        assert client._get_time_window(None) == "LAST_DAY"

    def test_get_time_window_week(self, client):
        """Test time window mapping for week."""
        assert client._get_time_window(5) == "LAST_WEEK"
        assert client._get_time_window(7) == "LAST_WEEK"

    def test_get_time_window_month(self, client):
        """Test time window mapping for month."""
        assert client._get_time_window(14) == "LAST_MONTH"
        assert client._get_time_window(30) == "LAST_MONTH"

    def test_get_time_window_six_months(self, client):
        """Test time window mapping for 6 months."""
        assert client._get_time_window(60) == "LAST_SIX_MONTHS"
        assert client._get_time_window(180) == "LAST_SIX_MONTHS"

    def test_get_time_window_year(self, client):
        """Test time window mapping for year."""
        assert client._get_time_window(365) == "LAST_YEAR"

    def test_parse_market_id_valid(self, client):
        """Test parsing valid market ID."""
        chain_id, address = client._parse_market_id("1-0xabc123")
        assert chain_id == 1
        assert address == "0xabc123"

    def test_parse_market_id_invalid_format(self, client):
        """Test parsing invalid market ID format."""
        with pytest.raises(ValueError, match="Invalid market ID format"):
            client._parse_market_id("invalid")

    def test_parse_market_id_invalid_chain(self, client):
        """Test parsing market ID with invalid chain."""
        with pytest.raises(ValueError, match="Invalid chain ID"):
            client._parse_market_id("abc-0x123")

    @pytest.mark.asyncio
    async def test_get_market_timeseries(self, client):
        """Test fetching market timeseries."""
        mock_response = {
            "supplyAPYHistory": [
                {"date": "2024-01-01T00:00:00+00:00", "avgRate": {"value": "0.05"}},
                {"date": "2024-01-02T00:00:00+00:00", "avgRate": {"value": "0.052"}},
            ],
            "borrowAPYHistory": [
                {"date": "2024-01-01T00:00:00+00:00", "avgRate": {"value": "0.07"}},
                {"date": "2024-01-02T00:00:00+00:00", "avgRate": {"value": "0.072"}},
            ],
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            timeseries = await client.get_market_timeseries(
                "1-0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
            )

            assert len(timeseries) == 2
            assert timeseries[0].supply_apy == Decimal("0.05")
            assert timeseries[0].borrow_apy == Decimal("0.07")
            assert timeseries[1].supply_apy == Decimal("0.052")
            assert timeseries[1].borrow_apy == Decimal("0.072")

    @pytest.mark.asyncio
    async def test_get_market_timeseries_invalid_market(self, client):
        """Test fetching timeseries for invalid market ID."""
        timeseries = await client.get_market_timeseries("invalid")
        assert timeseries == []

    @pytest.mark.asyncio
    async def test_get_market_timeseries_empty_response(self, client):
        """Test fetching timeseries with empty API response."""
        mock_response = {
            "supplyAPYHistory": [],
            "borrowAPYHistory": [],
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_response

            timeseries = await client.get_market_timeseries(
                "1-0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
            )

            assert timeseries == []


class TestAaveClient:
    """Tests for AaveClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return AaveClient()

    @pytest.fixture
    def mock_markets_response(self):
        """Sample markets response from Aave official API."""
        return {
            "markets": [
                {
                    "name": "AaveV3Ethereum",
                    "chain": {"chainId": 1, "name": "Ethereum"},
                    "reserves": [
                        {
                            "underlyingToken": {
                                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                "symbol": "USDC",
                                "name": "USD Coin",
                                "decimals": 6,
                            },
                            "usdExchangeRate": "1.0001",
                            "supplyInfo": {
                                "apy": {"value": "0.0312"},
                                "maxLTV": {"value": "0.80"},
                                "liquidationThreshold": {"value": "0.85"},
                                "total": {"value": "1500000000"},
                                "canBeCollateral": True,
                            },
                            "borrowInfo": {
                                "apy": {"value": "0.0456"},
                                "total": {
                                    "amount": {"value": "1200000000"},
                                    "usd": "1200120000",
                                },
                                "utilizationRate": {"value": "0.80"},
                                "availableLiquidity": {
                                    "amount": {"value": "300000000"},
                                    "usd": "300030000",
                                },
                            },
                            "isFrozen": False,
                            "isPaused": False,
                        },
                    ],
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_get_markets(self, client, mock_markets_response):
        """Test fetching markets."""
        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_markets_response

            markets = await client.get_markets(first=10)

            assert len(markets) == 1
            assert markets[0].loan_asset_symbol == "USDC"
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_markets_skip_frozen(self, client, mock_markets_response):
        """Test that frozen reserves are skipped."""
        mock_markets_response["markets"][0]["reserves"][0]["isFrozen"] = True

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_markets_response

            markets = await client.get_markets(first=10)

            assert len(markets) == 0

    @pytest.mark.asyncio
    async def test_get_market(self, client, mock_markets_response):
        """Test fetching single market."""
        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_markets_response

            market = await client.get_market(
                "1-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
            )

            assert market is not None
            assert market.loan_asset_symbol == "USDC"

    @pytest.mark.asyncio
    async def test_get_market_not_found(self, client, mock_markets_response):
        """Test fetching non-existent market."""
        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_markets_response

            market = await client.get_market("1-0xnonexistent")

            assert market is None

    @pytest.mark.asyncio
    async def test_get_market_invalid_id(self, client):
        """Test fetching market with invalid ID format."""
        market = await client.get_market("invalid-id-format")
        assert market is None

    @pytest.mark.asyncio
    async def test_get_rates(self, client, mock_markets_response):
        """Test fetching rates."""
        mock_rates_response = {
            "markets": [
                {
                    "reserves": [
                        {
                            "underlyingToken": {
                                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                "symbol": "USDC",
                            },
                            "supplyInfo": {"apy": {"value": "0.0312"}},
                            "borrowInfo": {
                                "apy": {"value": "0.0456"},
                                "utilizationRate": {"value": "0.80"},
                            },
                        }
                    ]
                }
            ]
        }

        with patch.object(client, "_execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_rates_response

            rates = await client.get_rates(first=10)

            market_id = "1-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
            assert market_id in rates
            assert rates[market_id]["supply_apy"] == Decimal("0.0312")
            assert rates[market_id]["borrow_apy"] == Decimal("0.0456")
            assert rates[market_id]["utilization"] == Decimal("0.80")

    def test_protocol_type(self, client):
        """Test protocol type property."""
        from src.data.clients.base import ProtocolType

        assert client.protocol_type == ProtocolType.AAVE

    def test_protocol_name(self, client):
        """Test protocol name property."""
        assert client.protocol_name == "Aave v3"

    def test_supports_vaults(self, client):
        """Test supports_vaults property."""
        assert client.supports_vaults is False
