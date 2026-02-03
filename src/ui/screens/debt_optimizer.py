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
from src.protocols.morpho.assets import (
    COLLATERAL_ASSETS as MORPHO_COLLATERAL,
    BORROW_ASSETS as MORPHO_BORROW,
    DEFAULT_COLLATERAL_ADDRESS as MORPHO_DEFAULT_COLLAT,
    DEFAULT_BORROW_ADDRESS as MORPHO_DEFAULT_BORROW,
    get_asset_name as get_morpho_asset_name,
)
from src.protocols.aave.assets import (
    COLLATERAL_ASSETS as AAVE_COLLATERAL,
    BORROW_ASSETS as AAVE_BORROW,
    DEFAULT_COLLATERAL_ADDRESS as AAVE_DEFAULT_COLLAT,
    DEFAULT_BORROW_ADDRESS as AAVE_DEFAULT_BORROW,
    get_asset_name as get_aave_asset_name,
)

logger = logging.getLogger(__name__)

# Rebalancing modes
REBALANCING_MODES = [
    ("Dynamic Rate (Recommended)", "dynamic_rate"),
    ("Static Threshold", "static_threshold"),
    ("Predictive (IRM)", "predictive"),
    ("Opportunity Cost", "opportunity_cost"),
]

# Available protocols
PROTOCOLS = [
    ("Morpho Blue", "morpho"),
    ("Aave v3", "aave"),
    ("Cross-Protocol (Morpho + Aave)", "cross"),
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
        # Initialize DataAggregator with both protocols using the same pipeline
        self.aggregator = DataAggregator(pipelines={
            "morpho": pipeline,
            "aave": pipeline,
        })
        self.optimizer = DebtRebalancingOptimizer(self.aggregator)

        self._current_result: Optional[RebalancingResult] = None
        self._initialized = False
        self._current_protocol = "morpho"

        # Track current asset lists based on protocol
        self._collateral_assets = MORPHO_COLLATERAL
        self._borrow_assets = MORPHO_BORROW
        self._default_collateral = MORPHO_DEFAULT_COLLAT
        self._default_borrow = MORPHO_DEFAULT_BORROW

    def compose(self) -> ComposeResult:
        with Vertical(id="debt-optimizer-main"):
            # Configuration Panel
            with Container(id="debt-config-panel"):
                yield Static("Debt Rebalancing Optimizer", id="debt-config-title")

                # Protocol selection row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Protocol:", classes="debt-config-label")
                        yield Select(
                            PROTOCOLS,
                            value="morpho",
                            id="protocol-select",
                        )

                # Asset selection row
                with Horizontal(classes="debt-config-row"):
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Collateral:", classes="debt-config-label")
                        yield Select(
                            self._collateral_assets,
                            value=self._default_collateral,
                            id="collateral-select",
                        )
                    with Horizontal(classes="debt-param-group"):
                        yield Label("Borrow:", classes="debt-config-label")
                        yield Select(
                            self._borrow_assets,
                            value=self._default_borrow,
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

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if event.select.id == "protocol-select":
            await self._update_protocol_assets(str(event.value))

    async def _update_protocol_assets(self, protocol: str) -> None:
        """Update asset options when protocol changes."""
        self._current_protocol = protocol

        if protocol == "aave":
            self._collateral_assets = AAVE_COLLATERAL
            self._borrow_assets = AAVE_BORROW
            self._default_collateral = AAVE_DEFAULT_COLLAT
            self._default_borrow = AAVE_DEFAULT_BORROW
        elif protocol == "cross":
            # Cross-protocol: Use combined assets (Morpho base + Aave extras)
            # Combine unique assets from both protocols
            self._collateral_assets = self._merge_assets(MORPHO_COLLATERAL, AAVE_COLLATERAL)
            self._borrow_assets = self._merge_assets(MORPHO_BORROW, AAVE_BORROW)
            self._default_collateral = MORPHO_DEFAULT_COLLAT
            self._default_borrow = MORPHO_DEFAULT_BORROW
        else:
            self._collateral_assets = MORPHO_COLLATERAL
            self._borrow_assets = MORPHO_BORROW
            self._default_collateral = MORPHO_DEFAULT_COLLAT
            self._default_borrow = MORPHO_DEFAULT_BORROW

        # Update the Select widgets with new options
        try:
            collateral_select = self.query_one("#collateral-select", Select)
            borrow_select = self.query_one("#borrow-select", Select)

            # Clear and set new options
            collateral_select.set_options(self._collateral_assets)
            collateral_select.value = self._default_collateral

            borrow_select.set_options(self._borrow_assets)
            borrow_select.value = self._default_borrow

            protocol_name = "Cross-Protocol" if protocol == "cross" else protocol.title()
            self._update_status(f"Switched to {protocol_name}")
        except Exception as e:
            logger.warning(f"Error updating asset selects: {e}")

    def _merge_assets(self, list1: list, list2: list) -> list:
        """Merge two asset lists, keeping unique addresses."""
        seen_addresses = set()
        merged = []

        for name, addr in list1:
            addr_lower = addr.lower()
            if addr_lower not in seen_addresses:
                seen_addresses.add(addr_lower)
                merged.append((name, addr))

        for name, addr in list2:
            addr_lower = addr.lower()
            if addr_lower not in seen_addresses and addr != "custom":
                seen_addresses.add(addr_lower)
                merged.append((name, addr))

        return merged

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
            protocol_select = self.query_one("#protocol-select", Select)
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

            # Get selected protocol and addresses
            protocol = str(protocol_select.value)
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

            # For Aave and Cross-protocol: actual_collateral_asset is the collateral address
            # (since Aave markets show MULTI as collateral)
            actual_collateral = collateral_addr if protocol in ("aave", "cross") else ""

            config = RebalancingConfig(
                collateral_asset=collateral_addr,
                borrow_asset=borrow_addr,
                actual_collateral_asset=actual_collateral,
                collateral_amount=Decimal(collateral_input.value or "100"),
                initial_ltv=initial_ltv,
                protocol=protocol,
                rebalancing_mode=rebalancing_mode,
                rate_threshold_bps=Decimal(threshold_input.value or "10"),
                min_allocation_pct=Decimal(min_alloc_input.value or "5") / 100,
                max_allocation_pct=Decimal(max_alloc_input.value or "80") / 100,
                min_health_factor=Decimal(min_hf_input.value or "1.2"),
                gas_cost_usd=Decimal(gas_input.value or "5"),
                simulation_days=int(days_input.value or "30"),
            )

            # Get display names for status
            collateral_name = get_morpho_asset_name(collateral_addr, MORPHO_COLLATERAL)
            borrow_name = get_morpho_asset_name(borrow_addr, MORPHO_BORROW)

            if protocol == "cross":
                protocol_label = "Cross-Protocol"
            else:
                protocol_label = protocol.title()

            self._update_status(
                f"[{protocol_label}] Finding {collateral_name}/{borrow_name} markets..."
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
        table.clear(columns=True)
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
        table.clear(columns=True)
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
        # Clear both rows AND columns to avoid duplicates
        table.clear(columns=True)

        # Check if cross-protocol to show protocol column
        is_cross = result.config.is_cross_protocol
        if is_cross:
            table.add_columns("Proto", "Market", "APY", "LLTV", "Util", "Score")
        else:
            table.add_columns("Market", "APY", "LLTV", "Util", "Liquidity", "Score")

        for market in result.available_markets[:10]:  # Top 10
            # Protocol indicator: M=Morpho, A=Aave
            proto = "A" if market.protocol == "aave" else "M"

            if is_cross:
                table.add_row(
                    proto,
                    market.market_name[:14],
                    f"{float(market.borrow_apy)*100:.2f}%",
                    f"{float(market.lltv)*100:.0f}%",
                    f"{float(market.utilization)*100:.0f}%",
                    f"{float(market.score):.1f}",
                )
            else:
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
            if is_cross:
                table.add_row("", "", "", "", "", "")
                table.add_row("", "OPTIMAL ALLOCATION", "", "", "", "")
            else:
                table.add_row("", "", "", "", "", "")
                table.add_row("OPTIMAL ALLOCATION", "", "", "", "", "")

            for pos in result.optimal_positions:
                # Format borrow amount with commas for large USD values
                borrow_display = f"${float(pos.borrow_amount):,.0f}" if float(pos.borrow_amount) > 100 else f"{float(pos.borrow_amount):.2f}"
                if is_cross:
                    # Find market to get protocol
                    market = next((m for m in result.available_markets if m.market_id == pos.market_id), None)
                    proto = "A" if (market and market.protocol == "aave") else "M"
                    table.add_row(
                        proto,
                        f"{pos.market_name[:12]}",
                        f"{float(pos.borrow_apy)*100:.2f}%",
                        f"{float(pos.allocation_weight)*100:.0f}%",
                        borrow_display,
                        f"HF:{float(pos.health_factor):.2f}",
                    )
                else:
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
        table.clear(columns=True)
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
        table.clear(columns=True)
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
