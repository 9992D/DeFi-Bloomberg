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
from src.sandbox.models.rebalancing import RebalancingConfig, RebalancingMode, RebalancingResult, PositionSummary
from src.core.models import Market

logger = logging.getLogger(__name__)


# Common collateral assets with addresses (Ethereum mainnet)
# Format: (display_name, address)
COLLATERAL_ASSETS = [
    ("wstETH", "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"),
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("cbETH", "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704"),
    ("rETH", "0xae78736Cd615f374D3085123A210448E74Fc6393"),
    ("weETH", "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee"),
    ("sDAI", "0x83F20F44975D03b1b09e64809B757c47f942BEeA"),
    ("WBTC", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),
    ("Custom address...", "custom"),
]

# Common borrow assets with addresses (Ethereum mainnet)
BORROW_ASSETS = [
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
    ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
    ("DAI", "0x6B175474E89094C44Da98b954EesdeaFE3C4d256"),
    ("USDA", "0x0000206329b97DB379d5E1Bf586BbDB969C63274"),
    ("pyUSD", "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"),
    ("Custom address...", "custom"),
]

# Rebalancing modes
REBALANCING_MODES = [
    ("Dynamic Rate (Recommended)", "dynamic_rate"),
    ("Static Threshold", "static_threshold"),
    ("Predictive (IRM)", "predictive"),
    ("Opportunity Cost", "opportunity_cost"),
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
                            value="0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0",  # wstETH
                            id="collateral-select",
                        )
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Borrow:", classes="debt-config-label")
                        yield Select(
                            BORROW_ASSETS,
                            value="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                            id="borrow-select",
                        )

                # Position parameters row - LTV-based
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Collateral Amt:", classes="debt-config-label")
                        yield Input(value="100", id="collateral-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Initial LTV %:", classes="debt-config-label")
                        yield Input(value="70", id="ltv-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Threshold (bps):", classes="debt-config-label")
                        yield Input(value="10", id="threshold-input", classes="debt-param-input")

                # Calculated borrow amount display
                yield Static("Borrow Amount: 70.00 (at 70% LTV)", id="borrow-calc")

                # Rebalancing mode row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Mode:", classes="debt-config-label")
                        yield Select(
                            REBALANCING_MODES,
                            value="dynamic_rate",
                            id="mode-select",
                        )
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Days:", classes="debt-config-label")
                        yield Input(value="30", id="days-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Min HF:", classes="debt-config-label")
                        yield Input(value="1.2", id="min-hf-input", classes="debt-param-input")

                # Allocation params row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Min Alloc %:", classes="debt-config-label")
                        yield Input(value="5", id="min-alloc-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Max Alloc %:", classes="debt-config-label")
                        yield Input(value="80", id="max-alloc-input", classes="debt-param-input")
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Gas ($):", classes="debt-config-label")
                        yield Input(value="5", id="gas-input", classes="debt-param-input")

                # Run button
                with Horizontal(id="debt-button-row"):
                    yield Button("Optimize Debt", id="debt-run-button", variant="primary")

            # Results Panel
            with ScrollableContainer(id="debt-results-panel"):
                yield Static("Optimization Results", id="debt-results-title")

                # Position Summary table (new)
                yield Static("Position Summary", classes="section-title")
                yield DataTable(id="position-summary-table")

                # Price Scenarios table (new)
                yield Static("Price Scenarios", classes="section-title")
                yield DataTable(id="price-scenarios-table")

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
                        yield Static("HF by Price", classes="debt-chart-title")
                        yield Sparkline([], id="hf-sparkline")

            yield Static("Ready | Enter: Run Optimization", id="debt-status-line")

    async def on_mount(self) -> None:
        """Initialize when mounted."""
        if not self._initialized:
            self._setup_tables()
            self._initialized = True

    def _setup_tables(self) -> None:
        """Set up result tables."""
        # Position Summary table
        summary_table = self.query_one("#position-summary-table", DataTable)
        summary_table.add_columns("Category", "Metric", "Value")

        # Price Scenarios table
        scenarios_table = self.query_one("#price-scenarios-table", DataTable)
        scenarios_table.add_columns("Price Chg", "Price", "HF", "LTV", "Dist to Liq", "Status")

        # Markets table
        markets_table = self.query_one("#markets-table", DataTable)
        markets_table.add_columns("Market", "APY", "LLTV", "Util", "Liquidity", "Score")

        # Opportunities table
        opps_table = self.query_one("#opportunities-table", DataTable)
        opps_table.add_columns("From", "To", "Rate Diff", "Savings/mo", "Breakeven", "Net 30d")

        # Metrics table
        metrics_table = self.query_one("#metrics-panel", DataTable)
        metrics_table.add_columns("Metric", "Strategy", "Benchmark", "Diff")

    def _update_borrow_calc(self) -> None:
        """Update calculated borrow amount display with USD value hint."""
        try:
            collateral_input = self.query_one("#collateral-input", Input)
            ltv_input = self.query_one("#ltv-input", Input)

            collateral = Decimal(collateral_input.value or "100")
            ltv_pct = Decimal(ltv_input.value or "70")
            ltv = ltv_pct / 100

            if ltv > 0 and ltv <= 1:
                borrow = collateral * ltv
                # Note: actual USD value will be calculated during optimization using real prices
                text = f"Borrow Amount: {borrow:.2f} tokens (at {ltv_pct:.0f}% LTV) - USD value calculated at runtime"
            else:
                text = "Borrow Amount: N/A (LTV must be 0-100%)"

            calc_label = self.query_one("#borrow-calc", Static)
            calc_label.update(text)
        except Exception:
            pass

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id in ("collateral-input", "ltv-input"):
            self._update_borrow_calc()

    def _update_status(self, message: str) -> None:
        """Update status line."""
        self.status_message = message
        try:
            status = self.query_one("#debt-status-line", Static)
            status.update(message)
        except Exception:
            pass

    def _get_asset_name(self, address: str, asset_list: list) -> str:
        """Get display name for an asset address."""
        for name, addr in asset_list:
            if addr.lower() == address.lower():
                return name
        # Return shortened address if not found
        return f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address

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
            collateral_input = self.query_one("#collateral-input", Input)
            ltv_input = self.query_one("#ltv-input", Input)
            threshold_input = self.query_one("#threshold-input", Input)
            days_input = self.query_one("#days-input", Input)
            min_alloc_input = self.query_one("#min-alloc-input", Input)
            max_alloc_input = self.query_one("#max-alloc-input", Input)
            mode_select = self.query_one("#mode-select", Select)
            min_hf_input = self.query_one("#min-hf-input", Input)
            gas_input = self.query_one("#gas-input", Input)

            # Get selected addresses (not symbols)
            collateral_addr = str(collateral_select.value)
            borrow_addr = str(borrow_select.value)

            # Map mode string to enum
            mode_map = {
                "static_threshold": RebalancingMode.STATIC_THRESHOLD,
                "dynamic_rate": RebalancingMode.DYNAMIC_RATE,
                "predictive": RebalancingMode.PREDICTIVE,
                "opportunity_cost": RebalancingMode.OPPORTUNITY_COST,
            }
            rebalancing_mode = mode_map.get(str(mode_select.value), RebalancingMode.DYNAMIC_RATE)

            # Parse LTV (input is percentage, convert to decimal)
            ltv_pct = Decimal(ltv_input.value or "70")
            initial_ltv = ltv_pct / 100

            config = RebalancingConfig(
                collateral_asset=collateral_addr,
                borrow_asset=borrow_addr,
                collateral_amount=Decimal(collateral_input.value or "100"),
                initial_ltv=initial_ltv,
                rebalancing_mode=rebalancing_mode,
                rate_threshold_bps=Decimal(threshold_input.value or "10"),
                min_allocation_pct=Decimal(min_alloc_input.value or "5") / 100,
                max_allocation_pct=Decimal(max_alloc_input.value or "80") / 100,
                min_health_factor=Decimal(min_hf_input.value or "1.2"),
                gas_cost_usd=Decimal(gas_input.value or "5"),
                simulation_days=int(days_input.value or "30"),
            )

            # Get display names for status
            collateral_name = self._get_asset_name(collateral_addr, COLLATERAL_ASSETS)
            borrow_name = self._get_asset_name(borrow_addr, BORROW_ASSETS)

            self._update_status(
                f"Finding {collateral_name}/{borrow_name} markets (by address)..."
            )

            result = await self.optimizer.optimize(config)
            self._current_result = result

            if result.success:
                self._update_position_summary(result)
                self._update_price_scenarios(result)
                self._update_markets_table(result)
                self._update_opportunities_table(result)
                self._update_metrics_table(result)
                self._update_charts(result)

                # Build status with alerts if any
                status_parts = [
                    f"Done: {len(result.available_markets)} markets, "
                    f"{len(result.opportunities)} opportunities"
                ]
                if result.position_summary and result.position_summary.alerts:
                    status_parts.append(f" | {len(result.position_summary.alerts)} alerts")

                self._update_status("".join(status_parts))
            else:
                self._update_status(f"Failed: {result.error_message}")

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            self._update_status(f"Error: {e}")

        finally:
            self.is_running = False

    def _update_position_summary(self, result: RebalancingResult) -> None:
        """Update position summary table with USD values."""
        table = self.query_one("#position-summary-table", DataTable)
        table.clear()
        table.add_columns("Category", "Metric", "Value")

        summary = result.position_summary
        if not summary:
            table.add_row("No position summary available", "", "")
            return

        # Calculate USD values
        # collateral_price is in loan asset terms (e.g., WBTC/USDC = 80000)
        collateral_value_usd = float(summary.collateral_amount) * float(summary.collateral_price)
        borrow_value_usd = float(summary.borrow_amount)  # Already in loan asset (e.g., USDC)

        # Position section with USD values
        table.add_row("POSITION", "Collateral", f"{float(summary.collateral_amount):.4f} {summary.collateral_symbol}")
        table.add_row("", "Collateral Value", f"${collateral_value_usd:,.2f} USD")
        table.add_row("", "Borrow", f"{float(summary.borrow_amount):,.2f} {summary.borrow_symbol}")
        table.add_row("", "Borrow Value", f"${borrow_value_usd:,.2f} USD")
        table.add_row("", "Collateral Price", f"{float(summary.collateral_price):,.2f} {summary.borrow_symbol}/{summary.collateral_symbol}")

        # Risk section
        table.add_row("RISK", "Health Factor", f"{float(summary.health_factor):.2f}")
        table.add_row("", "Current LTV", f"{float(summary.current_ltv)*100:.1f}%")
        table.add_row("", "Max LTV (LLTV)", f"{float(summary.max_ltv)*100:.1f}%")
        table.add_row("", "Liquidation Price", f"{float(summary.liquidation_price):,.2f}")
        table.add_row("", "Dist to Liquidation", f"{float(summary.distance_to_liquidation_pct):.1f}%")
        table.add_row("", "Margin Call Price", f"{float(summary.margin_call_price):,.2f}")

        # Cost section with USD values
        table.add_row("COST", "Borrow APY", f"{float(summary.borrow_apy)*100:.2f}%")
        table.add_row("", "Daily Interest", f"{float(summary.estimated_daily_interest):,.2f} {summary.borrow_symbol}")
        table.add_row("", "Monthly Interest", f"{float(summary.estimated_monthly_interest):,.2f} {summary.borrow_symbol}")
        table.add_row("", "Annual Interest", f"{float(summary.estimated_annual_interest):,.2f} {summary.borrow_symbol}")

        # Alerts section
        if summary.alerts:
            table.add_row("ALERTS", "", "")
            for alert in summary.alerts:
                table.add_row("", "⚠", alert[:50])

    def _update_price_scenarios(self, result: RebalancingResult) -> None:
        """Update price scenarios table."""
        table = self.query_one("#price-scenarios-table", DataTable)
        table.clear()
        table.add_columns("Price Chg", "Price", "HF", "LTV", "Dist to Liq", "Status")

        summary = result.position_summary
        if not summary or not summary.price_scenarios:
            table.add_row("No scenarios", "-", "-", "-", "-", "-")
            return

        for scenario in summary.price_scenarios:
            # Determine status indicator
            if scenario.is_liquidatable:
                status = "LIQUIDATED"
            elif scenario.is_margin_call:
                status = "MARGIN CALL"
            else:
                status = "OK"

            table.add_row(
                f"{float(scenario.price_change_pct):+.0f}%",
                f"{float(scenario.collateral_price):.4f}",
                f"{float(scenario.health_factor):.2f}",
                f"{float(scenario.current_ltv)*100:.1f}%",
                f"{float(scenario.distance_to_liquidation_pct):.1f}%",
                status,
            )

    def _update_markets_table(self, result: RebalancingResult) -> None:
        """Update markets table with results and USD values."""
        table = self.query_one("#markets-table", DataTable)
        table.clear()
        table.add_columns("Market", "APY", "LLTV", "Util", "Liquidity", "Score")

        for market in result.available_markets[:10]:  # Top 10
            table.add_row(
                market.market_name[:16],
                f"{float(market.borrow_apy)*100:.2f}%",
                f"{float(market.lltv)*100:.0f}%",
                f"{float(market.utilization)*100:.0f}%",
                f"${float(market.available_liquidity)/1e6:.1f}M",
                f"{float(market.score):.1f}",
            )

        # Add optimal allocation section with USD values
        if result.optimal_positions:
            table.add_row("", "", "", "", "", "")
            table.add_row("OPTIMAL ALLOCATION", "", "", "", "", "")
            for pos in result.optimal_positions:
                # Format borrow amount with commas for large USD values
                borrow_display = f"${float(pos.borrow_amount):,.0f}" if float(pos.borrow_amount) > 100 else f"{float(pos.borrow_amount):.2f}"
                table.add_row(
                    f"  {pos.market_name[:14]}",
                    f"{float(pos.borrow_apy)*100:.2f}%",
                    f"{float(pos.allocation_weight)*100:.0f}%",
                    borrow_display,
                    f"HF:{float(pos.health_factor):.2f}",
                    f"Liq:{float(pos.liquidation_price):,.0f}",
                )

    def _update_opportunities_table(self, result: RebalancingResult) -> None:
        """Update opportunities table."""
        table = self.query_one("#opportunities-table", DataTable)
        table.clear()
        table.add_columns("From", "To", "Rate Diff", "Savings/mo", "Breakeven", "Net 30d")

        if not result.opportunities:
            table.add_row("No rebalancing opportunities", "-", "-", "-", "-", "-")
            return

        for opp in result.opportunities[:5]:  # Top 5
            from_name = opp.from_market_name[:10] if len(opp.from_market_name) > 10 else opp.from_market_name
            to_name = opp.to_market_name[:10] if len(opp.to_market_name) > 10 else opp.to_market_name

            # Only show opportunities with positive net benefit
            net_30d = float(opp.net_benefit_30d)
            net_color = "+" if net_30d >= 0 else ""

            table.add_row(
                from_name,
                to_name,
                f"{float(opp.rate_diff_bps):.0f}bp",
                f"${float(opp.monthly_savings):.2f}",
                f"{float(opp.breakeven_days):.0f}d",
                f"${net_color}{net_30d:.2f}",
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
        """Update sparkline charts with simulation data."""
        try:
            # Borrow APY over time
            apy_data = [a * 100 for a in result.borrow_apy_series]  # Convert to %
            apy_sparkline = self.query_one("#apy-sparkline", Sparkline)
            apy_sparkline.data = apy_data if apy_data else [0]

            # Cumulative interest over time
            interest_data = result.cumulative_interest_series
            interest_sparkline = self.query_one("#interest-sparkline", Sparkline)
            interest_sparkline.data = interest_data if interest_data else [0]

            # Health Factor evolution during backtest simulation
            # Shows how HF changes over time with price movements and debt growth
            hf_data = result.health_factor_series
            if hf_data:
                hf_sparkline = self.query_one("#hf-sparkline", Sparkline)
                hf_sparkline.data = hf_data
            elif result.position_summary and result.position_summary.price_scenarios:
                # Fallback to price scenarios if no simulation HF data
                hf_data = [float(s.health_factor) for s in result.position_summary.price_scenarios]
                hf_sparkline = self.query_one("#hf-sparkline", Sparkline)
                hf_sparkline.data = hf_data if hf_data else [0]

        except Exception as e:
            logger.warning(f"Error updating charts: {e}")
