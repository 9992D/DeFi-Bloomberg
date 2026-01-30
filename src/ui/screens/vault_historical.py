"""Historical data screen for vaults with detailed charts."""

import asyncio
import logging
from typing import List

import asciichartpy as acp
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Label
from rich.text import Text

from config.settings import get_settings
from src.core.models import Vault, VaultTimeseriesPoint
from src.data.pipeline import DataPipeline

logger = logging.getLogger(__name__)


class VaultHistoricalScreen(Screen):
    """Screen for displaying detailed vault historical data with charts."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    VaultHistoricalScreen {
        background: #000000;
    }
    #vault-historical-main {
        layout: vertical;
        height: 100%;
        padding: 1;
    }
    #vault-header-section {
        height: 4;
        background: #111;
        padding: 1;
    }
    #vault-header-section Label {
        color: #ff8c00;
        text-style: bold;
    }
    #vault-charts-container {
        height: 1fr;
        padding: 1;
    }
    .chart-box {
        border: solid #333;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }
    #vault-loading {
        height: 3;
    }
    #vault-status-bar {
        dock: bottom;
        height: 1;
        background: #111;
        color: #888;
        padding: 0 1;
    }
    """

    def __init__(self, vault: Vault, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vault = vault
        self.settings = get_settings()
        self.pipeline = DataPipeline(settings=self.settings)
        self._timeseries: List[VaultTimeseriesPoint] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="vault-historical-main"):
            with Vertical(id="vault-header-section"):
                yield Label(f"📊 Historical Data: {self.vault.name}")
                yield Label(f"Vault: {self.vault.id[:20]}...", classes="dim")

            with ScrollableContainer(id="vault-charts-container"):
                yield Static("Loading...", id="vault-loading")
                yield Static("", id="chart-share-price", classes="chart-box")
                yield Static("", id="chart-tvl", classes="chart-box")
                yield Static("", id="chart-stats", classes="chart-box")

        yield Static("R to refresh, ESC to close", id="vault-status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Load data when screen is mounted."""
        await self._load_data()

    async def _load_data(self) -> None:
        """Load historical data from GraphQL API."""
        loading = self.query_one("#vault-loading", Static)
        loading.update("⏳ Fetching vault timeseries data...")

        for chart_id in ["#chart-share-price", "#chart-tvl", "#chart-stats"]:
            self.query_one(chart_id, Static).update("")

        try:
            self._timeseries = await self.pipeline.get_vault_timeseries(self.vault.id)

            if self._timeseries:
                loading.update("")
                await self._render_charts()
            else:
                loading.update("No historical data found for this vault.")

        except ValueError as e:
            loading.update(f"⚠️ {str(e)}")
        except Exception as e:
            logger.error(f"Error loading vault historical data: {e}")
            loading.update(f"❌ Error: {str(e)}")

    async def _render_charts(self) -> None:
        """Render all charts."""
        if not self._timeseries:
            return

        # Extract data - focus on share price and TVL
        share_prices = [float(p.share_price) if p.share_price else None for p in self._timeseries]
        total_assets = [float(p.total_assets) for p in self._timeseries]

        # Calculate period
        if len(self._timeseries) >= 2:
            first_ts = self._timeseries[0].timestamp
            last_ts = self._timeseries[-1].timestamp
            period_days = (last_ts - first_ts).days or 1
        else:
            period_days = 1

        # Share Price Chart (primary)
        valid_prices = [p for p in share_prices if p is not None]
        if valid_prices:
            share_chart = self._create_line_chart(
                y_data=valid_prices,
                title=f"Share Price - {period_days} Days ({len(valid_prices)} pts)",
                color=acp.green,
                height=12,
                format_str='{:8.6f}',
            )
            self.query_one("#chart-share-price", Static).update(share_chart)

        # TVL Chart (normalize to millions for display)
        asset_decimals = self.vault.asset_decimals
        valid_tvl = [t for t in total_assets if t and t > 0]
        if valid_tvl:
            tvl_millions = [t / (10 ** asset_decimals) / 1_000_000 for t in valid_tvl]
            tvl_chart = self._create_line_chart(
                y_data=tvl_millions,
                title=f"TVL (Millions {self.vault.asset_symbol}) - {period_days} Days ({len(valid_tvl)} pts)",
                color=acp.cyan,
                height=10,
                format_str='{:8.2f}',
            )
            self.query_one("#chart-tvl", Static).update(tvl_chart)

        # Stats summary
        stats = self._create_stats_summary(valid_prices, period_days)
        self.query_one("#chart-stats", Static).update(stats)

        # Update status
        pts_count = max(len(valid_prices), len(valid_tvl)) if valid_prices or valid_tvl else 0
        status = self.query_one("#vault-status-bar", Static)
        status.update(f"{pts_count} data points | {period_days} days | R to refresh, ESC to close")

    def _create_line_chart(
        self,
        y_data: List[float],
        title: str,
        color: int = acp.green,
        height: int = 10,
        format_str: str = '{:8.2f}',
    ) -> Text:
        """Create an ASCII line chart using asciichartpy."""
        if not y_data:
            return Text("No data available", style="dim")

        # Resample if too many points
        max_points = 80
        if len(y_data) > max_points:
            step = len(y_data) / max_points
            y_data = [y_data[int(i * step)] for i in range(max_points)]

        config = {
            'height': height,
            'colors': [color],
            'format': format_str,
        }

        chart_str = acp.plot(y_data, config)

        output = Text()
        output.append(f"  {title}\n", style="bold #ff8c00")
        output.append_text(Text.from_ansi(chart_str))

        return output

    def _create_stats_summary(self, share_prices: List[float], period_days: int) -> Text:
        """Create a summary of vault statistics."""
        import statistics

        output = Text()
        output.append("─" * 50 + "\n", style="dim")
        output.append("PERFORMANCE SUMMARY\n", style="bold #ff8c00")
        output.append("─" * 50 + "\n", style="dim")

        if self._timeseries:
            first = self._timeseries[0]
            last = self._timeseries[-1]

            output.append(f"\nPeriod: ", style="dim")
            output.append(f"{first.timestamp.strftime('%Y-%m-%d')} → {last.timestamp.strftime('%Y-%m-%d')}\n", style="white")

            output.append(f"Duration: ", style="dim")
            output.append(f"{period_days} days\n", style="cyan")

            output.append(f"Data Points: ", style="dim")
            output.append(f"{len(share_prices)} (share price)\n", style="cyan")

            # Share price stats
            if share_prices and len(share_prices) >= 2:
                first_price = share_prices[0]
                last_price = share_prices[-1]
                price_return = ((last_price / first_price) - 1) * 100
                return_color = "green" if price_return >= 0 else "red"

                output.append(f"\n── Share Price ──\n", style="bold green")
                output.append(f"Start: ", style="dim")
                output.append(f"${first_price:.6f}\n", style="white")
                output.append(f"End:   ", style="dim")
                output.append(f"${last_price:.6f}\n", style="white")

                output.append(f"\nTotal Return: ", style="dim")
                output.append(f"{price_return:+.4f}%\n", style=return_color)

                # Implied APY (annualized return)
                if period_days > 0:
                    implied_apy = ((1 + price_return / 100) ** (365 / period_days) - 1) * 100
                    apy_color = "green" if implied_apy > 0 else "red"
                    output.append(f"Implied APY: ", style="dim")
                    output.append(f"{implied_apy:.2f}%\n", style=f"bold {apy_color}")

                # Volatility and risk metrics
                if len(share_prices) > 2:
                    returns = []
                    for i in range(1, len(share_prices)):
                        r = (share_prices[i] / share_prices[i-1]) - 1
                        returns.append(r * 100)

                    if returns:
                        avg_return = sum(returns) / len(returns)
                        vol = statistics.stdev(returns)
                        ann_vol = vol * (365 ** 0.5)  # Annualized

                        output.append(f"\n── Risk Metrics ──\n", style="bold yellow")
                        output.append(f"Avg Daily Return: ", style="dim")
                        output.append(f"{avg_return:.4f}%\n", style="white")
                        output.append(f"Daily Volatility: ", style="dim")
                        output.append(f"{vol:.4f}%\n", style="white")
                        output.append(f"Ann. Volatility: ", style="dim")
                        output.append(f"{ann_vol:.2f}%\n", style="white")

                        # Max drawdown
                        peak = share_prices[0]
                        max_dd = 0
                        for price in share_prices:
                            if price > peak:
                                peak = price
                            dd = (peak - price) / peak * 100
                            if dd > max_dd:
                                max_dd = dd

                        dd_color = "red" if max_dd > 5 else "yellow" if max_dd > 1 else "green"
                        output.append(f"Max Drawdown: ", style="dim")
                        output.append(f"-{max_dd:.2f}%\n", style=dd_color)

                        # Sharpe ratio (with 0% risk-free, it's return/volatility)
                        if ann_vol > 0 and period_days > 0:
                            sharpe = implied_apy / ann_vol
                            sharpe_color = "green" if sharpe > 0 else "red"
                            output.append(f"Sharpe Ratio: ", style="dim")
                            output.append(f"{sharpe:.2f}\n", style=sharpe_color)

            # Current APY from API (for reference)
            output.append(f"\n── Current Rates ──\n", style="bold cyan")
            output.append(f"APY (API): ", style="dim")
            output.append(f"{float(self.vault.apy)*100:.2f}%\n", style="white")
            output.append(f"Net APY: ", style="dim")
            output.append(f"{float(self.vault.net_apy)*100:.2f}%\n", style="white")

        else:
            output.append("\nNo data found for this vault.\n", style="dim")

        return output

    def action_refresh(self) -> None:
        """Refresh data."""
        asyncio.create_task(self._load_data())

    def action_close(self) -> None:
        """Close the screen."""
        self.app.pop_screen()
