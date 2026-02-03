"""Aave v3 official API response parser.

Contains all parsing logic for converting Aave v3 API responses
into domain models.

Note: The official Aave API (api.v3.aave.com) returns values already
in decimal format, so no RAY/WAD conversions are needed.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.core.models import (
    Market,
    MarketState,
    Position,
    TimeseriesPoint,
)


class AaveParser:
    """Parser for Aave v3 official API responses."""

    @staticmethod
    def parse_decimal(value: Any) -> Decimal:
        """Safely parse a value to Decimal."""
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

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
                try:
                    return datetime.fromtimestamp(int(value), tz=timezone.utc)
                except (ValueError, OSError):
                    pass
        return datetime.now(tz=timezone.utc)

    @classmethod
    def parse_reserve_to_market(
        cls,
        reserve_data: Dict[str, Any],
        market_name: str,
        chain_id: int,
    ) -> Market:
        """Parse Aave reserve data to Market model.

        Aave reserves are mapped to Markets with:
        - loan_asset = the reserve's underlying asset
        - collateral_asset = empty (Aave uses global collateral pool)
        - collateral_asset_symbol = "MULTI" to indicate any enabled collateral

        Args:
            reserve_data: Reserve data from API
            market_name: Name of the market (e.g., "AaveV3Ethereum")
            chain_id: Chain ID

        Returns:
            Market object representing the reserve
        """
        # Parse underlying token info
        token = reserve_data.get("underlyingToken", {}) or {}
        symbol = token.get("symbol", "???")
        address = token.get("address", "")
        decimals = int(token.get("decimals", 18))

        # Parse USD price
        price_usd = cls.parse_decimal(reserve_data.get("usdExchangeRate", "0"))

        # Parse supply info
        supply_info = reserve_data.get("supplyInfo", {}) or {}
        supply_apy_data = supply_info.get("apy", {}) or {}
        supply_apy = cls.parse_decimal(supply_apy_data.get("value", "0"))

        ltv_data = supply_info.get("maxLTV", {}) or {}
        max_ltv = cls.parse_decimal(ltv_data.get("value", "0"))

        liq_threshold_data = supply_info.get("liquidationThreshold", {}) or {}
        liquidation_threshold = cls.parse_decimal(liq_threshold_data.get("value", "0"))

        total_supply_data = supply_info.get("total", {}) or {}
        total_supply = cls.parse_decimal(total_supply_data.get("value", "0"))

        # Parse borrow info (may be None for non-borrowable assets)
        borrow_info = reserve_data.get("borrowInfo") or {}
        borrow_apy_data = borrow_info.get("apy", {}) or {}
        borrow_apy = cls.parse_decimal(borrow_apy_data.get("value", "0"))

        total_borrow_data = borrow_info.get("total", {}) or {}
        total_borrow_amount = total_borrow_data.get("amount", {}) or {}
        total_borrow = cls.parse_decimal(total_borrow_amount.get("value", "0"))

        utilization_data = borrow_info.get("utilizationRate", {}) or {}
        utilization = cls.parse_decimal(utilization_data.get("value", "0"))

        # Create market ID from chain + address
        market_id = f"{chain_id}-{address.lower()}"

        # Create state
        # Convert token amounts to raw units for consistency with other protocols
        decimals_multiplier = Decimal(10 ** decimals)
        state = MarketState(
            total_supply_assets=total_supply * decimals_multiplier,
            total_supply_shares=total_supply * decimals_multiplier,
            total_borrow_assets=total_borrow * decimals_multiplier,
            total_borrow_shares=total_borrow * decimals_multiplier,
            last_update=datetime.now(tz=timezone.utc),
            fee=Decimal("0"),
        )

        return Market(
            id=market_id,
            loan_asset=address,
            loan_asset_symbol=symbol,
            loan_asset_decimals=decimals,
            collateral_asset="",
            collateral_asset_symbol="MULTI",
            collateral_asset_decimals=18,
            lltv=liquidation_threshold,
            oracle="aave-oracle",
            irm="aave-irm",
            creation_timestamp=None,
            supply_apy=supply_apy,
            borrow_apy=borrow_apy,
            rate_at_target=Decimal("0"),
            loan_asset_price_usd=price_usd,
            collateral_asset_price_usd=Decimal("0"),
            state=state,
        )

    @classmethod
    def parse_user_reserve_to_position(
        cls,
        reserve_data: Dict[str, Any],
        chain_id: int,
    ) -> Optional[Position]:
        """Parse Aave user reserve to Position model.

        Args:
            reserve_data: Reserve data with userState from API
            chain_id: Chain ID

        Returns:
            Position object or None if no position
        """
        token = reserve_data.get("underlyingToken", {}) or {}
        address = token.get("address", "")
        decimals = int(token.get("decimals", 18))

        user_state = reserve_data.get("userState")
        if not user_state:
            return None

        # Parse supplied amount
        supplied = user_state.get("suppliedAmount", {}) or {}
        supplied_amount_data = supplied.get("amount", {}) or {}
        supply_assets = cls.parse_decimal(supplied_amount_data.get("value", "0"))

        # Parse borrowed amount
        borrowed = user_state.get("borrowedAmount", {}) or {}
        borrowed_amount_data = borrowed.get("amount", {}) or {}
        borrow_assets = cls.parse_decimal(borrowed_amount_data.get("value", "0"))

        # Skip if no position
        if supply_assets == 0 and borrow_assets == 0:
            return None

        # Convert to raw units
        decimals_multiplier = Decimal(10 ** decimals)
        supply_raw = supply_assets * decimals_multiplier
        borrow_raw = borrow_assets * decimals_multiplier

        # Collateral is supply if enabled
        collateral_enabled = user_state.get("collateralEnabled", False)
        collateral = supply_raw if collateral_enabled else Decimal("0")

        market_id = f"{chain_id}-{address.lower()}"

        return Position(
            market_id=market_id,
            user="",  # User address not in this response
            supply_shares=supply_raw,
            supply_assets=supply_raw,
            borrow_shares=borrow_raw,
            borrow_assets=borrow_raw,
            collateral=collateral,
            last_update=None,
        )

    @classmethod
    def parse_history_to_timeseries(
        cls, history_items: List[Dict[str, Any]]
    ) -> List[TimeseriesPoint]:
        """Parse historical data to TimeseriesPoint list.

        Note: The official Aave API doesn't provide historical rate data.
        This method is kept for interface compatibility.

        Args:
            history_items: List of history items (if available)

        Returns:
            List of TimeseriesPoint sorted by timestamp
        """
        points = []
        for item in history_items:
            timestamp = cls.parse_timestamp(item.get("timestamp"))
            supply_apy = cls.parse_decimal(item.get("supplyApy", "0"))
            borrow_apy = cls.parse_decimal(item.get("borrowApy", "0"))
            utilization = cls.parse_decimal(item.get("utilization", "0"))

            points.append(
                TimeseriesPoint(
                    timestamp=timestamp,
                    supply_apy=supply_apy,
                    borrow_apy=borrow_apy,
                    utilization=utilization,
                    rate_at_target=Decimal("0"),
                )
            )

        points.sort(key=lambda x: x.timestamp)
        return points
