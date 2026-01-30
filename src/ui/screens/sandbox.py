"""Sandbox screen for vault allocation simulation."""

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
)
from textual.reactive import reactive

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.sandbox.data import DataAggregator
from src.sandbox.engine import AllocationSimulator
from src.sandbox.models import AllocationConfig, AllocationStrategy, AllocationResult
from src.core.models import Market

logger = logging.getLogger(__name__)


class SandboxScreen(Widget):
    """Vault allocation sandbox for simulation."""

    DEFAULT_CSS = """
    SandboxScreen {
        height: 100%;
        width: 100%;
        padding: 0 1;
    }

    #sandbox-main {
        height: 100%;
        width: 100%;
    }

    #config-panel {
        width: 100%;
        height: auto;
        border: solid #333;
        padding: 1;
        margin-bottom: 1;
    }

    #config-title {
        text-style: bold;
        color: #ff8c00;
        height: 1;
    }

    .config-row {
        height: 3;
        width: 100%;
        margin-top: 1;
    }

    .config-label {
        width: 12;
        padding-top: 1;
        color: #888;
    }

    #market-input {
        width: 1fr;
    }

    .param-group {
        width: 1fr;
        height: 3;
    }

    .param-input {
        width: 15;
    }

    #button-row {
        height: 3;
        width: 100%;
        margin-top: 1;
    }

    #run-button {
        width: 20;
    }

    #add-market-button {
        width: 15;
        margin-left: 2;
    }

    #clear-button {
        width: 10;
        margin-left: 2;
    }

    #selected-markets {
        height: auto;
        max-height: 4;
        color: #aaa;
        padding-left: 12;
    }

    #results-panel {
        height: 1fr;
        width: 100%;
        border: solid #333;
        padding: 1;
    }

    #results-title {
        text-style: bold;
        color: #ff8c00;
        height: 1;
    }

    #metrics-table {
        height: auto;
        max-height: 16;
        margin-top: 1;
    }

    #charts-panel {
        height: 7;
        margin-top: 1;
    }

    .chart-container {
        width: 1fr;
        height: 100%;
        border: solid #222;
        margin-right: 1;
        padding: 0 1;
    }

    .chart-title {
        color: #888;
        text-align: center;
        height: 1;
    }

    Sparkline {
        height: 5;
    }

    #status-line {
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
    """

    BINDINGS = [
        Binding("enter", "run_simulation", "Run", show=True),
        Binding("a", "add_market", "Add Market", show=True),
        Binding("c", "clear_markets", "Clear", show=True),
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
        self.simulator = AllocationSimulator(self.aggregator)

        self._all_markets: List[Market] = []
        self._filtered_markets: List[Market] = []
        self._selected_market_ids: List[str] = []
        self._current_result: Optional[AllocationResult] = None
        self._current_loan_token: str = ""
        self._initialized = False

    def compose(self) -> ComposeResult:
        with Vertical(id="sandbox-main"):
            # Configuration Panel
            with Container(id="config-panel"):
                yield Static("Vault Allocation Simulation", id="config-title")

                # Loan token filter + Market selection
                with Horizontal(classes="config-row"):
                    yield Label("Loan Token:", classes="config-label")
                    yield Select(
                        [("Loading...", "")],
                        id="loan-token-select",
                    )

                with Horizontal(classes="config-row"):
                    yield Label("Market:", classes="config-label")
                    yield Select(
                        [("Select loan token first", "")],
                        id="market-select",
                    )
                    yield Button("+Add", id="add-market-button")
                    yield Button("Clear", id="clear-button")

                yield Static("Selected: (none)", id="selected-markets")

                # Parameters row
                with Horizontal(classes="config-row"):
                    with Horizontal(classes="param-group"):
                        yield Label("Strategy:", classes="config-label")
                        yield Select(
                            [
                                ("Waterfill", "waterfill"),
                                ("Yield-Weighted", "yield_weighted"),
                                ("Equal", "equal"),
                            ],
                            value="waterfill",
                            id="strategy-select",
                        )
                    with Horizontal(classes="param-group"):
                        yield Label("Capital:", classes="config-label")
                        yield Input(value="100000", id="capital-input", classes="param-input")
                    with Horizontal(classes="param-group"):
                        yield Label("Days:", classes="config-label")
                        yield Input(value="30", id="days-input", classes="param-input")

                with Horizontal(classes="config-row"):
                    with Horizontal(classes="param-group"):
                        yield Label("Rebal (h):", classes="config-label")
                        yield Input(value="168", id="rebalance-input", classes="param-input")
                    with Horizontal(classes="param-group"):
                        yield Label("Min Alloc:", classes="config-label")
                        yield Input(value="0.05", id="min-alloc-input", classes="param-input")
                    with Horizontal(classes="param-group"):
                        yield Label("Max Alloc:", classes="config-label")
                        yield Input(value="0.5", id="max-alloc-input", classes="param-input")

                # Run button
                with Horizontal(id="button-row"):
                    yield Button("Run Simulation", id="run-button", variant="primary")

            # Results Panel
            with Container(id="results-panel"):
                yield Static("Simulation Results", id="results-title")
                yield DataTable(id="metrics-table")

                with Horizontal(id="charts-panel"):
                    with Vertical(classes="chart-container"):
                        yield Static("PnL Evolution %", classes="chart-title")
                        yield Sparkline([], id="pnl-sparkline")
                    with Vertical(classes="chart-container"):
                        yield Static("Excess vs Benchmark %", classes="chart-title")
                        yield Sparkline([], id="excess-sparkline")
                    with Vertical(classes="chart-container"):
                        yield Static("Weighted APY %", classes="chart-title")
                        yield Sparkline([], id="apy-sparkline")

            yield Static("Ready | Enter: Run  A: Add market  C: Clear", id="status-line")

    async def on_mount(self) -> None:
        """Initialize when mounted."""
        if not self._initialized:
            await self._load_markets()
            self._setup_metrics_table()
            self._initialized = True

    async def _load_markets(self) -> None:
        """Load available markets."""
        self._update_status("Loading markets...")

        try:
            markets = await self.aggregator.get_markets("morpho", first=100)

            # Filter for reasonable markets (TVL > 1M, APY 0-50%)
            self._all_markets = [
                m for m in markets
                if float(m.tvl) > 1_000_000
                and 0 <= float(m.supply_apy) < 0.5
            ]

            # Sort by TVL
            self._all_markets.sort(key=lambda m: float(m.tvl), reverse=True)

            # Extract unique loan tokens
            loan_tokens = {}
            for m in self._all_markets:
                token = m.loan_asset_symbol
                if token not in loan_tokens:
                    loan_tokens[token] = 0
                loan_tokens[token] += 1

            # Sort by count (most common first)
            sorted_tokens = sorted(loan_tokens.items(), key=lambda x: -x[1])

            # Update loan token select
            token_select = self.query_one("#loan-token-select", Select)
            token_options = [(f"{t} ({c} markets)", t) for t, c in sorted_tokens]
            token_select.set_options(token_options)

            if token_options:
                token_select.value = token_options[0][1]
                self._current_loan_token = str(token_options[0][1])
                self._filter_markets_by_token(self._current_loan_token)

            self._update_status(f"Loaded {len(self._all_markets)} markets")

        except Exception as e:
            logger.error(f"Error loading markets: {e}")
            self._update_status(f"Error: {e}")

    def _filter_markets_by_token(self, loan_token: str) -> None:
        """Filter markets by loan token."""
        self._filtered_markets = [
            m for m in self._all_markets
            if m.loan_asset_symbol == loan_token
        ]

        # Update market select
        select = self.query_one("#market-select", Select)
        options = [
            (f"{m.collateral_asset_symbol} ({float(m.supply_apy)*100:.1f}% APY, ${float(m.tvl)/1e6:.0f}M)", m.id)
            for m in self._filtered_markets[:30]
        ]
        select.set_options(options)

        if options:
            select.value = options[0][1]

        # Clear selection when token changes
        self._selected_market_ids = []
        self._update_selected_display()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "loan-token-select" and event.value:
            self._current_loan_token = str(event.value)
            self._filter_markets_by_token(self._current_loan_token)
            self._update_status(f"Filtered to {self._current_loan_token} markets")

    def _setup_metrics_table(self) -> None:
        """Set up metrics table."""
        table = self.query_one("#metrics-table", DataTable)
        table.add_columns("Metric", "Strategy", "Benchmark", "Diff")

        placeholders = [
            ("Total Return", "-", "-", "-"),
            ("Annualized", "-", "-", "-"),
            ("Sharpe Ratio", "-", "-", "-"),
            ("Avg APY", "-", "-", "-"),
            ("Max Drawdown", "-", "-", "-"),
            ("Rebalances", "-", "-", "-"),
        ]
        for row in placeholders:
            table.add_row(*row)

    def _update_selected_display(self) -> None:
        """Update display of selected markets."""
        label = self.query_one("#selected-markets", Static)

        if not self._selected_market_ids:
            label.update(f"Selected: (none) - Loan token: {self._current_loan_token}")
            return

        names = []
        for mid in self._selected_market_ids:
            for m in self._all_markets:
                if m.id == mid:
                    names.append(m.collateral_asset_symbol)
                    break

        label.update(f"Selected ({len(names)}): " + ", ".join(names) + f" → {self._current_loan_token}")

    def _update_metrics(self) -> None:
        """Update metrics table."""
        if not self._current_result or not self._current_result.metrics:
            return

        r = self._current_result
        m = r.metrics

        table = self.query_one("#metrics-table", DataTable)
        table.clear()
        table.add_columns("Metric", "Strategy", "Benchmark", "Diff")

        rows = [
            (
                "Total Return",
                f"{float(m.total_return_pct):.3f}%",
                f"{float(m.benchmark_return_pct):.3f}%",
                f"{float(m.excess_return_pct):+.3f}%",
            ),
            (
                "Annualized",
                f"{float(m.annualized_return):.2f}%",
                "-",
                "-",
            ),
            (
                "Sharpe Ratio",
                f"{float(m.sharpe_ratio):.2f}",
                "-",
                "-",
            ),
            (
                "Avg APY",
                f"{float(m.avg_weighted_apy)*100:.2f}%",
                "-",
                "-",
            ),
            (
                "Max Drawdown",
                f"{float(m.max_drawdown):.3f}%",
                "-",
                "-",
            ),
            (
                "Rebalances",
                str(m.rebalance_count),
                "0",
                f"+{m.rebalance_count}",
            ),
        ]

        for row in rows:
            table.add_row(*row)

        # Add allocation breakdown
        table.add_row("", "", "", "")
        table.add_row("Final Allocations", "", "", "")

        if r.snapshots:
            for alloc in r.snapshots[-1].allocations:
                table.add_row(
                    f"  {alloc.market_name}",
                    f"{float(alloc.weight)*100:.1f}%",
                    f"{float(alloc.amount):.0f}",
                    "",
                )

    def _update_charts(self) -> None:
        """Update charts."""
        if not self._current_result:
            return

        try:
            # PnL evolution (strategy returns)
            strategy_returns = self._current_result.return_series
            pnl_sparkline = self.query_one("#pnl-sparkline", Sparkline)
            pnl_sparkline.data = strategy_returns

            # Excess return (strategy - benchmark)
            benchmark_returns = self._current_result.benchmark_series
            if len(strategy_returns) == len(benchmark_returns):
                excess = [s - b for s, b in zip(strategy_returns, benchmark_returns)]
                excess_sparkline = self.query_one("#excess-sparkline", Sparkline)
                excess_sparkline.data = excess

            # APY over time
            apy_data = [a * 100 for a in self._current_result.apy_series]  # Convert to %
            apy_sparkline = self.query_one("#apy-sparkline", Sparkline)
            apy_sparkline.data = apy_data

        except Exception as e:
            logger.warning(f"Error updating charts: {e}")

    def _update_status(self, message: str) -> None:
        """Update status line."""
        self.status_message = message
        try:
            status = self.query_one("#status-line", Static)
            status.update(message)
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "run-button":
            await self._run_simulation()
        elif event.button.id == "add-market-button":
            self._add_selected_market()
        elif event.button.id == "clear-button":
            self._clear_markets()

    def _add_selected_market(self) -> None:
        """Add currently selected market to list."""
        select = self.query_one("#market-select", Select)
        if select.value and select.value not in self._selected_market_ids:
            self._selected_market_ids.append(str(select.value))
            self._update_selected_display()
            self._update_status(f"Added market ({len(self._selected_market_ids)} selected)")

    def _clear_markets(self) -> None:
        """Clear selected markets."""
        self._selected_market_ids = []
        self._update_selected_display()
        self._update_status("Markets cleared")

    async def action_add_market(self) -> None:
        """Add market action."""
        self._add_selected_market()

    async def action_clear_markets(self) -> None:
        """Clear markets action."""
        self._clear_markets()

    async def action_run_simulation(self) -> None:
        """Run simulation action."""
        await self._run_simulation()

    async def _run_simulation(self) -> None:
        """Run allocation simulation."""
        if self.is_running:
            return

        if len(self._selected_market_ids) < 2:
            self._update_status("Error: Select at least 2 markets")
            return

        self.is_running = True
        self._update_status("Running simulation...")

        try:
            # Get config values
            strategy_select = self.query_one("#strategy-select", Select)
            capital_input = self.query_one("#capital-input", Input)
            days_input = self.query_one("#days-input", Input)
            rebalance_input = self.query_one("#rebalance-input", Input)
            min_alloc_input = self.query_one("#min-alloc-input", Input)
            max_alloc_input = self.query_one("#max-alloc-input", Input)

            strategy_map = {
                "waterfill": AllocationStrategy.WATERFILL,
                "yield_weighted": AllocationStrategy.YIELD_WEIGHTED,
                "equal": AllocationStrategy.EQUAL,
            }
            strategy = strategy_map.get(str(strategy_select.value), AllocationStrategy.WATERFILL)

            config = AllocationConfig(
                name="Vault Simulation",
                market_ids=self._selected_market_ids.copy(),
                initial_capital=Decimal(capital_input.value or "100000"),
                strategy=strategy,
                rebalance_frequency_hours=int(rebalance_input.value or "168"),
                min_allocation=Decimal(min_alloc_input.value or "0"),
                max_allocation=Decimal(max_alloc_input.value or "1"),
                simulation_days=int(days_input.value or "30"),
                simulation_interval="HOUR",
            )

            self._update_status(f"Simulating {len(config.market_ids)} markets...")

            result = await self.simulator.run_simulation(config)
            self._current_result = result

            if result.success:
                self._update_metrics()
                self._update_charts()
                m = result.metrics
                self._update_status(
                    f"Done: {float(m.total_return_pct):.3f}% return, "
                    f"{float(m.excess_return_pct):+.3f}% vs benchmark"
                )
            else:
                self._update_status(f"Failed: {result.error_message}")

        except Exception as e:
            logger.error(f"Simulation error: {e}")
            self._update_status(f"Error: {e}")

        finally:
            self.is_running = False
