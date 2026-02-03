"""Aave v3 official API client implementing ProtocolClient interface.

Uses the official Aave GraphQL API at https://api.v3.aave.com/graphql
Documentation: https://aave.com/docs/aave-v3/getting-started/graphql
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from aiolimiter import AsyncLimiter
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from config.settings import Settings, get_settings
from src.core.models import (
    Market,
    Position,
    TimeseriesPoint,
)
from src.data.clients.base import ProtocolClient, ProtocolType
from src.data.clients.aave.parser import AaveParser
from src.protocols.aave.config import (
    AAVE_API_RATE_LIMIT,
    AAVE_API_RATE_WINDOW,
    AAVE_V3_API_URL,
    AAVE_V3_POOL_ADDRESS,
    ETHEREUM_MAINNET,
)
from src.protocols.aave.queries import AaveQueries

logger = logging.getLogger(__name__)


class AaveClient(ProtocolClient):
    """GraphQL client for Aave v3 official API implementing ProtocolClient interface."""

    def __init__(self, settings: Optional[Settings] = None, chain_id: int = ETHEREUM_MAINNET):
        self.settings = settings or get_settings()
        self._rate_limiter = AsyncLimiter(
            AAVE_API_RATE_LIMIT, AAVE_API_RATE_WINDOW
        )
        self._parser = AaveParser()
        self._chain_id = chain_id

    @property
    def protocol_type(self) -> ProtocolType:
        return ProtocolType.AAVE

    @property
    def protocol_name(self) -> str:
        return "Aave v3"

    @property
    def supports_vaults(self) -> bool:
        return False  # Aave doesn't have MetaMorpho-style vaults

    def _get_api_url(self) -> str:
        """Get the Aave API URL."""
        return getattr(self.settings, "aave_api_url", None) or AAVE_V3_API_URL

    async def _execute(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GraphQL query with rate limiting."""
        async with self._rate_limiter:
            transport = AIOHTTPTransport(url=self._get_api_url())
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
        """Fetch reserves from Aave v3 as Markets."""
        try:
            result = await self._execute(
                AaveQueries.MARKETS_QUERY,
                {"chainIds": [self._chain_id]},
            )

            markets = []
            for market_data in result.get("markets", []):
                market_name = market_data.get("name", "")
                chain_info = market_data.get("chain", {}) or {}
                chain_id = chain_info.get("chainId", self._chain_id)

                reserves = market_data.get("reserves", []) or []
                for reserve in reserves:
                    # Skip frozen/paused reserves
                    if reserve.get("isFrozen") or reserve.get("isPaused"):
                        continue

                    try:
                        market = self._parser.parse_reserve_to_market(
                            reserve, market_name, chain_id
                        )
                        markets.append(market)
                    except Exception as e:
                        symbol = reserve.get("underlyingToken", {}).get("symbol", "unknown")
                        logger.warning(f"Failed to parse reserve {symbol}: {e}")
                        continue

            # Apply pagination (API doesn't support skip/first natively)
            return markets[skip:skip + first]

        except Exception as e:
            logger.error(f"Failed to fetch Aave markets: {e}")
            raise

    async def get_market(self, market_id: str) -> Optional[Market]:
        """Fetch a single reserve by ID.

        Market ID format: {chain_id}-{token_address}
        """
        try:
            # Parse market_id to get chain and address
            parts = market_id.split("-", 1)
            if len(parts) != 2:
                logger.warning(f"Invalid market ID format: {market_id}")
                return None

            try:
                chain_id = int(parts[0])
            except ValueError:
                logger.warning(f"Invalid chain ID in market ID: {market_id}")
                return None

            token_address = parts[1].lower()

            result = await self._execute(
                AaveQueries.MARKETS_QUERY,
                {"chainIds": [chain_id]},
            )

            for market_data in result.get("markets", []):
                market_name = market_data.get("name", "")
                chain_info = market_data.get("chain", {}) or {}
                actual_chain_id = chain_info.get("chainId", chain_id)

                for reserve in market_data.get("reserves", []) or []:
                    token = reserve.get("underlyingToken", {}) or {}
                    if token.get("address", "").lower() == token_address:
                        return self._parser.parse_reserve_to_market(
                            reserve, market_name, actual_chain_id
                        )

            return None

        except Exception as e:
            logger.error(f"Failed to fetch Aave market {market_id}: {e}")
            raise

    def _get_time_window(self, days: Optional[int] = None) -> str:
        """Convert days to Aave TimeWindow enum value."""
        if days is None or days <= 1:
            return "LAST_DAY"
        elif days <= 7:
            return "LAST_WEEK"
        elif days <= 30:
            return "LAST_MONTH"
        elif days <= 180:
            return "LAST_SIX_MONTHS"
        else:
            return "LAST_YEAR"

    def _parse_market_id(self, market_id: str) -> tuple[int, str]:
        """Parse market ID into chain_id and token_address.

        Market ID format: {chain_id}-{token_address}
        """
        parts = market_id.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid market ID format: {market_id}")
        try:
            chain_id = int(parts[0])
        except ValueError:
            raise ValueError(f"Invalid chain ID in market ID: {market_id}")
        return chain_id, parts[1]

    def _get_pool_address(self, chain_id: int) -> str:
        """Get the Aave pool address for a chain."""
        # For now, we only support Ethereum mainnet
        if chain_id == ETHEREUM_MAINNET:
            return AAVE_V3_POOL_ADDRESS
        # Add other chain pool addresses as needed
        raise ValueError(f"Unsupported chain ID: {chain_id}")

    async def get_market_timeseries(
        self,
        market_id: str,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        interval: str = "DAY",
    ) -> List[TimeseriesPoint]:
        """Fetch historical timeseries data for a reserve.

        Uses the supplyAPYHistory and borrowAPYHistory queries.

        Args:
            market_id: Market ID in format {chain_id}-{token_address}
            start_timestamp: Not used (API uses time windows instead)
            end_timestamp: Not used
            interval: Not used (API determines granularity)

        Returns:
            List of TimeseriesPoint with historical APY data
        """
        try:
            chain_id, token_address = self._parse_market_id(market_id)
            pool_address = self._get_pool_address(chain_id)

            # Calculate days from timestamps if provided
            days = None
            if start_timestamp and end_timestamp:
                days = (end_timestamp - start_timestamp) // 86400
            elif start_timestamp:
                now = int(datetime.now(timezone.utc).timestamp())
                days = (now - start_timestamp) // 86400

            time_window = self._get_time_window(days)

            result = await self._execute(
                AaveQueries.APY_HISTORY_QUERY,
                {
                    "chainId": chain_id,
                    "market": pool_address,
                    "underlyingToken": token_address,
                    "window": time_window,
                },
            )

            supply_history = result.get("supplyAPYHistory", [])
            borrow_history = result.get("borrowAPYHistory", [])

            # Create a map of borrow APY by date for efficient lookup
            borrow_by_date: Dict[str, Decimal] = {}
            for item in borrow_history:
                date_str = item.get("date", "")
                avg_rate = item.get("avgRate", {}).get("value", "0")
                borrow_by_date[date_str] = self._parser.parse_decimal(avg_rate)

            # Build timeseries points
            points: List[TimeseriesPoint] = []
            for item in supply_history:
                date_str = item.get("date", "")
                if not date_str:
                    continue

                try:
                    # Parse ISO format datetime
                    timestamp = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    logger.warning(f"Failed to parse date: {date_str}")
                    continue

                supply_apy = self._parser.parse_decimal(
                    item.get("avgRate", {}).get("value", "0")
                )
                borrow_apy = borrow_by_date.get(date_str, Decimal("0"))

                # Calculate utilization estimate from APY ratio (rough approximation)
                # In Aave, utilization ≈ borrow_apy / (borrow_apy + spread)
                # This is a rough estimate since we don't have exact utilization history
                utilization = Decimal("0")
                if borrow_apy > 0 and supply_apy > 0:
                    # Rough estimate: utilization ≈ supply_apy / borrow_apy * some_factor
                    utilization = min(supply_apy / borrow_apy, Decimal("1"))

                points.append(TimeseriesPoint(
                    timestamp=timestamp,
                    supply_apy=supply_apy,
                    borrow_apy=borrow_apy,
                    utilization=utilization,
                    rate_at_target=None,
                ))

            # Sort by timestamp (oldest first)
            points.sort(key=lambda p: p.timestamp)

            logger.info(
                f"Fetched {len(points)} historical data points for Aave market {market_id}"
            )
            return points

        except ValueError as e:
            logger.warning(f"Invalid market ID for timeseries: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch Aave timeseries for {market_id}: {e}")
            return []

    # ========== POSITION METHODS ==========

    async def get_positions(
        self,
        user_address: str,
        first: int = 100,
    ) -> List[Position]:
        """Fetch positions for a user."""
        try:
            result = await self._execute(
                AaveQueries.USER_POSITIONS_QUERY,
                {
                    "chainIds": [self._chain_id],
                    "user": user_address.lower(),
                },
            )

            positions = []
            for market_data in result.get("markets", []):
                chain_info = market_data.get("chain", {}) or {}
                chain_id = chain_info.get("chainId", self._chain_id)

                for reserve in market_data.get("reserves", []) or []:
                    try:
                        position = self._parser.parse_user_reserve_to_position(
                            reserve, chain_id
                        )
                        if position:
                            position.user = user_address.lower()
                            positions.append(position)
                    except Exception as e:
                        logger.warning(f"Failed to parse user reserve: {e}")
                        continue

            return positions[:first]

        except Exception as e:
            logger.error(f"Failed to fetch positions for {user_address}: {e}")
            raise

    # ========== RATE METHODS ==========

    async def get_rates(self, first: int = 50) -> Dict[str, Dict[str, Decimal]]:
        """Fetch lightweight rate data for all reserves."""
        try:
            result = await self._execute(
                AaveQueries.RATES_QUERY,
                {"chainIds": [self._chain_id]},
            )

            rates = {}
            for market_data in result.get("markets", []):
                for reserve in market_data.get("reserves", []) or []:
                    token = reserve.get("underlyingToken", {}) or {}
                    address = token.get("address", "")
                    market_id = f"{self._chain_id}-{address.lower()}"

                    supply_info = reserve.get("supplyInfo", {}) or {}
                    supply_apy_data = supply_info.get("apy", {}) or {}
                    supply_apy = self._parser.parse_decimal(supply_apy_data.get("value", "0"))

                    borrow_info = reserve.get("borrowInfo") or {}
                    borrow_apy_data = borrow_info.get("apy", {}) or {}
                    borrow_apy = self._parser.parse_decimal(borrow_apy_data.get("value", "0"))

                    utilization_data = borrow_info.get("utilizationRate", {}) or {}
                    utilization = self._parser.parse_decimal(utilization_data.get("value", "0"))

                    rates[market_id] = {
                        "supply_apy": supply_apy,
                        "borrow_apy": borrow_apy,
                        "utilization": utilization,
                        "rate_at_target": Decimal("0"),
                    }

            return dict(list(rates.items())[:first])

        except Exception as e:
            logger.error(f"Failed to fetch rates: {e}")
            raise

    # ========== LIFECYCLE ==========

    async def close(self) -> None:
        """Close the client connection (no-op as we create fresh connections)."""
        pass
