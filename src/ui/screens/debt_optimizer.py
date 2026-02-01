"""Debt optimizer screen for rebalancing simulation."""

import asyncio
import logging
from decimal import Decimal
from typing import Optional, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import (
    Static,
    DataTable,
    Button,
    Input,
    Select,
    Label,
    Sparkline,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.sandbox.data import DataAggregator
from src.sandbox.engine.debt_optimizer import DebtRebalancingOptimizer
from src.sandbox.models.rebalancing import RebalancingConfig, RebalancingResult
from src.core.models import Market

logger = logging.getLogger(__name__)


# Common collateral assets for lending
COLLATERAL_ASSETS = [
    ("wstETH", "wstETH"),
    ("WETH", "WETH"),
    ("cbETH", "cbETH"),
    ("rETH", "rETH"),
    ("weETH", "weETH"),
    ("sDAI", "sDAI"),
    ("WBTC", "WBTC"),
]

# Common borrow assets
BORROW_ASSETS = [
    ("WETH", "WETH"),
    ("ETH", "ETH"),
    ("USDC", "USDC"),
    ("USDT", "USDT"),
    ("DAI", "DAI"),
    ("USDA", "USDA"),
]


class DebtOptimizerScreen(Widget):
    """Debt rebalancing optimizer screen."""

    DEFAULT_CSS = """
    DebtOptimizerScreen {
        height: 100%;
        width: 100%;
        padding: 0 1;
    }

    #debt-optimizer-main {
        height: 100%;
        width: 100%;
    }

    #debt-config-panel {
        width: 100%;
        height: auto;
        border: solid #333;
        padding: 1;
        margin-bottom: 1;
    }

    #debt-config-title {
        text-style: bold;
        color: #ff8c00;
        height: 1;
    }

    .debt-config-row {
        height: 3;
        width: 100%;
        margin-top: 1;
    }

    .debt-config-label {
        width: 14;
        padding-top: 1;
        color: #888;
    }

    .debt-param-group {
        width: 1fr;
        height: 3;
    }

    .debt-param-input {
        width: 15;
    }

    #collateral-calc {
        height: 1;
        color: #ff8c00;
        padding-left: 14;
        margin-top: 1;
    }

    #debt-button-row {
        height: 3;
        width: 100%;
        margin-top: 1;
    }

    #debt-run-button {
        width: 20;
    }

    #debt-results-panel {
        height: 1fr;
        width: 100%;
        border: solid #333;
        padding: 1;
    }

    #debt-results-title {
        text-style: bold;
        color: #ff8c00;
        height: 1;
    }

    #markets-table {
        height: auto;
        max-height: 10;
        margin-top: 1;
    }

    #opportunities-table {
        height: auto;
        max-height: 8;
        margin-top: 1;
    }

    #metrics-panel {
        height: auto;
        max-height: 10;
        margin-top: 1;
    }

    #debt-charts-panel {
        height: 8;
        margin-top: 1;
    }

    .debt-chart-container {
        width: 1fr;
        height: 100%;
        border: solid #222;
        margin-right: 1;
        padding: 0 1;
    }

    .debt-chart-title {
        color: #888;
        text-align: center;
        height: 1;
    }

    Sparkline {
        height: 5;
    }

    #debt-status-line {
        height: 1;
        background: #111;
        color: #888;
        padding: 0 1;
    }

    Button {
        background: #222;
        color: #ff8c00;
        border: solid #444;
    }

    Button:hover {
        background: #333;
    }

    Button:focus {
        border: solid #ff8c00;
    }

    Input {
        background: #111;
        border: solid #333;
    }

    Input:focus {
        border: solid #ff8c00;
    }

    Select {
        background: #111;
        border: solid #333;
    }

    .section-title {
        color: #888;
        text-style: bold;
        margin-top: 1;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("enter", "run_optimization", "Optimize", show=True),
    ]

    is_running = reactive(False)
    status_message = reactive("Ready")

    def __init__(
        self,
        pipeline: DataPipeline,
        settings: Settings,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        self.settings = settings
        self.aggregator = DataAggregator(pipelines={"morpho": pipeline})
        self.optimizer = DebtRebalancingOptimizer(self.aggregator)

        self._current_result: Optional[RebalancingResult] = None
        self._initialized = False

    def compose(self) -> ComposeResult:
        with Vertical(id="debt-optimizer-main"):
            # Configuration Panel
            with Container(id="debt-config-panel"):
                yield Static("Debt Rebalancing Optimizer", id="debt-config-title")

                # Asset selection row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Collateral:", classes="debt-config-label")
                        yield Select(
                            COLLATERAL_ASSETS,
                            value="wstETH",
                            id="collateral-select",
                        )
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Borrow:", classes="debt-config-label")
                        yield Select(
                            BORROW_ASSETS,
                            value="WETH",
                            id="borrow-select",
                        )

                # Position parameters row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Total Debt:", classes="debt-config-label")
                        yield Input(value="100", id="debt-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Leverage:", classes="debt-config-label")
                        yield Input(value="3", id="leverage-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Threshold (bps):", classes="debt-config-label")
                        yield Input(value="10", id="threshold-input", classes="debt-param-input")

                # Calculated collateral display
                yield Static("Required Collateral: 50.00 (at 3x leverage)", id="collateral-calc")

                # Simulation params row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Days:", classes="debt-config-label")
                        yield Input(value="30", id="days-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Min Alloc %:", classes="debt-config-label")
                        yield Input(value="5", id="min-alloc-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Max Alloc %:", classes="debt-config-label")
                        yield Input(value="80", id="max-alloc-input", classes="debt-param-input")

                # Run button
                with Horizontal(id="debt-button-row"):
                    yield Button("Optimize Debt", id="debt-run-button", variant="primary")

            # Results Panel
            with ScrollableContainer(id="debt-results-panel"):
                yield Static("Optimization Results", id="debt-results-title")

                # Markets table
                yield Static("Available Markets", classes="section-title")
                yield DataTable(id="markets-table")

                # Opportunities table
                yield Static("Rebalancing Opportunities", classes="section-title")
                yield DataTable(id="opportunities-table")

                # Metrics
                yield Static("Simulation Metrics", classes="section-title")
                yield DataTable(id="metrics-panel")

                # Charts
                with Horizontal(id="debt-charts-panel"):
                    with Vertical(classes="debt-chart-container"):
                        yield Static("Borrow APY %", classes="debt-chart-title")
                        yield Sparkline([], id="apy-sparkline")
                    with Vertical(classes="debt-chart-container"):
                        yield Static("Cumulative Interest", classes="debt-chart-title")
                        yield Sparkline([], id="interest-sparkline")
                    with Vertical(classes="debt-chart-container"):
                        yield Static("Savings vs Benchmark", classes="debt-chart-title")
                        yield Sparkline([], id="savings-sparkline")

            yield Static("Ready | Enter: Run Optimization", id="debt-status-line")

    async def on_mount(self) -> None:
        """Initialize when mounted."""
        if not self._initialized:
            self._setup_tables()
            self._initialized = True

    def _setup_tables(self) -> None:
        """Set up result tables."""
        # Markets table
        markets_table = self.query_one("#markets-table", DataTable)
        markets_table.add_columns("Market", "Borrow APY", "Utilization", "Liquidity", "Score")

        # Opportunities table
        opps_table = self.query_one("#opportunities-table", DataTable)
        opps_table.add_columns("From", "To", "Rate Diff", "Savings/mo", "Breakeven", "Net 30d")

        # Metrics table
        metrics_table = self.query_one("#metrics-panel", DataTable)
        metrics_table.add_columns("Metric", "Strategy", "Benchmark", "Diff")

    def _update_collateral_calc(self) -> None:
        """Update calculated collateral display."""
        try:
            debt_input = self.query_one("#debt-input", Input)
            leverage_input = self.query_one("#leverage-input", Input)

            debt = Decimal(debt_input.value or "100")
            leverage = Decimal(leverage_input.value or "3")

            if leverage > 1:
                collateral = debt / (leverage - 1)
                text = f"Required Collateral: {collateral:.2f} (at {leverage}x leverage)"
            else:
                text = "Required Collateral: N/A (leverage must be > 1)"

            calc_label = self.query_one("#collateral-calc", Static)
            calc_label.update(text)
        except Exception:
            pass

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id in ("debt-input", "leverage-input"):
            self._update_collateral_calc()

    def _update_status(self, message: str) -> None:
        """Update status line."""
        self.status_message = message
        try:
            status = self.query_one("#debt-status-line", Static)
            status.update(message)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "debt-run-button":
            await self._run_optimization()

    async def action_run_optimization(self) -> None:
        """Run optimization action."""
        await self._run_optimization()

    async def _run_optimization(self) -> None:
        """Run debt rebalancing optimization."""
        if self.is_running:
            return

        self.is_running = True
        self._update_status("Running optimization...")

        try:
            # Get config values
            collateral_select = self.query_one("#collateral-select", Select)
            borrow_select = self.query_one("#borrow-select", Select)
            debt_input = self.query_one("#debt-input", Input)
            leverage_input = self.query_one("#leverage-input", Input)
            threshold_input = self.query_one("#threshold-input", Input)
            days_input = self.query_one("#days-input", Input)
            min_alloc_input = self.query_one("#min-alloc-input", Input)
            max_alloc_input = self.query_one("#max-alloc-input", Input)

            config = RebalancingConfig(
                collateral_asset=str(collateral_select.value),
                borrow_asset=str(borrow_select.value),
                total_debt=Decimal(debt_input.value or "100"),
                target_leverage=Decimal(leverage_input.value or "3"),
                rate_threshold_bps=Decimal(threshold_input.value or "10"),
                min_allocation_pct=Decimal(min_alloc_input.value or "5") / 100,
                max_allocation_pct=Decimal(max_alloc_input.value or "80") / 100,
                simulation_days=int(days_input.value or "30"),
            )

            self._update_status(
                f"Finding {config.collateral_asset}/{config.borrow_asset} markets..."
            )

            result = await self.optimizer.optimize(config)
            self._current_result = result

            if result.success:
                self._update_markets_table(result)
                self._update_opportunities_table(result)
                self._update_metrics_table(result)
                self._update_charts(result)

                self._update_status(
                    f"Done: {len(result.available_markets)} markets, "
                    f"{len(result.opportunities)} opportunities"
                )
            else:
                self._update_status(f"Failed: {result.error_message}")

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            self._update_status(f"Error: {e}")

        finally:
            self.is_running = False

    def _update_markets_table(self, result: RebalancingResult) -> None:
        """Update markets table with results."""
        table = self.query_one("#markets-table", DataTable)
        table.clear()
        table.add_columns("Market", "Borrow APY", "Utilization", "Liquidity", "Score")

        for market in result.available_markets[:10]:  # Top 10
            table.add_row(
                market.market_name[:20],
                f"{float(market.borrow_apy)*100:.2f}%",
                f"{float(market.utilization)*100:.1f}%",
                f"${float(market.available_liquidity)/1e6:.1f}M",
                f"{float(market.score)*100:.2f}",
            )

        # Add optimal allocation section
        if result.optimal_positions:
            table.add_row("", "", "", "", "")
            table.add_row("OPTIMAL ALLOCATION", "", "", "", "")
            for pos in result.optimal_positions:
                table.add_row(
                    f"  {pos.market_name[:18]}",
                    f"{float(pos.borrow_apy)*100:.2f}%",
                    f"{float(pos.allocation_weight)*100:.0f}%",
                    f"{float(pos.borrow_amount):.2f}",
                    f"HF: {float(pos.health_factor):.2f}",
                )

    def _update_opportunities_table(self, result: RebalancingResult) -> None:
        """Update opportunities table."""
        table = self.query_one("#opportunities-table", DataTable)
        table.clear()
        table.add_columns("From", "To", "Rate Diff", "Savings/mo", "Breakeven", "Net 30d")

        if not result.opportunities:
            table.add_row("No opportunities found", "-", "-", "-", "-", "-")
            return

        for opp in result.opportunities[:5]:  # Top 5
            from_name = opp.from_market_name[:12] if len(opp.from_market_name) > 12 else opp.from_market_name
            to_name = opp.to_market_name[:12] if len(opp.to_market_name) > 12 else opp.to_market_name

            table.add_row(
                from_name,
                to_name,
                f"{float(opp.rate_diff_bps):.0f} bps",
                f"${float(opp.monthly_savings):.2f}",
                f"{float(opp.breakeven_days):.0f}d",
                f"${float(opp.net_benefit_30d):+.2f}",
            )

    def _update_metrics_table(self, result: RebalancingResult) -> None:
        """Update metrics table."""
        table = self.query_one("#metrics-panel", DataTable)
        table.clear()
        table.add_columns("Metric", "Strategy", "Benchmark", "Diff")

        if not result.metrics:
            return

        m = result.metrics

        rows = [
            (
                "Interest Paid",
                f"${float(m.total_interest_paid):.4f}",
                f"${float(m.benchmark_interest_paid):.4f}",
                f"${float(m.interest_savings):+.4f}",
            ),
            (
                "Interest Savings",
                f"{float(m.interest_savings_pct):.2f}%",
                "-",
                "-",
            ),
            (
                "Avg Borrow APY",
                f"{float(m.avg_weighted_borrow_apy)*100:.2f}%",
                f"{float(m.benchmark_avg_borrow_apy)*100:.2f}%",
                f"{float(m.avg_weighted_borrow_apy - m.benchmark_avg_borrow_apy)*100:+.2f}%",
            ),
            (
                "APY Range",
                f"{float(m.min_weighted_borrow_apy)*100:.2f}-{float(m.max_weighted_borrow_apy)*100:.2f}%",
                "-",
                "-",
            ),
            (
                "Rebalances",
                str(m.rebalance_count),
                "0",
                f"+{m.rebalance_count}",
            ),
            (
                "Rebalance Cost",
                f"${float(m.total_rebalance_cost):.2f}",
                "$0",
                f"${float(m.total_rebalance_cost):.2f}",
            ),
            (
                "Net Savings",
                f"${float(m.net_savings):.4f}",
                "-",
                "-",
            ),
            (
                "Net Savings (Ann.)",
                f"${float(m.net_savings_annualized):.2f}",
                "-",
                "-",
            ),
        ]

        for row in rows:
            table.add_row(*row)

    def _update_charts(self, result: RebalancingResult) -> None:
        """Update sparkline charts."""
        try:
            # Borrow APY over time
            apy_data = [a * 100 for a in result.borrow_apy_series]  # Convert to %
            apy_sparkline = self.query_one("#apy-sparkline", Sparkline)
            apy_sparkline.data = apy_data if apy_data else [0]

            # Cumulative interest
            interest_data = result.cumulative_interest_series
            interest_sparkline = self.query_one("#interest-sparkline", Sparkline)
            interest_sparkline.data = interest_data if interest_data else [0]

            # Savings vs benchmark
            if result.cumulative_interest_series and result.benchmark_interest_series:
                savings_data = [
                    b - s for s, b in zip(
                        result.cumulative_interest_series,
                        result.benchmark_interest_series
                    )
                ]
                savings_sparkline = self.query_one("#savings-sparkline", Sparkline)
                savings_sparkline.data = savings_data if savings_data else [0]

        except Exception as e:
            logger.warning(f"Error updating charts: {e}")
