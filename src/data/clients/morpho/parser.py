"""Morpho API response parser.

Contains all parsing logic for converting Morpho GraphQL API responses
into domain models.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

from src.core.constants import WAD, SECONDS_PER_YEAR
from src.core.models import (
    Market,
    MarketState,
    Position,
    TimeseriesPoint,
    Vault,
    VaultState,
    VaultAllocation,
    VaultTimeseriesPoint,
)


class MorphoParser:
    """Parser for Morpho GraphQL API responses."""

    @staticmethod
    def parse_decimal(value: Any) -> Decimal:
        """Safely parse a value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def parse_rate_at_target(value: Any) -> Decimal:
        """Convert rateAtTarget from on-chain format to annual rate.

        On-chain format: per-second rate in WAD (1e18)
        Output: annual rate as decimal (e.g., 0.04 = 4% APR)
        """
        if value is None:
            return Decimal("0")
        raw = MorphoParser.parse_decimal(value)
        if raw == 0:
            return Decimal("0")
        # Convert: rate_per_second * seconds_per_year / WAD
        annual_rate = raw * Decimal(str(SECONDS_PER_YEAR)) / Decimal(str(WAD))
        return annual_rate

    @staticmethod
    def parse_wad(value: Any) -> Decimal:
        """Convert a WAD value (1e18 scaled) to decimal.

        On-chain format: value * 1e18 (e.g., 0.86 = 860000000000000000)
        Output: decimal (e.g., 0.86)
        """
        if value is None:
            return Decimal("0")
        raw = MorphoParser.parse_decimal(value)
        if raw == 0:
            return Decimal("0")
        return raw / Decimal(str(WAD))

    @staticmethod
    def parse_timestamp(value: Any) -> datetime:
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

    @classmethod
    def parse_market(cls, data: Dict[str, Any]) -> Market:
        """Parse market data from API response."""
        loan_asset = data.get("loanAsset", {}) or {}
        collateral_asset = data.get("collateralAsset", {}) or {}
        state_data = data.get("state", {}) or {}

        state = None
        if state_data:
            state = MarketState(
                total_supply_assets=cls.parse_decimal(state_data.get("supplyAssets")),
                total_supply_shares=cls.parse_decimal(state_data.get("supplyShares")),
                total_borrow_assets=cls.parse_decimal(state_data.get("borrowAssets")),
                total_borrow_shares=cls.parse_decimal(state_data.get("borrowShares")),
                last_update=cls.parse_timestamp(state_data.get("timestamp")),
                fee=cls.parse_decimal(state_data.get("fee")),
            )

        # Parse creation timestamp if available
        creation_ts = data.get("creationTimestamp")
        creation_timestamp = cls.parse_timestamp(creation_ts) if creation_ts else None

        return Market(
            id=data.get("uniqueKey", data.get("id", "")),
            loan_asset=loan_asset.get("address", ""),
            loan_asset_symbol=loan_asset.get("symbol", "???"),
            loan_asset_decimals=int(loan_asset.get("decimals", 18)),
            collateral_asset=collateral_asset.get("address", ""),
            collateral_asset_symbol=collateral_asset.get("symbol", "???"),
            collateral_asset_decimals=int(collateral_asset.get("decimals", 18)),
            lltv=cls.parse_wad(data.get("lltv")),
            oracle=data.get("oracleAddress", ""),
            irm=data.get("irmAddress", ""),
            creation_timestamp=creation_timestamp,
            supply_apy=cls.parse_decimal(state_data.get("supplyApy")),
            borrow_apy=cls.parse_decimal(state_data.get("borrowApy")),
            rate_at_target=cls.parse_rate_at_target(state_data.get("rateAtTarget")),
            loan_asset_price_usd=cls.parse_decimal(loan_asset.get("priceUsd")),
            collateral_asset_price_usd=cls.parse_decimal(collateral_asset.get("priceUsd")),
            state=state,
        )

    @classmethod
    def parse_position(cls, data: Dict[str, Any]) -> Position:
        """Parse position data from API response."""
        market_data = data.get("market", {}) or {}
        user_data = data.get("user", {}) or {}
        state_data = data.get("state", {}) or {}

        return Position(
            market_id=market_data.get("uniqueKey", ""),
            user=user_data.get("address", ""),
            supply_shares=cls.parse_decimal(state_data.get("supplyShares")),
            supply_assets=cls.parse_decimal(state_data.get("supplyAssets")),
            borrow_shares=cls.parse_decimal(state_data.get("borrowShares")),
            borrow_assets=cls.parse_decimal(state_data.get("borrowAssets")),
            collateral=cls.parse_decimal(state_data.get("collateral")),
            last_update=cls.parse_timestamp(state_data.get("timestamp")) if state_data.get("timestamp") else None,
        )

    @classmethod
    def parse_historical_state(cls, historical_data: Dict[str, Any]) -> List[TimeseriesPoint]:
        """Parse historical state data from API response.

        The API returns data in format:
        {
            "supplyApy": [{"x": timestamp, "y": value}, ...],
            "borrowApy": [{"x": timestamp, "y": value}, ...],
            "utilization": [{"x": timestamp, "y": value}, ...],
            "rateAtTarget": [{"x": timestamp, "y": value}, ...]
        }

        We merge these into TimeseriesPoint objects by timestamp.
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
                timestamp=cls.parse_timestamp(ts),
                supply_apy=cls.parse_decimal(data.get("supply_apy")),
                borrow_apy=cls.parse_decimal(data.get("borrow_apy")),
                utilization=cls.parse_decimal(data.get("utilization")),
                rate_at_target=cls.parse_rate_at_target(data.get("rate_at_target")),
            ))

        # Sort by timestamp
        points.sort(key=lambda x: x.timestamp)
        return points

    @classmethod
    def parse_vault_allocation(cls, data: Dict[str, Any]) -> VaultAllocation:
        """Parse vault allocation data."""
        market_data = data.get("market", {}) or {}
        loan_asset = market_data.get("loanAsset", {}) or {}
        collateral_asset = market_data.get("collateralAsset", {}) or {}

        return VaultAllocation(
            market_id=market_data.get("uniqueKey", ""),
            loan_asset_symbol=loan_asset.get("symbol", "???"),
            collateral_asset_symbol=collateral_asset.get("symbol") if collateral_asset else None,
            lltv=cls.parse_wad(market_data.get("lltv")),
            supply_assets=cls.parse_decimal(data.get("supplyAssets")),
            supply_assets_usd=cls.parse_decimal(data.get("supplyAssetsUsd")),
            supply_shares=cls.parse_decimal(data.get("supplyShares")),
        )

    @classmethod
    def parse_vault(cls, data: Dict[str, Any]) -> Vault:
        """Parse vault data from API response."""
        asset = data.get("asset", {}) or {}
        state_data = data.get("state", {}) or {}

        state = None
        if state_data:
            allocations = []
            for alloc_data in state_data.get("allocation", []) or []:
                allocations.append(cls.parse_vault_allocation(alloc_data))

            state = VaultState(
                total_assets=cls.parse_decimal(state_data.get("totalAssets")),
                total_assets_usd=cls.parse_decimal(state_data.get("totalAssetsUsd")),
                total_supply=cls.parse_decimal(state_data.get("totalSupply")),
                fee=cls.parse_decimal(state_data.get("fee")),
                share_price=cls.parse_decimal(state_data.get("sharePriceNumber")),
                share_price_usd=cls.parse_decimal(state_data.get("sharePriceUsd")),
                last_update=cls.parse_timestamp(state_data.get("timestamp")),
                allocation=allocations,
            )

        # Parse creation timestamp if available
        creation_ts = data.get("creationTimestamp")
        creation_timestamp = cls.parse_timestamp(creation_ts) if creation_ts else None

        return Vault(
            id=data.get("address", ""),
            name=data.get("name", ""),
            symbol=data.get("symbol", ""),
            asset_address=asset.get("address", ""),
            asset_symbol=asset.get("symbol", "???"),
            asset_decimals=int(asset.get("decimals", 18)),
            asset_price_usd=cls.parse_decimal(asset.get("priceUsd")),
            apy=cls.parse_decimal(state_data.get("apy")),
            net_apy=cls.parse_decimal(state_data.get("netApy")),
            creation_timestamp=creation_timestamp,
            state=state,
        )

    @classmethod
    def parse_vault_historical_state(cls, historical_data: Dict[str, Any]) -> List[VaultTimeseriesPoint]:
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
                timestamp=cls.parse_timestamp(ts),
                apy=cls.parse_decimal(data.get("apy")),
                net_apy=cls.parse_decimal(data.get("net_apy")),
                total_assets=cls.parse_decimal(data.get("total_assets")),
                share_price=cls.parse_decimal(data.get("share_price")) if data.get("share_price") else None,
            ))

        points.sort(key=lambda x: x.timestamp)
        return points
