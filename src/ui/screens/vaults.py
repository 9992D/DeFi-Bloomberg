"""Vaults screen widget for the main app."""

import asyncio
import logging
from typing import Optional, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static, DataTable, Input, Label
from textual import on
from rich.text import Text

from config.settings import Settings
from src.core.models import Vault
from src.data.pipeline import DataPipeline
from src.ui.screens.vault_historical import VaultHistoricalScreen

logger = logging.getLogger(__name__)

# Sparkline characters
BLOCKS = " ▁▂▃▄▅▆▇█"


def make_sparkline(data: List[float], width: int = 30, color: str = "green", as_percent: bool = True) -> Text:
    """Create a sparkline from data."""
    if not data:
        return Text("No data", style="dim")

    if len(data) > width:
        step = len(data) / width
        data = [data[int(i * step)] for i in range(width)]

    min_val = min(data)
    max_val = max(data)
    val_range = max_val - min_val or 1

    result = Text()
    if as_percent:
        result.append(f"{min_val*100:5.1f}% ", style="dim")
    else:
        result.append(f"{min_val:8.4f} ", style="dim")

    for v in data:
        normalized = ((v - min_val) / val_range) * 8
        idx = min(int(normalized), len(BLOCKS) - 1)
        result.append(BLOCKS[idx], style=color)

    if as_percent:
        result.append(f" {max_val*100:5.1f}%", style="dim")
        if data:
            result.append(f" [now: {data[-1]*100:.2f}%]", style=f"bold {color}")
    else:
        result.append(f" {max_val:8.4f}", style="dim")
        if data:
            result.append(f" [now: {data[-1]:.4f}]", style=f"bold {color}")

    return result


def make_sparkline_usd(data: List[float], width: int = 30, color: str = "cyan") -> Text:
    """Create a sparkline for USD values."""
    if not data:
        return Text("No data", style="dim")

    if len(data) > width:
        step = len(data) / width
        data = [data[int(i * step)] for i in range(width)]

    min_val = min(data)
    max_val = max(data)
    val_range = max_val - min_val or 1

    result = Text()
    result.append(f"{format_usd(min_val):>9s} ", style="dim")

    for v in data:
        normalized = ((v - min_val) / val_range) * 8
        idx = min(int(normalized), len(BLOCKS) - 1)
        result.append(BLOCKS[idx], style=color)

    result.append(f" {format_usd(max_val)}", style="dim")

    return result


def format_usd(value: float) -> str:
    """Format a USD value with appropriate suffix."""
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.2f}K"
    else:
        return f"${value:.2f}"


def shorten_address(addr: str, chars: int = 6) -> str:
    """Shorten an Ethereum address for display."""
    if not addr or len(addr) < 10:
        return addr or ""
    return f"{addr[:chars]}...{addr[-4:]}"


class VaultsScreen(Widget):
    """Widget for displaying and interacting with vaults."""

    DEFAULT_CSS = """
    VaultsScreen {
        height: 100%;
        layout: horizontal;
    }
    #vaults-left {
        width: 55%;
        border-right: solid #333;
    }
    #vaults-right {
        width: 45%;
        padding: 1;
    }
    #vaults-left-header, #vaults-right-header {
        dock: top;
        height: 3;
        background: #111;
        padding: 1;
        color: #ff8c00;
        text-style: bold;
    }
    #vaults-filters {
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
    #vaults-table-container {
        height: 100%;
    }
    #vaults-table {
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
    #vaults-kpi-scroll {
        height: 100%;
    }
    #vaults-kpi {
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
        self._vaults: List[Vault] = []
        self._filtered_vaults: List[Vault] = []
        self._name_filter: str = ""
        self._selected_vault: Optional[Vault] = None

    def compose(self) -> ComposeResult:
        with Container(id="vaults-left"):
            yield Static("MORPHO METAMORPHO VAULTS", id="vaults-left-header")
            with Horizontal(id="vaults-filters"):
                with Vertical(classes="filter-box"):
                    yield Label("Filter by Name/Symbol")
                    yield Input(placeholder="steakUSDC, Gauntlet...", id="vault-name-filter")
            with ScrollableContainer(id="vaults-table-container"):
                yield DataTable(id="vaults-table", cursor_type="row", zebra_stripes=True)
        with Vertical(id="vaults-right"):
            yield Static("VAULT DETAILS", id="vaults-right-header")
            with ScrollableContainer(id="vaults-kpi-scroll"):
                yield Static("Select a vault...", id="vaults-kpi")

    async def on_mount(self) -> None:
        table = self.query_one("#vaults-table", DataTable)
        table.add_column("Name", width=18)
        table.add_column("Asset", width=6)
        table.add_column("APY", width=7)
        table.add_column("Net", width=7)
        table.add_column("TVL", width=10)
        table.add_column("Share$", width=8)
        table.add_column("Created", width=10)

        await self._load_vaults()

    async def _load_vaults(self) -> None:
        try:
            self._vaults = await self.pipeline.get_vaults(first=200)
            self._apply_filters()
        except Exception as e:
            logger.error(f"Error loading vaults: {e}")

    async def refresh_data(self) -> None:
        """Refresh vault data."""
        await self._load_vaults()

    def _apply_filters(self) -> None:
        """Apply name filter to vaults."""
        if not self._name_filter.strip():
            self._filtered_vaults = self._vaults
        else:
            search = self._name_filter.strip().lower()
            self._filtered_vaults = [
                v for v in self._vaults
                if search in v.name.lower() or search in v.symbol.lower()
            ]
        self._update_table()

    def _update_table(self) -> None:
        """Update the table with filtered vaults."""
        table = self.query_one("#vaults-table", DataTable)
        table.clear()

        for v in self._filtered_vaults:
            created = v.creation_timestamp.strftime("%Y-%m-%d") if v.creation_timestamp else "N/A"
            table.add_row(
                v.name[:16] if len(v.name) > 16 else v.name,
                v.asset_symbol,
                f"{float(v.apy)*100:.1f}%",
                f"{float(v.net_apy)*100:.1f}%",
                format_usd(float(v.tvl)),
                f"${float(v.share_price):.3f}",
                created,
                key=v.id,
            )

    @on(Input.Changed, "#vault-name-filter")
    def on_name_filter_changed(self, event: Input.Changed) -> None:
        self._name_filter = event.value
        self._apply_filters()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle vault selection from table."""
        row_key = event.row_key
        if row_key is None:
            return

        vault = next((v for v in self._vaults if v.id == row_key.value), None)
        if not vault:
            return

        self._selected_vault = vault
        kpi_widget = self.query_one("#vaults-kpi", Static)
        kpi_widget.update("Loading vault details...")

        try:
            # Fetch detailed vault with timeseries
            detailed_vault = await self.pipeline.get_vault(vault.id)
            if detailed_vault:
                vault = detailed_vault
                self._selected_vault = vault

            timeseries = await self.pipeline.get_vault_timeseries(vault.id)

            output = Text()
            output.append("─" * 44 + "\n", style="dim")
            output.append("VAULT DETAILS\n", style="bold #ff8c00")
            output.append("─" * 44 + "\n", style="dim")

            output.append(f"{vault.name}\n", style="bold cyan")
            output.append(f"Symbol: {vault.symbol}\n", style="dim")
            output.append("\n")

            output.append("Vault Address:\n", style="dim")
            output.append(f"  {vault.id}\n", style="white")

            output.append("Underlying Asset:\n", style="dim")
            output.append(f"  {vault.asset_symbol} ", style="green")
            output.append(f"({shorten_address(vault.asset_address)})\n", style="dim green")

            # Key Metrics
            output.append("\n")
            output.append("─" * 44 + "\n", style="dim")
            output.append("KEY METRICS\n", style="bold #ff8c00")
            output.append("─" * 44 + "\n", style="dim")

            output.append(f"TVL: ", style="dim")
            output.append(f"{format_usd(float(vault.tvl))}\n", style="bold cyan")

            output.append(f"APY: ", style="dim")
            output.append(f"{float(vault.apy)*100:.2f}%\n", style="bold green")

            output.append(f"Net APY: ", style="dim")
            output.append(f"{float(vault.net_apy)*100:.2f}%\n", style="bold green")

            if vault.state:
                output.append(f"Fee: ", style="dim")
                output.append(f"{float(vault.state.fee)*100:.1f}%\n", style="white")

            # Share Price
            output.append("\n")
            output.append("─" * 44 + "\n", style="dim")
            output.append("SHARE PRICE\n", style="bold #ff8c00")
            output.append("─" * 44 + "\n", style="dim")

            output.append(f"Current Share Price: ", style="dim")
            output.append(f"${float(vault.share_price):.6f}\n", style="bold white")

            if vault.state:
                output.append(f"Share Price (USD): ", style="dim")
                output.append(f"${float(vault.state.share_price_usd):.6f}\n", style="white")

            # Share price evolution from timeseries
            if timeseries:
                share_prices = [float(p.share_price) for p in timeseries if p.share_price]
                if share_prices and len(share_prices) >= 2:
                    first_price = share_prices[0]
                    last_price = share_prices[-1]
                    price_change = ((last_price / first_price) - 1) * 100
                    change_color = "green" if price_change >= 0 else "red"

                    output.append(f"Price Change: ", style="dim")
                    output.append(f"{price_change:+.4f}%\n", style=change_color)

            # Allocation
            if vault.state and vault.state.allocation:
                output.append("\n")
                output.append("─" * 44 + "\n", style="dim")
                output.append("ALLOCATION\n", style="bold #ff8c00")
                output.append("─" * 44 + "\n", style="dim")

                allocations = vault.get_allocation_percents()
                for market_name, pct, usd_value in allocations[:8]:  # Top 8
                    # Truncate long market names
                    display_name = market_name[:14] if len(market_name) > 14 else market_name
                    bar_width = int(pct / 5)  # Scale to 20 chars max
                    bar = "█" * bar_width
                    output.append(f"  {display_name:14s} ", style="white")
                    output.append(f"{bar:20s} ", style="cyan")
                    output.append(f"{pct:5.1f}% ", style="bold")
                    output.append(f"{format_usd(usd_value)}\n", style="dim")

            # Historical sparklines - prefer share price and TVL (more data points)
            if timeseries:
                share_prices = [float(p.share_price) for p in timeseries if p.share_price]
                tvl_data = [float(p.total_assets) for p in timeseries if p.total_assets]

                # Only show if we have meaningful data
                if share_prices or tvl_data:
                    output.append("\n")
                    output.append("─" * 44 + "\n", style="dim")
                    output.append("HISTORICAL DATA\n", style="bold #ff8c00")
                    output.append("─" * 44 + "\n", style="dim")

                    first_date = timeseries[0].timestamp.strftime("%Y-%m-%d")
                    last_date = timeseries[-1].timestamp.strftime("%Y-%m-%d")
                    pts_count = max(len(share_prices), len(tvl_data))
                    output.append(f"{first_date} → {last_date} ({pts_count} pts)\n\n", style="dim")

                    # Share Price sparkline
                    if share_prices and len(share_prices) >= 2:
                        output.append("Share$     ", style="green dim")
                        output.append_text(make_sparkline(share_prices, width=20, color="green", as_percent=False))
                        output.append("\n")

                        # Calculate implied APY from share price growth
                        if len(share_prices) >= 2:
                            days = (timeseries[-1].timestamp - timeseries[0].timestamp).days or 1
                            total_return = (share_prices[-1] / share_prices[0]) - 1
                            implied_apy = ((1 + total_return) ** (365 / days) - 1) * 100
                            output.append(f"           Implied APY: ", style="dim")
                            apy_color = "green" if implied_apy > 0 else "red"
                            output.append(f"{implied_apy:.2f}%\n", style=apy_color)

                    # TVL sparkline
                    if tvl_data and len(tvl_data) >= 2:
                        output.append("TVL        ", style="cyan dim")
                        output.append_text(make_sparkline_usd(tvl_data, width=20, color="cyan"))
                        output.append("\n")

            # KPIs derived from share price
            share_prices = [float(p.share_price) for p in timeseries if p.share_price] if timeseries else []

            if share_prices and len(share_prices) >= 2:
                output.append("\n")
                output.append("─" * 44 + "\n", style="dim")
                output.append("PERFORMANCE KPIs\n", style="bold #ff8c00")
                output.append("─" * 44 + "\n", style="dim")

                import statistics

                # Calculate period returns from share price
                returns = []
                for i in range(1, len(share_prices)):
                    r = (share_prices[i] / share_prices[i-1]) - 1
                    returns.append(r * 100)

                # Total return
                total_return = ((share_prices[-1] / share_prices[0]) - 1) * 100
                output.append(f"Total Return: ", style="dim")
                color = "green" if total_return >= 0 else "red"
                output.append(f"{total_return:+.4f}%\n", style=color)

                # Time period
                if timeseries:
                    days = (timeseries[-1].timestamp - timeseries[0].timestamp).days or 1
                    output.append(f"Period: ", style="dim")
                    output.append(f"{days} days\n", style="white")

                    # Annualized return (implied APY)
                    annualized = ((1 + total_return / 100) ** (365 / days) - 1) * 100
                    output.append(f"Annualized Return: ", style="dim")
                    ann_color = "green" if annualized > 0 else "red"
                    output.append(f"{annualized:.2f}%\n", style=ann_color)

                if len(returns) > 1:
                    avg_return = sum(returns) / len(returns)
                    return_vol = statistics.stdev(returns)

                    output.append(f"\nAvg Daily Return: ", style="dim")
                    output.append(f"{avg_return:.4f}%\n", style="white")

                    output.append(f"Daily Volatility: ", style="dim")
                    output.append(f"{return_vol:.4f}%\n", style="white")

                    # Annualized volatility (assuming daily data)
                    ann_vol = return_vol * (365 ** 0.5)
                    output.append(f"Ann. Volatility: ", style="dim")
                    output.append(f"{ann_vol:.2f}%\n", style="white")

                    # Max Drawdown
                    peak = share_prices[0]
                    max_dd = 0
                    for price in share_prices:
                        if price > peak:
                            peak = price
                        dd = (peak - price) / peak * 100
                        if dd > max_dd:
                            max_dd = dd

                    output.append(f"Max Drawdown: ", style="dim")
                    dd_color = "red" if max_dd > 5 else "yellow" if max_dd > 1 else "green"
                    output.append(f"-{max_dd:.2f}%\n", style=dd_color)

                    # Sharpe Ratio (with 0% risk-free, it's simply return/volatility)
                    if ann_vol > 0 and timeseries:
                        days = (timeseries[-1].timestamp - timeseries[0].timestamp).days or 1
                        annualized = ((1 + total_return / 100) ** (365 / days) - 1) * 100

                        sharpe = annualized / ann_vol
                        output.append(f"\nSharpe Ratio: ", style="dim")
                        sharpe_color = "green" if sharpe > 0 else "red"
                        output.append(f"{sharpe:.2f}\n", style=sharpe_color)

                        # Sortino Ratio (only downside volatility)
                        downside_returns = [r for r in returns if r < 0]
                        if len(downside_returns) > 1:
                            downside_vol = statistics.stdev(downside_returns) * (365 ** 0.5)
                            if downside_vol > 0:
                                sortino = annualized / downside_vol
                                output.append(f"Sortino Ratio: ", style="dim")
                                sortino_color = "green" if sortino > 0 else "red"
                                output.append(f"{sortino:.2f}\n", style=sortino_color)

            kpi_widget.update(output)

        except Exception as e:
            logger.error(f"Vault details error: {e}")
            kpi_widget.update(f"Error: {e}")

    def action_show_history(self) -> None:
        """Open the historical data screen for the selected vault."""
        if self._selected_vault is None:
            return

        self.app.push_screen(VaultHistoricalScreen(self._selected_vault))
