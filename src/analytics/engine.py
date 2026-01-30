"""Analytics engine orchestrator."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Type

from src.core.models import Market, TimeseriesPoint, KPIResult, KPIType, MarketKPIs
from src.data.pipeline import DataPipeline
from src.analytics.kpis import (
    BaseKPICalculator,
    VolatilityCalculator,
    SharpeCalculator,
    SortinoCalculator,
    ElasticityCalculator,
    IRMEvolutionCalculator,
    MeanReversionCalculator,
    UtilAdjustedReturnCalculator,
)

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """
    Orchestrates KPI calculations for markets.

    Manages data fetching, calculator registration, and result aggregation.
    """

    # Default calculators
    DEFAULT_CALCULATORS: List[Type[BaseKPICalculator]] = [
        VolatilityCalculator,
        SharpeCalculator,
        SortinoCalculator,
        ElasticityCalculator,
        IRMEvolutionCalculator,
        MeanReversionCalculator,
        UtilAdjustedReturnCalculator,
    ]

    def __init__(
        self,
        pipeline: Optional[DataPipeline] = None,
        calculators: Optional[List[BaseKPICalculator]] = None,
    ):
        self.pipeline = pipeline or DataPipeline()
        self._calculators: Dict[KPIType, BaseKPICalculator] = {}

        # Register calculators
        if calculators:
            for calc in calculators:
                self.register_calculator(calc)
        else:
            # Use default calculators
            for calc_class in self.DEFAULT_CALCULATORS:
                self.register_calculator(calc_class())

    def register_calculator(self, calculator: BaseKPICalculator) -> None:
        """Register a KPI calculator."""
        self._calculators[calculator.kpi_type] = calculator
        logger.debug(f"Registered calculator: {calculator.kpi_type.value}")

    def unregister_calculator(self, kpi_type: KPIType) -> None:
        """Unregister a KPI calculator."""
        if kpi_type in self._calculators:
            del self._calculators[kpi_type]

    @property
    def available_kpis(self) -> List[KPIType]:
        """List of available KPI types."""
        return list(self._calculators.keys())

    async def calculate_market_kpis(
        self,
        market: Market,
        timeseries: Optional[List[TimeseriesPoint]] = None,
        kpi_types: Optional[List[KPIType]] = None,
        timeseries_hours: Optional[int] = None,
    ) -> MarketKPIs:
        """
        Calculate KPIs for a single market.

        Args:
            market: Market object
            timeseries: Pre-fetched timeseries (optional)
            kpi_types: Specific KPIs to calculate (None = all)
            timeseries_hours: Hours of data (None = all available)

        Returns:
            MarketKPIs with all calculated results
        """
        # Use market's embedded timeseries if available
        if timeseries is None and market.timeseries:
            timeseries = market.timeseries

        # Fetch timeseries if still not available
        if timeseries is None:
            timeseries = await self.pipeline.get_market_timeseries(
                market.id, hours=timeseries_hours
            )

        # Determine which KPIs to calculate
        types_to_calc = kpi_types or list(self._calculators.keys())

        # Calculate each KPI
        market_kpis = MarketKPIs(market_id=market.id)

        for kpi_type in types_to_calc:
            if kpi_type not in self._calculators:
                continue

            calculator = self._calculators[kpi_type]

            try:
                result = calculator.calculate(market, timeseries)
                market_kpis.add(result)
            except Exception as e:
                logger.error(f"Error calculating {kpi_type.value} for {market.id}: {e}")
                market_kpis.add(
                    KPIResult(
                        kpi_type=kpi_type,
                        market_id=market.id,
                        value=None,
                        status=KPIResult.KPIStatus.ERROR if hasattr(KPIResult, 'KPIStatus') else 2,
                        error_message=str(e),
                    )
                )

        return market_kpis

    async def calculate_all_kpis(
        self,
        markets: Optional[List[Market]] = None,
        kpi_types: Optional[List[KPIType]] = None,
        timeseries_hours: int = 168,
        max_concurrent: int = 5,
    ) -> Dict[str, MarketKPIs]:
        """
        Calculate KPIs for multiple markets.

        Args:
            markets: List of markets (None = fetch from pipeline)
            kpi_types: Specific KPIs to calculate (None = all)
            timeseries_hours: Hours of timeseries data to fetch
            max_concurrent: Maximum concurrent calculations

        Returns:
            Dict mapping market_id to MarketKPIs
        """
        # Fetch markets if not provided
        if markets is None:
            markets = await self.pipeline.get_markets()

        results: Dict[str, MarketKPIs] = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def calc_with_semaphore(market: Market) -> tuple:
            async with semaphore:
                kpis = await self.calculate_market_kpis(
                    market,
                    kpi_types=kpi_types,
                    timeseries_hours=timeseries_hours,
                )
                return market.id, kpis

        # Calculate all in parallel with concurrency limit
        tasks = [calc_with_semaphore(m) for m in markets]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Error in batch calculation: {result}")
                continue
            market_id, kpis = result
            results[market_id] = kpis

        return results

    async def get_market_summary(
        self,
        market_id: str,
        timeseries_hours: int = 168,
    ) -> Dict:
        """
        Get a comprehensive summary for a market.

        Args:
            market_id: Market unique key
            timeseries_hours: Hours of data for analysis

        Returns:
            Dict with market info and KPIs
        """
        # Fetch market
        market = await self.pipeline.get_market(market_id)
        if not market:
            return {"error": f"Market {market_id} not found"}

        # Calculate KPIs
        kpis = await self.calculate_market_kpis(
            market, timeseries_hours=timeseries_hours
        )

        return {
            "market": {
                "id": market.id,
                "name": market.name,
                "loan_asset": market.loan_asset_symbol,
                "collateral_asset": market.collateral_asset_symbol,
                "lltv": str(market.lltv),
                "supply_apy": str(market.supply_apy),
                "borrow_apy": str(market.borrow_apy),
                "utilization": str(market.utilization),
            },
            "kpis": {
                kpi_type.value: {
                    "value": result.display_value,
                    "signal": result.signal,
                    "metadata": result.metadata,
                }
                for kpi_type, result in kpis.kpis.items()
            },
            "calculated_at": datetime.utcnow().isoformat(),
        }

    def calculate_sync(
        self,
        market: Market,
        timeseries: List[TimeseriesPoint],
        kpi_type: KPIType,
    ) -> KPIResult:
        """
        Synchronous single KPI calculation (for testing/debugging).

        Args:
            market: Market object
            timeseries: Historical data
            kpi_type: KPI to calculate

        Returns:
            KPIResult
        """
        if kpi_type not in self._calculators:
            raise ValueError(f"No calculator registered for {kpi_type}")

        return self._calculators[kpi_type].calculate(market, timeseries)

    async def close(self):
        """Close the engine and underlying resources."""
        await self.pipeline.close()
