"""Data aggregator for unified access to all protocol pipelines."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from src.data.pipeline import DataPipeline
from src.core.models import Market, TimeseriesPoint

logger = logging.getLogger(__name__)


@dataclass
class PricePoint:
    """A price data point."""
    timestamp: datetime
    price: Decimal              # Price in quote asset
    source: str = "oracle"      # "oracle", "market", "external"


@dataclass
class MarketSnapshot:
    """Complete market state at a point in time."""
    timestamp: datetime
    market_id: str

    # Prices
    collateral_price: Decimal   # Collateral/loan price from oracle
    loan_asset_price_usd: Decimal
    collateral_asset_price_usd: Decimal

    # Rates
    supply_apy: Decimal
    borrow_apy: Decimal
    utilization: Decimal

    # Market params
    lltv: Decimal

    @property
    def collateral_loan_ratio(self) -> Decimal:
        """Collateral price in loan asset terms."""
        if self.loan_asset_price_usd == 0:
            return Decimal("1")
        return self.collateral_asset_price_usd / self.loan_asset_price_usd


class DataAggregator:
    """
    Unified interface to all protocol data pipelines.

    Provides consistent access to market data, prices, and timeseries
    across different protocols (currently Morpho, extensible to others).
    """

    def __init__(self, pipelines: Optional[Dict[str, DataPipeline]] = None):
        """
        Initialize with protocol pipelines.

        Args:
            pipelines: Dict mapping protocol name to DataPipeline
                      e.g., {"morpho": MorphoDataPipeline()}
        """
        self.pipelines = pipelines or {}
        self._market_cache: Dict[str, Market] = {}

    def add_pipeline(self, protocol: str, pipeline: DataPipeline) -> None:
        """Add a protocol pipeline."""
        self.pipelines[protocol] = pipeline

    def get_pipeline(self, protocol: str) -> DataPipeline:
        """Get pipeline for a protocol."""
        if protocol not in self.pipelines:
            raise ValueError(f"Unknown protocol: {protocol}")
        return self.pipelines[protocol]

    async def get_market(
        self,
        protocol: str,
        market_id: str,
        use_cache: bool = True
    ) -> Optional[Market]:
        """
        Get market details.

        Args:
            protocol: Protocol name (e.g., "morpho")
            market_id: Market identifier
            use_cache: Whether to use cached data

        Returns:
            Market object or None
        """
        cache_key = f"{protocol}:{market_id}"

        if use_cache and cache_key in self._market_cache:
            return self._market_cache[cache_key]

        pipeline = self.get_pipeline(protocol)
        market = await pipeline.get_market(market_id)

        if market:
            self._market_cache[cache_key] = market

        return market

    async def get_markets(
        self,
        protocol: str,
        first: int = 100
    ) -> List[Market]:
        """Get all markets for a protocol."""
        pipeline = self.get_pipeline(protocol)
        return await pipeline.get_markets(first=first)

    async def get_market_timeseries(
        self,
        protocol: str,
        market_id: str,
        interval: str = "HOUR",
        days: int = 90,
    ) -> List[TimeseriesPoint]:
        """
        Get market timeseries data.

        Args:
            protocol: Protocol name
            market_id: Market identifier
            interval: Data interval (HOUR, DAY, WEEK)
            days: Number of days to fetch

        Returns:
            List of TimeseriesPoint
        """
        pipeline = self.get_pipeline(protocol)

        return await pipeline.get_market_timeseries(
            market_id=market_id,
            days=days,
            interval=interval,
        )

    async def get_market_snapshots(
        self,
        protocol: str,
        market_id: str,
        interval: str = "HOUR",
        days: int = 90,
    ) -> List[MarketSnapshot]:
        """
        Get market snapshots with full state over time.

        This combines market info with timeseries data to provide
        complete snapshots for simulation.

        Args:
            protocol: Protocol name
            market_id: Market identifier
            interval: Data interval
            days: Number of days

        Returns:
            List of MarketSnapshot
        """
        # Get market details
        market = await self.get_market(protocol, market_id)
        if not market:
            raise ValueError(f"Market not found: {market_id}")

        # Get timeseries
        timeseries = await self.get_market_timeseries(
            protocol=protocol,
            market_id=market_id,
            interval=interval,
            days=days,
        )

        # Get current collateral/loan price ratio
        current_price = Decimal("1")
        if market.loan_asset_price_usd > 0:
            current_price = market.collateral_asset_price_usd / market.loan_asset_price_usd

        # For yield-bearing collateral (wstETH), simulate historical prices
        # by working backwards from current price using cumulative yield
        # wstETH appreciates vs ETH at roughly the staking APY rate
        snapshots = []
        now = datetime.now(tz=timezone.utc)

        for point in timeseries:
            # Calculate days from this point to now
            days_to_now = (now - point.timestamp).total_seconds() / (24 * 3600)

            # Reconstruct historical price using supply APY as yield proxy
            # For wstETH/ETH: price_historical = price_now / (1 + yield)^(days/365)
            # Use average yield of ~3% if APY is 0 or missing
            yield_rate = float(point.supply_apy) if point.supply_apy > 0 else 0.03

            if days_to_now > 0:
                # Discount current price back to historical price
                discount_factor = Decimal(str((1 + yield_rate) ** (days_to_now / 365)))
                historical_price = current_price / discount_factor
            else:
                historical_price = current_price

            snapshot = MarketSnapshot(
                timestamp=point.timestamp,
                market_id=market_id,
                collateral_price=historical_price,
                loan_asset_price_usd=market.loan_asset_price_usd,
                collateral_asset_price_usd=market.collateral_asset_price_usd,
                supply_apy=point.supply_apy,
                borrow_apy=point.borrow_apy,
                utilization=point.utilization,
                lltv=market.lltv,
            )
            snapshots.append(snapshot)

        return snapshots

    async def get_price_history(
        self,
        protocol: str,
        market_id: str,
        interval: str = "HOUR",
        days: int = 90,
    ) -> List[PricePoint]:
        """
        Get collateral/loan price history for a market.

        For wstETH/ETH, this returns wstETH price in ETH terms over time.

        Note: Currently approximated from yield data since Morpho API
        doesn't provide historical oracle prices. For wstETH/ETH,
        we can derive the price evolution from the yield differential.

        Args:
            protocol: Protocol name
            market_id: Market identifier
            interval: Data interval
            days: Number of days

        Returns:
            List of PricePoint
        """
        market = await self.get_market(protocol, market_id)
        if not market:
            return []

        timeseries = await self.get_market_timeseries(
            protocol=protocol,
            market_id=market_id,
            interval=interval,
            days=days,
        )

        # Get current price as baseline
        current_price = Decimal("1")
        if market.loan_asset_price_usd > 0:
            current_price = market.collateral_asset_price_usd / market.loan_asset_price_usd

        # For wstETH/ETH, reconstruct historical prices from yield
        # wstETH accrues value vs ETH based on staking yield
        # price_t = price_current / (1 + yield_rate)^(days_from_t_to_now / 365)
        prices = []

        if not timeseries:
            return prices

        # Calculate backwards from current price using cumulative yield
        latest_ts = timeseries[-1].timestamp
        now = datetime.now(tz=timezone.utc)

        for point in timeseries:
            # Days from this point to now
            days_diff = (now - point.timestamp).total_seconds() / (24 * 3600)

            # Approximate yield rate at this point (supply - borrow spread)
            # For wstETH/ETH, supply_apy reflects wstETH staking yield
            yield_rate = float(point.supply_apy)

            # Reconstruct historical price
            # price_t = price_now / (1 + r)^(days/365)
            if yield_rate > 0 and days_diff > 0:
                historical_price = current_price / Decimal(str(
                    (1 + yield_rate) ** (days_diff / 365)
                ))
            else:
                historical_price = current_price

            prices.append(PricePoint(
                timestamp=point.timestamp,
                price=historical_price,
                source="derived",
            ))

        return prices

    async def find_markets_by_pair(
        self,
        protocol: str,
        collateral_symbol: str,
        loan_symbol: str,
    ) -> List[Market]:
        """
        Find markets matching a trading pair.

        Args:
            protocol: Protocol name
            collateral_symbol: Collateral asset symbol (e.g., "wstETH")
            loan_symbol: Loan asset symbol (e.g., "WETH", "ETH")

        Returns:
            List of matching markets
        """
        markets = await self.get_markets(protocol, first=500)

        matches = []
        for m in markets:
            collat_match = collateral_symbol.lower() in m.collateral_asset_symbol.lower()
            loan_match = loan_symbol.lower() in m.loan_asset_symbol.lower()

            if collat_match and loan_match:
                matches.append(m)

        # Sort by TVL
        matches.sort(key=lambda m: m.tvl, reverse=True)
        return matches

    def clear_cache(self) -> None:
        """Clear market cache."""
        self._market_cache.clear()
