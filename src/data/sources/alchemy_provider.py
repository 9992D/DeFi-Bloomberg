"""Alchemy provider for on-chain historical data."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.exceptions import Web3Exception

from config.settings import Settings, get_settings
from src.core.constants import MORPHO_BLUE_ADDRESS, WAD, SECONDS_PER_YEAR

logger = logging.getLogger(__name__)


# Morpho Blue event signatures (keccak256 hashes)
EVENT_SIGNATURES = {
    "AccrueInterest": "0x4ed4f65737775016a6c2c2062483ea227f2bb1a0f0ee9447e10a4be68a9600f8",
    "Supply": "0xedf8870433c83823eb071d3df1caa8d008f12f6440918c20d75a3602cda30fe0",
    "Withdraw": "0xa56fc0ad5702ec05ce63666221f796fb62437c32db1aa1aa075fc6484cf58fbf",
    "Borrow": "0x570954540bed6b1304a87dfe815a5eda4a648f7097a16240dcd85c9b5fd42a43",
    "Repay": "0x52acb05cebbd3cd39715469f22afbf5a17496295ef3bc9bb5944056c63ccaa09",
}


@dataclass
class MarketEvent:
    """Represents a Morpho Blue market event."""
    event_type: str
    market_id: str
    block_number: int
    timestamp: datetime
    transaction_hash: str

    # Event-specific data
    assets: Optional[Decimal] = None
    shares: Optional[Decimal] = None
    borrow_rate: Optional[Decimal] = None  # For AccrueInterest
    interest: Optional[Decimal] = None  # For AccrueInterest


@dataclass
class HistoricalDataPoint:
    """A single historical data point for charts."""
    timestamp: datetime
    block_number: int
    supply_assets: Decimal
    borrow_assets: Decimal
    borrow_rate: Decimal  # Per-second rate
    utilization: Decimal

    @property
    def borrow_apy(self) -> Decimal:
        """Convert per-second rate to APY."""
        if self.borrow_rate == 0:
            return Decimal("0")
        # APY = (1 + rate_per_second)^seconds_per_year - 1
        # Approximation: rate_per_second * seconds_per_year
        return self.borrow_rate * Decimal(str(SECONDS_PER_YEAR))

    @property
    def supply_apy(self) -> Decimal:
        """Estimate supply APY from borrow APY and utilization."""
        if self.utilization == 0:
            return Decimal("0")
        return self.borrow_apy * self.utilization


class AlchemyProvider:
    """Provider for fetching on-chain historical data via Alchemy."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._web3: Optional[AsyncWeb3] = None

    async def _get_web3(self) -> AsyncWeb3:
        """Get or create Web3 instance."""
        if self._web3 is None:
            rpc_url = self.settings.alchemy_rpc_url
            if not rpc_url:
                raise ValueError("Alchemy RPC URL not configured. Set ETH_ALCHEMY_API_KEY in .env")
            self._web3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        return self._web3

    async def get_current_block(self) -> int:
        """Get the current block number."""
        web3 = await self._get_web3()
        return await web3.eth.block_number

    async def get_block_timestamp(self, block_number: int) -> datetime:
        """Get timestamp for a block."""
        web3 = await self._get_web3()
        block = await web3.eth.get_block(block_number)
        return datetime.fromtimestamp(block['timestamp'], tz=timezone.utc)

    async def get_market_events(
        self,
        market_id: str,
        from_block: int,
        to_block: int,
        event_types: Optional[List[str]] = None,
    ) -> List[MarketEvent]:
        """
        Fetch Morpho Blue events for a specific market.

        Args:
            market_id: The market unique key (bytes32 as hex string)
            from_block: Starting block number
            to_block: Ending block number
            event_types: List of event types to fetch (default: all)

        Returns:
            List of MarketEvent objects sorted by block number
        """
        web3 = await self._get_web3()

        if event_types is None:
            event_types = list(EVENT_SIGNATURES.keys())

        # Ensure market_id is properly formatted (32 bytes hex = 66 chars with 0x)
        if not market_id.startswith("0x"):
            market_id = "0x" + market_id
        # Pad to 32 bytes if needed
        market_id_clean = market_id[2:].lower()  # Remove 0x
        market_id_padded = "0x" + market_id_clean.zfill(64)

        events = []

        for event_type in event_types:
            if event_type not in EVENT_SIGNATURES:
                continue

            topic0 = EVENT_SIGNATURES[event_type]

            try:
                # Build filter with hex block numbers
                filter_params = {
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    "address": web3.to_checksum_address(MORPHO_BLUE_ADDRESS),
                    "topics": [topic0, market_id_padded],
                }

                logs = await web3.eth.get_logs(filter_params)

                for log in logs:
                    event = await self._parse_event(log, event_type, web3)
                    if event:
                        events.append(event)

            except Web3Exception as e:
                logger.warning(f"Error fetching {event_type} events: {e}")
                continue

        # Sort by block number
        events.sort(key=lambda e: e.block_number)
        return events

    async def _parse_event(
        self,
        log: Dict[str, Any],
        event_type: str,
        web3: AsyncWeb3,
    ) -> Optional[MarketEvent]:
        """Parse a raw log into a MarketEvent."""
        try:
            block_number = log['blockNumber']

            # Get block timestamp
            block = await web3.eth.get_block(block_number)
            timestamp = datetime.fromtimestamp(block['timestamp'], tz=timezone.utc)

            # Extract market_id from topics[1]
            market_id = log['topics'][1].hex() if len(log['topics']) > 1 else ""

            event = MarketEvent(
                event_type=event_type,
                market_id=market_id,
                block_number=block_number,
                timestamp=timestamp,
                transaction_hash=log['transactionHash'].hex(),
            )

            # Parse event-specific data from log data
            data = log['data']
            if isinstance(data, bytes):
                data = data.hex()
            if data.startswith("0x"):
                data = data[2:]

            if event_type == "AccrueInterest" and len(data) >= 192:
                # AccrueInterest(bytes32 id, uint256 prevBorrowRate, uint256 interest, uint256 feeShares)
                # Data: prevBorrowRate (32 bytes) + interest (32 bytes) + feeShares (32 bytes)
                event.borrow_rate = Decimal(int(data[0:64], 16)) / Decimal(WAD)
                event.interest = Decimal(int(data[64:128], 16))

            elif event_type in ["Supply", "Withdraw", "Borrow", "Repay"] and len(data) >= 128:
                # These events have: assets (32 bytes) + shares (32 bytes)
                event.assets = Decimal(int(data[0:64], 16))
                event.shares = Decimal(int(data[64:128], 16))

            return event

        except Exception as e:
            logger.debug(f"Error parsing event: {e}")
            return None

    async def get_historical_data(
        self,
        market_id: str,
        days: int = 30,
        resolution_blocks: int = 7200,  # ~1 day at 12s/block
    ) -> List[HistoricalDataPoint]:
        """
        Get historical data points for a market by sampling AccrueInterest events.

        Args:
            market_id: Market unique key
            days: Number of days of history
            resolution_blocks: Block interval for sampling

        Returns:
            List of HistoricalDataPoint objects
        """
        web3 = await self._get_web3()

        current_block = await web3.eth.block_number
        blocks_per_day = 7200  # ~12 seconds per block
        from_block = current_block - (days * blocks_per_day)

        # Fetch AccrueInterest events
        events = await self.get_market_events(
            market_id=market_id,
            from_block=from_block,
            to_block=current_block,
            event_types=["AccrueInterest"],
        )

        if not events:
            return []

        # Sample events at regular intervals
        data_points = []
        last_block = 0

        for event in events:
            # Skip if too close to last point
            if event.block_number - last_block < resolution_blocks:
                continue

            if event.borrow_rate is not None:
                point = HistoricalDataPoint(
                    timestamp=event.timestamp,
                    block_number=event.block_number,
                    supply_assets=Decimal("0"),  # Would need to query state
                    borrow_assets=Decimal("0"),  # Would need to query state
                    borrow_rate=event.borrow_rate,
                    utilization=Decimal("0.9"),  # Estimate
                )
                data_points.append(point)
                last_block = event.block_number

        return data_points

    async def get_detailed_history(
        self,
        market_id: str,
        from_block: int,
        to_block: int,
    ) -> Dict[str, List[Dict]]:
        """
        Get detailed event history for a market.

        Returns a dict with event counts and timeseries for each type.
        """
        events = await self.get_market_events(
            market_id=market_id,
            from_block=from_block,
            to_block=to_block,
        )

        # Group by event type
        grouped = {
            "AccrueInterest": [],
            "Supply": [],
            "Withdraw": [],
            "Borrow": [],
            "Repay": [],
        }

        for event in events:
            if event.event_type in grouped:
                grouped[event.event_type].append({
                    "timestamp": event.timestamp,
                    "block": event.block_number,
                    "assets": float(event.assets) if event.assets else None,
                    "borrow_rate": float(event.borrow_rate) if event.borrow_rate else None,
                })

        return grouped

    async def close(self):
        """Close the provider."""
        self._web3 = None
