"""Morpho GraphQL API client."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from aiolimiter import AsyncLimiter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from config.settings import Settings, get_settings
from src.core.constants import (
    ETHEREUM_MAINNET_CHAIN_ID,
    MORPHO_API_RATE_LIMIT,
    MORPHO_API_RATE_WINDOW,
    WAD,
    SECONDS_PER_YEAR,
)
from src.core.models import (
    Market, MarketState, Position, TimeseriesPoint,
    Vault, VaultState, VaultAllocation, VaultTimeseriesPoint,
)
from src.protocols.morpho.queries import MorphoQueries

logger = logging.getLogger(__name__)


class MorphoAPIClient:
    """GraphQL client for Morpho Blue API."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._rate_limiter = AsyncLimiter(
            MORPHO_API_RATE_LIMIT, MORPHO_API_RATE_WINDOW
        )
        self._chain_id = ETHEREUM_MAINNET_CHAIN_ID

    async def _execute(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GraphQL query with rate limiting."""
        async with self._rate_limiter:
            # Create fresh transport and client for each request to avoid connection issues
            transport = AIOHTTPTransport(url=self.settings.morpho_api_url)
            client = Client(transport=transport, fetch_schema_from_transport=False)
            async with client as session:
                result = await session.execute(gql(query), variable_values=variables)
                return result

    def _parse_decimal(self, value: Any) -> Decimal:
        """Safely parse a value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _parse_rate_at_target(self, value: Any) -> Decimal:
        """
        Convert rateAtTarget from on-chain format to annual rate.

        On-chain format: per-second rate in WAD (1e18)
        Output: annual rate as decimal (e.g., 0.04 = 4% APR)
        """
        if value is None:
            return Decimal("0")
        raw = self._parse_decimal(value)
        if raw == 0:
            return Decimal("0")
        # Convert: rate_per_second * seconds_per_year / WAD
        annual_rate = raw * Decimal(str(SECONDS_PER_YEAR)) / Decimal(str(WAD))
        return annual_rate

    def _parse_wad(self, value: Any) -> Decimal:
        """
        Convert a WAD value (1e18 scaled) to decimal.

        On-chain format: value * 1e18 (e.g., 0.86 = 860000000000000000)
        Output: decimal (e.g., 0.86)
        """
        if value is None:
            return Decimal("0")
        raw = self._parse_decimal(value)
        if raw == 0:
            return Decimal("0")
        return raw / Decimal(str(WAD))

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse timestamp to datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.fromtimestamp(int(value), tz=timezone.utc)
        return datetime.now(tz=timezone.utc)

    def _parse_market(self, data: Dict[str, Any]) -> Market:
        """Parse market data from API response."""
        loan_asset = data.get("loanAsset", {}) or {}
        collateral_asset = data.get("collateralAsset", {}) or {}
        state_data = data.get("state", {}) or {}

        state = None
        if state_data:
            state = MarketState(
                total_supply_assets=self._parse_decimal(state_data.get("supplyAssets")),
                total_supply_shares=self._parse_decimal(state_data.get("supplyShares")),
                total_borrow_assets=self._parse_decimal(state_data.get("borrowAssets")),
                total_borrow_shares=self._parse_decimal(state_data.get("borrowShares")),
                last_update=self._parse_timestamp(state_data.get("timestamp")),
                fee=self._parse_decimal(state_data.get("fee")),
            )

        # Parse creation timestamp if available
        creation_ts = data.get("creationTimestamp")
        creation_timestamp = self._parse_timestamp(creation_ts) if creation_ts else None

        return Market(
            id=data.get("uniqueKey", data.get("id", "")),
            loan_asset=loan_asset.get("address", ""),
            loan_asset_symbol=loan_asset.get("symbol", "???"),
            loan_asset_decimals=int(loan_asset.get("decimals", 18)),
            collateral_asset=collateral_asset.get("address", ""),
            collateral_asset_symbol=collateral_asset.get("symbol", "???"),
            collateral_asset_decimals=int(collateral_asset.get("decimals", 18)),
            lltv=self._parse_wad(data.get("lltv")),
            oracle=data.get("oracleAddress", ""),
            irm=data.get("irmAddress", ""),
            creation_timestamp=creation_timestamp,
            supply_apy=self._parse_decimal(state_data.get("supplyApy")),
            borrow_apy=self._parse_decimal(state_data.get("borrowApy")),
            rate_at_target=self._parse_rate_at_target(state_data.get("rateAtTarget")),
            loan_asset_price_usd=self._parse_decimal(loan_asset.get("priceUsd")),
            collateral_asset_price_usd=self._parse_decimal(collateral_asset.get("priceUsd")),
            state=state,
        )

    def _parse_position(self, data: Dict[str, Any]) -> Position:
        """Parse position data from API response."""
        market_data = data.get("market", {}) or {}
        user_data = data.get("user", {}) or {}
        state_data = data.get("state", {}) or {}

        return Position(
            market_id=market_data.get("uniqueKey", ""),
            user=user_data.get("address", ""),
            supply_shares=self._parse_decimal(state_data.get("supplyShares")),
            supply_assets=self._parse_decimal(state_data.get("supplyAssets")),
            borrow_shares=self._parse_decimal(state_data.get("borrowShares")),
            borrow_assets=self._parse_decimal(state_data.get("borrowAssets")),
            collateral=self._parse_decimal(state_data.get("collateral")),
            last_update=self._parse_timestamp(state_data.get("timestamp")) if state_data.get("timestamp") else None,
        )

    def _parse_historical_state(self, historical_data: Dict[str, Any]) -> List[TimeseriesPoint]:
        """
        Parse historical state data from API response.

        The API returns data in format:
        {
            "supplyApy": [{"x": timestamp, "y": value}, ...],
            "borrowApy": [{"x": timestamp, "y": value}, ...],
            "utilization": [{"x": timestamp, "y": value}, ...],
            "rateAtTarget": [{"x": timestamp, "y": value}, ...]
        }

        We need to merge these into TimeseriesPoint objects by timestamp.
        """
        if not historical_data:
            return []

        # Extract arrays
        supply_apy_data = historical_data.get("supplyApy", []) or []
        borrow_apy_data = historical_data.get("borrowApy", []) or []
        utilization_data = historical_data.get("utilization", []) or []
        rate_at_target_data = historical_data.get("rateAtTarget", []) or []

        # Build dict keyed by timestamp
        points_by_ts: Dict[float, Dict[str, Any]] = {}

        for item in supply_apy_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["supply_apy"] = item.get("y")

        for item in borrow_apy_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["borrow_apy"] = item.get("y")

        for item in utilization_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["utilization"] = item.get("y")

        for item in rate_at_target_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["rate_at_target"] = item.get("y")

        # Convert to TimeseriesPoint objects
        points = []
        for ts, data in points_by_ts.items():
            points.append(TimeseriesPoint(
                timestamp=self._parse_timestamp(ts),
                supply_apy=self._parse_decimal(data.get("supply_apy")),
                borrow_apy=self._parse_decimal(data.get("borrow_apy")),
                utilization=self._parse_decimal(data.get("utilization")),
                rate_at_target=self._parse_rate_at_target(data.get("rate_at_target")),
            ))

        # Sort by timestamp
        points.sort(key=lambda x: x.timestamp)
        return points

    async def get_markets(
        self,
        first: int = 50,
        skip: int = 0,
    ) -> List[Market]:
        """Fetch markets from Morpho API."""
        try:
            result = await self._execute(
                MorphoQueries.MARKETS_QUERY,
                {
                    "first": first,
                    "skip": skip,
                    "chainId": self._chain_id,
                },
            )

            markets_data = result.get("markets", {}).get("items", [])
            return [self._parse_market(m) for m in markets_data]

        except Exception as e:
            logger.error(f"Failed to fetch markets: {e}")
            raise

    async def get_market(self, market_id: str) -> Optional[Market]:
        """Fetch a single market by ID with historical data."""
        try:
            result = await self._execute(
                MorphoQueries.MARKET_DETAIL_QUERY,
                {
                    "uniqueKey": market_id,
                    "chainId": self._chain_id,
                },
            )

            market_data = result.get("marketByUniqueKey")
            if not market_data:
                return None

            market = self._parse_market(market_data)

            # Parse historical data if available
            historical_data = market_data.get("historicalState")
            if historical_data:
                market.timeseries = self._parse_historical_state(historical_data)

            return market

        except Exception as e:
            logger.error(f"Failed to fetch market {market_id}: {e}")
            raise

    async def get_market_timeseries(
        self,
        market_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[TimeseriesPoint]:
        """Fetch timeseries data for a market.

        Args:
            market_id: The market unique key
            start_timestamp: Start of time range (unix timestamp)
            end_timestamp: End of time range (unix timestamp)
            interval: Data interval - HOUR, DAY, WEEK, MONTH, QUARTER, YEAR
        """
        try:
            # Build options for timeseries query
            now = int(datetime.now(tz=timezone.utc).timestamp())
            # Default to 90 days ago if not specified
            default_start = now - (90 * 24 * 60 * 60)

            options = {
                "startTimestamp": start_timestamp or default_start,
                "endTimestamp": end_timestamp or now,
                "interval": interval,
            }

            result = await self._execute(
                MorphoQueries.MARKET_TIMESERIES_QUERY,
                {
                    "uniqueKey": market_id,
                    "chainId": self._chain_id,
                    "options": options,
                },
            )

            market_data = result.get("marketByUniqueKey")
            if not market_data:
                return []

            historical_data = market_data.get("historicalState")
            points = self._parse_historical_state(historical_data)

            return points

        except Exception as e:
            logger.error(f"Failed to fetch timeseries for market {market_id}: {e}")
            raise

    async def get_positions(
        self,
        user_address: str,
        first: int = 100,
    ) -> List[Position]:
        """Fetch positions for a user."""
        try:
            result = await self._execute(
                MorphoQueries.POSITIONS_QUERY,
                {
                    "userAddress": user_address.lower(),
                    "chainId": self._chain_id,
                    "first": first,
                },
            )

            positions_data = result.get("positions", {}).get("items", [])
            return [self._parse_position(p) for p in positions_data]

        except Exception as e:
            logger.error(f"Failed to fetch positions for {user_address}: {e}")
            raise

    async def get_rates(self, first: int = 50) -> Dict[str, Dict[str, Decimal]]:
        """Fetch lightweight rate data for all markets."""
        try:
            result = await self._execute(
                MorphoQueries.RATES_QUERY,
                {
                    "chainId": self._chain_id,
                    "first": first,
                },
            )

            rates = {}
            markets_data = result.get("markets", {}).get("items", [])

            for m in markets_data:
                market_id = m.get("uniqueKey", "")
                state = m.get("state", {}) or {}
                rates[market_id] = {
                    "supply_apy": self._parse_decimal(state.get("supplyApy")),
                    "borrow_apy": self._parse_decimal(state.get("borrowApy")),
                    "utilization": self._parse_decimal(state.get("utilization")),
                    "rate_at_target": self._parse_decimal(state.get("rateAtTarget")),
                }

            return rates

        except Exception as e:
            logger.error(f"Failed to fetch rates: {e}")
            raise

    # ========== VAULT METHODS ==========

    def _parse_vault_allocation(self, data: Dict[str, Any]) -> VaultAllocation:
        """Parse vault allocation data."""
        market_data = data.get("market", {}) or {}
        loan_asset = market_data.get("loanAsset", {}) or {}
        collateral_asset = market_data.get("collateralAsset", {}) or {}

        return VaultAllocation(
            market_id=market_data.get("uniqueKey", ""),
            loan_asset_symbol=loan_asset.get("symbol", "???"),
            collateral_asset_symbol=collateral_asset.get("symbol") if collateral_asset else None,
            lltv=self._parse_wad(market_data.get("lltv")),
            supply_assets=self._parse_decimal(data.get("supplyAssets")),
            supply_assets_usd=self._parse_decimal(data.get("supplyAssetsUsd")),
            supply_shares=self._parse_decimal(data.get("supplyShares")),
        )

    def _parse_vault(self, data: Dict[str, Any]) -> Vault:
        """Parse vault data from API response."""
        asset = data.get("asset", {}) or {}
        state_data = data.get("state", {}) or {}

        state = None
        if state_data:
            allocations = []
            for alloc_data in state_data.get("allocation", []) or []:
                allocations.append(self._parse_vault_allocation(alloc_data))

            state = VaultState(
                total_assets=self._parse_decimal(state_data.get("totalAssets")),
                total_assets_usd=self._parse_decimal(state_data.get("totalAssetsUsd")),
                total_supply=self._parse_decimal(state_data.get("totalSupply")),
                fee=self._parse_decimal(state_data.get("fee")),
                share_price=self._parse_decimal(state_data.get("sharePriceNumber")),
                share_price_usd=self._parse_decimal(state_data.get("sharePriceUsd")),
                last_update=self._parse_timestamp(state_data.get("timestamp")),
                allocation=allocations,
            )

        # Parse creation timestamp if available
        creation_ts = data.get("creationTimestamp")
        creation_timestamp = self._parse_timestamp(creation_ts) if creation_ts else None

        return Vault(
            id=data.get("address", ""),
            name=data.get("name", ""),
            symbol=data.get("symbol", ""),
            asset_address=asset.get("address", ""),
            asset_symbol=asset.get("symbol", "???"),
            asset_decimals=int(asset.get("decimals", 18)),
            asset_price_usd=self._parse_decimal(asset.get("priceUsd")),
            apy=self._parse_decimal(state_data.get("apy")),
            net_apy=self._parse_decimal(state_data.get("netApy")),
            creation_timestamp=creation_timestamp,
            state=state,
        )

    def _parse_vault_historical_state(self, historical_data: Dict[str, Any]) -> List[VaultTimeseriesPoint]:
        """Parse vault historical state data."""
        if not historical_data:
            return []

        apy_data = historical_data.get("apy", []) or []
        net_apy_data = historical_data.get("netApy", []) or []
        total_assets_data = historical_data.get("totalAssets", []) or []
        share_price_data = historical_data.get("sharePriceNumber", []) or []

        # Build dict keyed by timestamp
        points_by_ts: Dict[float, Dict[str, Any]] = {}

        for item in apy_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["apy"] = item.get("y")

        for item in net_apy_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["net_apy"] = item.get("y")

        for item in total_assets_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["total_assets"] = item.get("y")

        for item in share_price_data:
            ts = item.get("x")
            if ts is not None:
                if ts not in points_by_ts:
                    points_by_ts[ts] = {}
                points_by_ts[ts]["share_price"] = item.get("y")

        # Convert to VaultTimeseriesPoint objects
        points = []
        for ts, data in points_by_ts.items():
            points.append(VaultTimeseriesPoint(
                timestamp=self._parse_timestamp(ts),
                apy=self._parse_decimal(data.get("apy")),
                net_apy=self._parse_decimal(data.get("net_apy")),
                total_assets=self._parse_decimal(data.get("total_assets")),
                share_price=self._parse_decimal(data.get("share_price")) if data.get("share_price") else None,
            ))

        points.sort(key=lambda x: x.timestamp)
        return points

    async def get_vaults(
        self,
        first: int = 50,
        skip: int = 0,
    ) -> List[Vault]:
        """Fetch vaults from Morpho API."""
        try:
            result = await self._execute(
                MorphoQueries.VAULTS_QUERY,
                {
                    "first": first,
                    "skip": skip,
                    "chainId": self._chain_id,
                },
            )

            vaults_data = result.get("vaults", {}).get("items", [])
            return [self._parse_vault(v) for v in vaults_data]

        except Exception as e:
            logger.error(f"Failed to fetch vaults: {e}")
            raise

    async def get_vault(self, vault_address: str) -> Optional[Vault]:
        """Fetch a single vault by address with historical data."""
        try:
            result = await self._execute(
                MorphoQueries.VAULT_DETAIL_QUERY,
                {
                    "address": vault_address,
                    "chainId": self._chain_id,
                },
            )

            vaults_data = result.get("vaults", {}).get("items", [])
            if not vaults_data:
                return None

            vault_data = vaults_data[0]
            vault = self._parse_vault(vault_data)

            # Parse historical data if available
            historical_data = vault_data.get("historicalState")
            if historical_data:
                vault.timeseries = self._parse_vault_historical_state(historical_data)

            return vault

        except Exception as e:
            logger.error(f"Failed to fetch vault {vault_address}: {e}")
            raise

    async def get_vault_timeseries(
        self,
        vault_address: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[VaultTimeseriesPoint]:
        """Fetch timeseries data for a vault.

        Args:
            vault_address: The vault address
            start_timestamp: Start of time range (unix timestamp)
            end_timestamp: End of time range (unix timestamp)
            interval: Data interval - HOUR, DAY, WEEK, MONTH, QUARTER, YEAR
        """
        try:
            # Build options for timeseries query
            now = int(datetime.now(tz=timezone.utc).timestamp())
            # Default to 90 days ago if not specified
            default_start = now - (90 * 24 * 60 * 60)

            options = {
                "startTimestamp": start_timestamp or default_start,
                "endTimestamp": end_timestamp or now,
                "interval": interval,
            }

            result = await self._execute(
                MorphoQueries.VAULT_TIMESERIES_QUERY,
                {
                    "address": vault_address,
                    "chainId": self._chain_id,
                    "options": options,
                },
            )

            vaults_data = result.get("vaults", {}).get("items", [])
            if not vaults_data:
                return []

            historical_data = vaults_data[0].get("historicalState")
            return self._parse_vault_historical_state(historical_data)

        except Exception as e:
            logger.error(f"Failed to fetch timeseries for vault {vault_address}: {e}")
            raise

    async def close(self):
        """Close the client connection (no-op as we create fresh connections)."""
        pass
