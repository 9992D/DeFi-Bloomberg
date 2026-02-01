"""Morpho GraphQL API client implementing ProtocolClient interface."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from aiolimiter import AsyncLimiter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from config.settings import Settings, get_settings
from src.core.constants import ETHEREUM_MAINNET_CHAIN_ID
from src.core.models import (
    Market,
    Position,
    TimeseriesPoint,
    Vault,
    VaultTimeseriesPoint,
)
from src.data.clients.base import ProtocolClient, ProtocolType
from src.data.clients.morpho.parser import MorphoParser
from src.protocols.morpho.config import (
    MORPHO_API_RATE_LIMIT,
    MORPHO_API_RATE_WINDOW,
)
from src.protocols.morpho.queries import MorphoQueries

logger = logging.getLogger(__name__)


class MorphoClient(ProtocolClient):
    """GraphQL client for Morpho Blue API implementing ProtocolClient interface."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._rate_limiter = AsyncLimiter(
            MORPHO_API_RATE_LIMIT, MORPHO_API_RATE_WINDOW
        )
        self._chain_id = ETHEREUM_MAINNET_CHAIN_ID
        self._parser = MorphoParser()

    @property
    def protocol_type(self) -> ProtocolType:
        return ProtocolType.MORPHO

    @property
    def protocol_name(self) -> str:
        return "Morpho Blue"

    @property
    def supports_vaults(self) -> bool:
        return True

    async def _execute(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GraphQL query with rate limiting."""
        async with self._rate_limiter:
            transport = AIOHTTPTransport(url=self.settings.morpho_api_url)
            client = Client(transport=transport, fetch_schema_from_transport=False)
            async with client as session:
                result = await session.execute(gql(query), variable_values=variables)
                return result

    # ========== MARKET METHODS ==========

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
            return [self._parser.parse_market(m) for m in markets_data]

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

            market = self._parser.parse_market(market_data)

            # Parse historical data if available
            historical_data = market_data.get("historicalState")
            if historical_data:
                market.timeseries = self._parser.parse_historical_state(historical_data)

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
        """Fetch timeseries data for a market."""
        try:
            now = int(datetime.now(tz=timezone.utc).timestamp())
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
            return self._parser.parse_historical_state(historical_data)

        except Exception as e:
            logger.error(f"Failed to fetch timeseries for market {market_id}: {e}")
            raise

    # ========== POSITION METHODS ==========

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
            return [self._parser.parse_position(p) for p in positions_data]

        except Exception as e:
            logger.error(f"Failed to fetch positions for {user_address}: {e}")
            raise

    # ========== RATE METHODS ==========

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
                    "supply_apy": self._parser.parse_decimal(state.get("supplyApy")),
                    "borrow_apy": self._parser.parse_decimal(state.get("borrowApy")),
                    "utilization": self._parser.parse_decimal(state.get("utilization")),
                    "rate_at_target": self._parser.parse_decimal(state.get("rateAtTarget")),
                }

            return rates

        except Exception as e:
            logger.error(f"Failed to fetch rates: {e}")
            raise

    # ========== VAULT METHODS ==========

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
            return [self._parser.parse_vault(v) for v in vaults_data]

        except Exception as e:
            logger.error(f"Failed to fetch vaults: {e}")
            raise

    async def get_vault(self, vault_id: str) -> Optional[Vault]:
        """Fetch a single vault by address with historical data."""
        try:
            result = await self._execute(
                MorphoQueries.VAULT_DETAIL_QUERY,
                {
                    "address": vault_id,
                    "chainId": self._chain_id,
                },
            )

            vaults_data = result.get("vaults", {}).get("items", [])
            if not vaults_data:
                return None

            vault_data = vaults_data[0]
            vault = self._parser.parse_vault(vault_data)

            # Parse historical data if available
            historical_data = vault_data.get("historicalState")
            if historical_data:
                vault.timeseries = self._parser.parse_vault_historical_state(historical_data)

            return vault

        except Exception as e:
            logger.error(f"Failed to fetch vault {vault_id}: {e}")
            raise

    async def get_vault_timeseries(
        self,
        vault_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[VaultTimeseriesPoint]:
        """Fetch timeseries data for a vault."""
        try:
            now = int(datetime.now(tz=timezone.utc).timestamp())
            default_start = now - (90 * 24 * 60 * 60)

            options = {
                "startTimestamp": start_timestamp or default_start,
                "endTimestamp": end_timestamp or now,
                "interval": interval,
            }

            result = await self._execute(
                MorphoQueries.VAULT_TIMESERIES_QUERY,
                {
                    "address": vault_id,
                    "chainId": self._chain_id,
                    "options": options,
                },
            )

            vaults_data = result.get("vaults", {}).get("items", [])
            if not vaults_data:
                return []

            historical_data = vaults_data[0].get("historicalState")
            return self._parser.parse_vault_historical_state(historical_data)

        except Exception as e:
            logger.error(f"Failed to fetch timeseries for vault {vault_id}: {e}")
            raise

    # ========== LIFECYCLE ==========

    async def close(self) -> None:
        """Close the client connection (no-op as we create fresh connections)."""
        pass
