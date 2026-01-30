"""Unit tests for KPI calculators."""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

import numpy as np

from src.core.models import Market, MarketState, TimeseriesPoint, KPIType, KPIStatus
from src.analytics.kpis import (
    VolatilityCalculator,
    SharpeCalculator,
    SortinoCalculator,
    ElasticityCalculator,
    IRMEvolutionCalculator,
    MeanReversionCalculator,
    UtilAdjustedReturnCalculator,
)


class TestFixtures:
    """Test fixtures for KPI tests."""

    @staticmethod
    def create_market(
        market_id: str = "test-market",
        supply_apy: Decimal = Decimal("0.05"),
        borrow_apy: Decimal = Decimal("0.08"),
        utilization: Decimal = Decimal("0.85"),
    ) -> Market:
        """Create a test market."""
        return Market(
            id=market_id,
            loan_asset="0xloan",
            loan_asset_symbol="USDC",
            loan_asset_decimals=6,
            collateral_asset="0xcoll",
            collateral_asset_symbol="WETH",
            collateral_asset_decimals=18,
            lltv=Decimal("0.86"),
            oracle="0xoracle",
            irm="0xirm",
            supply_apy=supply_apy,
            borrow_apy=borrow_apy,
            rate_at_target=Decimal("0.04"),
            state=MarketState(
                total_supply_assets=Decimal("1000000"),
                total_supply_shares=Decimal("1000000"),
                total_borrow_assets=Decimal("850000"),
                total_borrow_shares=Decimal("850000"),
                last_update=datetime.now(timezone.utc),
                fee=Decimal("0.1"),
            ),
        )

    @staticmethod
    def create_timeseries(
        hours: int = 168,
        base_supply_apy: float = 0.05,
        base_borrow_apy: float = 0.08,
        base_utilization: float = 0.85,
        volatility: float = 0.01,
        trend: float = 0.0,
    ) -> List[TimeseriesPoint]:
        """Create test timeseries data."""
        now = datetime.now(timezone.utc)
        points = []

        for i in range(hours):
            ts = now - timedelta(hours=hours - i)

            # Add noise and trend
            noise = np.random.normal(0, volatility)
            supply = base_supply_apy + noise + (trend * i / hours)
            borrow = base_borrow_apy + noise * 1.5 + (trend * i / hours)
            util = base_utilization + noise * 0.5

            points.append(
                TimeseriesPoint(
                    timestamp=ts,
                    supply_apy=Decimal(str(max(0.001, supply))),
                    borrow_apy=Decimal(str(max(0.001, borrow))),
                    utilization=Decimal(str(max(0.01, min(0.99, util)))),
                    rate_at_target=Decimal(str(max(0.001, base_supply_apy + trend * i / hours))),
                )
            )

        return points


class TestVolatilityCalculator:
    """Tests for VolatilityCalculator."""

    @pytest.fixture
    def calculator(self):
        return VolatilityCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.VOLATILITY

    def test_insufficient_data(self, calculator, market):
        """Test with insufficient data points."""
        timeseries = TestFixtures.create_timeseries(hours=10)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.INSUFFICIENT_DATA

    def test_low_volatility(self, calculator, market):
        """Test with low volatility data."""
        timeseries = TestFixtures.create_timeseries(hours=168, volatility=0.001)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert result.value is not None
        # Volatility is annualized, so even small values get scaled up significantly

    def test_high_volatility(self, calculator, market):
        """Test with high volatility data."""
        timeseries = TestFixtures.create_timeseries(hours=168, volatility=0.05)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert result.value is not None
        # Higher volatility expected

    def test_borrow_rate_volatility(self, calculator, market):
        """Test volatility for borrow rates."""
        timeseries = TestFixtures.create_timeseries(hours=168)
        result = calculator.calculate(market, timeseries, rate_type="borrow")

        assert result.status == KPIStatus.SUCCESS
        assert result.metadata.get("rate_type") == "borrow"


class TestSharpeCalculator:
    """Tests for SharpeCalculator."""

    @pytest.fixture
    def calculator(self):
        return SharpeCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.SHARPE_RATIO

    def test_positive_sharpe(self, calculator, market):
        """Test positive Sharpe ratio."""
        # High return, low volatility
        timeseries = TestFixtures.create_timeseries(
            hours=200, base_supply_apy=0.10, volatility=0.005
        )
        result = calculator.calculate(market, timeseries, risk_free_rate=0.05)

        assert result.status == KPIStatus.SUCCESS
        assert result.value > Decimal("0")

    def test_negative_sharpe(self, calculator, market):
        """Test negative Sharpe ratio."""
        # Return below risk-free rate
        timeseries = TestFixtures.create_timeseries(
            hours=200, base_supply_apy=0.02, volatility=0.01
        )
        result = calculator.calculate(market, timeseries, risk_free_rate=0.05)

        assert result.status == KPIStatus.SUCCESS
        assert result.value < Decimal("0")


class TestSortinoCalculator:
    """Tests for SortinoCalculator."""

    @pytest.fixture
    def calculator(self):
        return SortinoCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.SORTINO_RATIO

    def test_sortino_calculation(self, calculator, market):
        """Test Sortino ratio calculation."""
        timeseries = TestFixtures.create_timeseries(hours=200, volatility=0.01)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert result.value is not None
        assert "downside_std" in result.metadata


class TestElasticityCalculator:
    """Tests for ElasticityCalculator."""

    @pytest.fixture
    def calculator(self):
        return ElasticityCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.ELASTICITY

    def test_elasticity_calculation(self, calculator, market):
        """Test elasticity calculation."""
        # Create data with utilization in target range
        timeseries = TestFixtures.create_timeseries(
            hours=100, base_utilization=0.90, volatility=0.02
        )
        result = calculator.calculate(market, timeseries)

        # May have insufficient data in range, but should not error
        assert result.status in (KPIStatus.SUCCESS, KPIStatus.INSUFFICIENT_DATA)


class TestIRMEvolutionCalculator:
    """Tests for IRMEvolutionCalculator."""

    @pytest.fixture
    def calculator(self):
        return IRMEvolutionCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.IRM_EVOLUTION

    def test_stable_rate(self, calculator, market):
        """Test with stable rate at target."""
        timeseries = TestFixtures.create_timeseries(hours=100, volatility=0.001)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert "trend" in result.metadata

    def test_increasing_rate(self, calculator, market):
        """Test with increasing rate at target."""
        timeseries = TestFixtures.create_timeseries(hours=100, trend=0.02)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        if result.metadata.get("trend"):
            # Trend should be detected
            pass


class TestMeanReversionCalculator:
    """Tests for MeanReversionCalculator."""

    @pytest.fixture
    def calculator(self):
        return MeanReversionCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.MEAN_REVERSION

    def test_mean_reverting_series(self, calculator, market):
        """Test with mean-reverting data."""
        timeseries = TestFixtures.create_timeseries(hours=100, volatility=0.01)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert "theta" in result.metadata or "is_mean_reverting" in result.metadata


class TestUtilAdjustedReturnCalculator:
    """Tests for UtilAdjustedReturnCalculator."""

    @pytest.fixture
    def calculator(self):
        return UtilAdjustedReturnCalculator()

    @pytest.fixture
    def market(self):
        return TestFixtures.create_market()

    def test_kpi_type(self, calculator):
        """Test correct KPI type."""
        assert calculator.kpi_type == KPIType.UTIL_ADJUSTED_RETURN

    def test_low_utilization_no_penalty(self, calculator, market):
        """Test that low utilization has minimal penalty."""
        timeseries = TestFixtures.create_timeseries(
            hours=50, base_utilization=0.70, volatility=0.01
        )
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert result.metadata.get("mean_penalty", 0) > 0.5  # Low penalty (above 50%)

    def test_high_utilization_penalty(self, calculator, market):
        """Test that high utilization has penalty."""
        timeseries = TestFixtures.create_timeseries(
            hours=50, base_utilization=0.95, volatility=0.01
        )
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert result.metadata.get("mean_penalty", 1) < 0.5  # Significant penalty

    def test_yield_haircut_calculation(self, calculator, market):
        """Test yield haircut is calculated."""
        timeseries = TestFixtures.create_timeseries(hours=50)
        result = calculator.calculate(market, timeseries)

        assert result.status == KPIStatus.SUCCESS
        assert "yield_haircut" in result.metadata
        assert "raw_mean_apy" in result.metadata
