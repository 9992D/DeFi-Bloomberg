"""Markets screen widget for the main app."""

import asyncio
import logging
from typing import Optional, List, Set

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static, DataTable, Input, Label
from textual import on
from rich.text import Text

from config.settings import Settings
from src.core.models import Market, KPIType, KPIStatus
from src.data.pipeline import DataPipeline
from src.analytics.engine import AnalyticsEngine
from src.ui.screens.historical import HistoricalScreen

logger = logging.getLogger(__name__)

# Sparkline characters
BLOCKS = " ▁▂▃▄▅▆▇█"


def make_sparkline(data: List[float], width: int = 30, color: str = "green") -> Text:
    """Create a sparkline from data."""
    if not data:
        return Text("No data", style="dim")

    # Resample if needed
    if len(data) > width:
        step = len(data) / width
        resampled = []
        for i in range(width):
            idx = int(i * step)
            resampled.append(data[idx])
        data = resampled

    min_val = min(data)
    max_val = max(data)
    val_range = max_val - min_val or 1

    result = Text()
    result.append(f"{min_val*100:5.1f}% ", style="dim")

    for v in data:
        normalized = ((v - min_val) / val_range) * 8
        idx = min(int(normalized), len(BLOCKS) - 1)
        result.append(BLOCKS[idx], style=color)

    result.append(f" {max_val*100:5.1f}%", style="dim")
    if data:
        result.append(f" [now: {data[-1]*100:.2f}%]", style=f"bold {color}")

    return result


def shorten_address(addr: str, chars: int = 6) -> str:
    """Shorten an Ethereum address for display."""
    if not addr or len(addr) < 10:
        return addr or ""
    return f"{addr[:chars]}...{addr[-4:]}"


class MarketsScreen(Widget):
    """Widget for displaying and interacting with markets."""

    DEFAULT_CSS = """
    MarketsScreen {
        height: 100%;
        layout: horizontal;
    }
    #markets-left {
        width: 60%;
        border-right: solid #333;
    }
    #markets-right {
        width: 40%;
        padding: 1;
    }
    #markets-left-header, #markets-right-header {
        dock: top;
        height: 3;
        background: #111;
        padding: 1;
        color: #ff8c00;
        text-style: bold;
    }
    #markets-filters {
        dock: top;
        height: 5;
        background: #0a0a0a;
        padding: 0 1;
        layout: horizontal;
    }
    .filter-box {
        width: 1fr;
        padding: 0 1;
    }
    .filter-box Label {
        color: #888;
    }
    .filter-box Input {
        background: #111;
        border: solid #333;
        width: 100%;
        height: 3;
    }
    .filter-box Input:focus {
        border: solid #ff8c00;
    }
    #markets-table-container {
        height: 100%;
    }
    #markets-table {
        height: 100%;
    }
    DataTable > .datatable--header {
        background: #111;
        color: #ff8c00;
    }
    DataTable > .datatable--cursor {
        background: #663300;
        color: #fff;
    }
    DataTable:focus > .datatable--cursor {
        background: #ff8c00;
        color: #000;
    }
    #markets-kpi-scroll {
        height: 100%;
    }
    #markets-kpi {
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("h", "show_history", "History"),
    ]

    def __init__(self, pipeline: DataPipeline, settings: Settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipeline = pipeline
        self.settings = settings
        self.analytics = AnalyticsEngine(pipeline=self.pipeline)
        self._markets: List[Market] = []
        self._filtered_markets: List[Market] = []
        self._loan_filter: str = ""
        self._collateral_filter: str = ""
        self._selected_market: Optional[Market] = None

    def compose(self) -> ComposeResult:
        with Container(id="markets-left"):
            yield Static("MORPHO BLUE MARKETS", id="markets-left-header")
            with Horizontal(id="markets-filters"):
                with Vertical(classes="filter-box"):
                    yield Label("Loan Asset (comma-separated)")
                    yield Input(placeholder="0x..., 0x...", id="loan-filter")
                with Vertical(classes="filter-box"):
                    yield Label("Collateral Asset (comma-separated)")
                    yield Input(placeholder="0x..., 0x...", id="collateral-filter")
            with ScrollableContainer(id="markets-table-container"):
                yield DataTable(id="markets-table", cursor_type="row", zebra_stripes=True)
        with Vertical(id="markets-right"):
            yield Static("KPI ANALYTICS", id="markets-right-header")
            with ScrollableContainer(id="markets-kpi-scroll"):
                yield Static("Select a market...", id="markets-kpi")

    async def on_mount(self) -> None:
        table = self.query_one("#markets-table", DataTable)
        table.add_column("Market ID", width=14)
        table.add_column("Loan", width=8)
        table.add_column("Collat", width=8)
        table.add_column("LLTV", width=6)
        table.add_column("Supply", width=7)
        table.add_column("Util", width=6)
        table.add_column("Created", width=10)

        await self._load_markets()

    async def _load_markets(self) -> None:
        try:
            self._markets = await self.pipeline.get_markets(first=500)
            self._apply_filters()
        except Exception as e:
            logger.error(f"Error: {e}")

    async def refresh_data(self) -> None:
        """Refresh market data."""
        await self._load_markets()

    def _apply_filters(self) -> None:
        """Apply loan and collateral filters to markets."""
        loan_addrs: Set[str] = set()
        collateral_addrs: Set[str] = set()

        if self._loan_filter.strip():
            for addr in self._loan_filter.split(","):
                addr = addr.strip().lower()
                if addr:
                    loan_addrs.add(addr)

        if self._collateral_filter.strip():
            for addr in self._collateral_filter.split(","):
                addr = addr.strip().lower()
                if addr:
                    collateral_addrs.add(addr)

        filtered = []
        for m in self._markets:
            if loan_addrs:
                loan_match = any(
                    addr in m.loan_asset.lower() or m.loan_asset.lower().startswith(addr)
                    for addr in loan_addrs
                )
                if not loan_match:
                    continue

            if collateral_addrs:
                coll_match = any(
                    addr in m.collateral_asset.lower() or m.collateral_asset.lower().startswith(addr)
                    for addr in collateral_addrs
                )
                if not coll_match:
                    continue

            filtered.append(m)

        self._filtered_markets = filtered
        self._update_table()

    def _update_table(self) -> None:
        """Update the table with filtered markets."""
        table = self.query_one("#markets-table", DataTable)
        table.clear()

        for m in self._filtered_markets:
            created = m.creation_timestamp.strftime("%Y-%m-%d") if m.creation_timestamp else "N/A"
            table.add_row(
                shorten_address(m.id, 8),
                m.loan_asset_symbol[:6],
                m.collateral_asset_symbol[:6],
                f"{float(m.lltv)*100:.0f}%",
                f"{float(m.supply_apy)*100:.1f}%",
                f"{float(m.utilization)*100:.0f}%",
                created,
                key=m.id,
            )

    @on(Input.Changed, "#loan-filter")
    def on_loan_filter_changed(self, event: Input.Changed) -> None:
        self._loan_filter = event.value
        self._apply_filters()

    @on(Input.Changed, "#collateral-filter")
    def on_collateral_filter_changed(self, event: Input.Changed) -> None:
        self._collateral_filter = event.value
        self._apply_filters()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle market selection from table."""
        row_key = event.row_key
        if row_key is None:
            return

        market = next((m for m in self._markets if m.id == row_key.value), None)
        if not market:
            return

        self._selected_market = market
        kpi_widget = self.query_one("#markets-kpi", Static)
        kpi_widget.update("Loading KPIs...")

        try:
            timeseries = await self.pipeline.get_market_timeseries(market.id)
            kpis = await self.analytics.calculate_market_kpis(market, timeseries=timeseries)

            output = Text()
            output.append("─" * 42 + "\n", style="dim")
            output.append("MARKET DETAILS\n", style="bold #ff8c00")
            output.append("─" * 42 + "\n", style="dim")

            output.append(f"{market.name}\n", style="bold cyan")
            output.append("\n")

            output.append("Market ID:\n", style="dim")
            output.append(f"  {market.id}\n", style="white")

            output.append("Loan Asset:\n", style="dim")
            output.append(f"  {market.loan_asset}\n", style="green")
            output.append(f"  ({market.loan_asset_symbol})\n", style="dim green")

            output.append("Collateral:\n", style="dim")
            output.append(f"  {market.collateral_asset}\n", style="yellow")
            output.append(f"  ({market.collateral_asset_symbol})\n", style="dim yellow")

            output.append(f"\nMax LTV: ", style="dim")
            output.append(f"{float(market.lltv)*100:.1f}%\n", style="bold white")

            output.append(f"Rate at Target: ", style="dim")
            output.append(f"{float(market.rate_at_target)*100:.2f}%\n", style="white")

            # TVL
            tvl = float(market.tvl)
            if tvl >= 1_000_000_000:
                tvl_str = f"${tvl/1_000_000_000:.2f}B"
            elif tvl >= 1_000_000:
                tvl_str = f"${tvl/1_000_000:.2f}M"
            elif tvl >= 1_000:
                tvl_str = f"${tvl/1_000:.2f}K"
            else:
                tvl_str = f"${tvl:.2f}"
            output.append(f"TVL: ", style="dim")
            output.append(f"{tvl_str}\n", style="bold cyan")

            # Sparklines
            if timeseries:
                supply_data = [float(p.supply_apy) for p in timeseries]
                borrow_data = [float(p.borrow_apy) for p in timeseries]
                util_data = [float(p.utilization) for p in timeseries]

                output.append("\n")
                output.append("─" * 42 + "\n", style="dim")
                output.append("HISTORICAL DATA\n", style="bold #ff8c00")
                output.append("─" * 42 + "\n", style="dim")

                first_date = timeseries[0].timestamp.strftime("%Y-%m-%d")
                last_date = timeseries[-1].timestamp.strftime("%Y-%m-%d")
                output.append(f"{first_date} → {last_date} ({len(timeseries)} pts)\n\n", style="dim")

                output.append("Supply APY  ", style="green dim")
                output.append_text(make_sparkline(supply_data, width=20, color="green"))
                output.append("\n")

                output.append("Borrow APY  ", style="red dim")
                output.append_text(make_sparkline(borrow_data, width=20, color="red"))
                output.append("\n")

                output.append("Utilization ", style="yellow dim")
                output.append_text(make_sparkline(util_data, width=20, color="yellow"))
                output.append("\n")

            # KPIs
            output.append("\n")
            output.append("─" * 42 + "\n", style="dim")
            output.append("KPI METRICS\n", style="bold #ff8c00")
            output.append("─" * 42 + "\n", style="dim")

            for kt in KPIType:
                r = kpis.get(kt)
                if r and r.status == KPIStatus.SUCCESS:
                    output.append(f"{kt.value:20s} ", style="dim")
                    output.append(f"{r.display_value}\n", style="bold white")
                else:
                    output.append(f"{kt.value:20s} ", style="dim")
                    output.append("N/A\n", style="dim red")

            kpi_widget.update(output)

        except Exception as e:
            logger.error(f"KPI error: {e}")
            kpi_widget.update(f"Error: {e}")

    def action_show_history(self) -> None:
        """Open the historical data screen for the selected market."""
        if self._selected_market is None:
            self.notify("Select a market first", severity="warning")
            return

        if not self.settings.alchemy_rpc_url:
            self.notify("Alchemy API key required for historical data", severity="warning")
            return

        self.app.push_screen(HistoricalScreen(self._selected_market))
