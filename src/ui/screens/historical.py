"""Historical data screen with detailed charts."""

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
from src.core.models import Market, TimeseriesPoint
from src.data.pipeline import DataPipeline

logger = logging.getLogger(__name__)


class HistoricalScreen(Screen):
    """Screen for displaying detailed historical data with charts."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    HistoricalScreen {
        background: #000000;
    }
    #historical-main {
        layout: vertical;
        height: 100%;
        padding: 1;
    }
    #header-section {
        height: 4;
        background: #111;
        padding: 1;
    }
    #header-section Label {
        color: #ff8c00;
        text-style: bold;
    }
    #charts-container {
        height: 1fr;
        padding: 1;
    }
    .chart-box {
        border: solid #333;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }
    #loading {
        height: 3;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: #111;
        color: #888;
        padding: 0 1;
    }
    """

    def __init__(self, market: Market, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.market = market
        self.settings = get_settings()
        self.pipeline = DataPipeline(settings=self.settings)
        self._timeseries: List[TimeseriesPoint] = []
        self._loading = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="historical-main"):
            with Vertical(id="header-section"):
                yield Label(f"📊 Historical Data: {self.market.name}")
                yield Label(f"Market ID: {self.market.id[:20]}...", classes="dim")

            with ScrollableContainer(id="charts-container"):
                yield Static("Loading...", id="loading")
                yield Static("", id="chart-borrow-rate", classes="chart-box")
                yield Static("", id="chart-supply-rate", classes="chart-box")
                yield Static("", id="chart-utilization", classes="chart-box")
                yield Static("", id="chart-stats", classes="chart-box")

        yield Static("R to refresh, ESC to close", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Load data when screen is mounted."""
        await self._load_data()

    async def _load_data(self) -> None:
        """Load historical data from GraphQL API."""
        loading = self.query_one("#loading", Static)
        loading.update("⏳ Fetching timeseries data...")

        # Hide charts while loading
        for chart_id in ["#chart-borrow-rate", "#chart-supply-rate", "#chart-utilization", "#chart-stats"]:
            self.query_one(chart_id, Static).update("")

        try:
            self._timeseries = await self.pipeline.get_market_timeseries(self.market.id)

            if self._timeseries:
                loading.update("")
                await self._render_charts()
            else:
                loading.update("No historical data found. The market may be new or have low activity.")

        except ValueError as e:
            loading.update(f"⚠️ {str(e)}")
        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            loading.update(f"❌ Error: {str(e)}")

    async def _render_charts(self) -> None:
        """Render all charts."""
        if not self._timeseries:
            return

        # Extract data from TimeseriesPoint objects
        borrow_rates = [float(p.borrow_apy) * 100 for p in self._timeseries]  # Convert to %
        supply_rates = [float(p.supply_apy) * 100 for p in self._timeseries]  # Convert to %
        utilizations = [float(p.utilization) * 100 for p in self._timeseries]  # Convert to %

        # Calculate period in days
        if len(self._timeseries) >= 2:
            first_ts = self._timeseries[0].timestamp
            last_ts = self._timeseries[-1].timestamp
            period_days = (last_ts - first_ts).days or 1
        else:
            period_days = 1

        # Render borrow rate chart
        borrow_chart = self._create_line_chart(
            y_data=borrow_rates,
            title=f"Borrow APY (%) - {period_days} Days",
            color=acp.red,
            height=10,
        )
        self.query_one("#chart-borrow-rate", Static).update(borrow_chart)

        # Render supply rate chart
        supply_chart = self._create_line_chart(
            y_data=supply_rates,
            title=f"Supply APY (%) - {period_days} Days",
            color=acp.green,
            height=10,
        )
        self.query_one("#chart-supply-rate", Static).update(supply_chart)

        # Render utilization chart
        util_chart = self._create_line_chart(
            y_data=utilizations,
            title=f"Utilization (%) - {period_days} Days",
            color=acp.yellow,
            height=10,
        )
        self.query_one("#chart-utilization", Static).update(util_chart)

        # Statistics summary
        stats_summary = self._create_stats_summary()
        self.query_one("#chart-stats", Static).update(stats_summary)

        # Update status
        status = self.query_one("#status-bar", Static)
        status.update(f"{len(self._timeseries)} data points | {period_days} days | R to refresh, ESC to close")

    def _create_line_chart(
        self,
        y_data: List[float],
        title: str,
        color: int = acp.red,
        height: int = 12,
    ) -> Text:
        """Create an ASCII line chart using asciichartpy."""
        if not y_data:
            return Text("No data available", style="dim")

        # Resample data if too many points (max ~80 for good display)
        max_points = 80
        if len(y_data) > max_points:
            step = len(y_data) / max_points
            y_data = [y_data[int(i * step)] for i in range(max_points)]

        # Create chart with asciichartpy
        config = {
            'height': height,
            'colors': [color],
            'format': '{:8.2f}',
        }

        chart_str = acp.plot(y_data, config)

        # Build output with title
        output = Text()
        output.append(f"  {title}\n", style="bold #ff8c00")
        output.append_text(Text.from_ansi(chart_str))

        return output

    def _create_stats_summary(self) -> Text:
        """Create a summary of historical data statistics."""
        output = Text()
        output.append("─" * 50 + "\n", style="dim")
        output.append("STATISTICS SUMMARY\n", style="bold #ff8c00")
        output.append("─" * 50 + "\n", style="dim")

        if self._timeseries:
            first = self._timeseries[0]
            last = self._timeseries[-1]

            output.append(f"\nPeriod: ", style="dim")
            output.append(f"{first.timestamp.strftime('%Y-%m-%d')} → {last.timestamp.strftime('%Y-%m-%d')}\n", style="white")

            output.append(f"Data Points: ", style="dim")
            output.append(f"{len(self._timeseries)}\n", style="cyan")

            # Borrow rate change
            first_borrow = float(first.borrow_apy) * 100
            last_borrow = float(last.borrow_apy) * 100
            borrow_change = last_borrow - first_borrow
            borrow_color = "green" if borrow_change < 0 else "red"

            output.append(f"\nBorrow APY: ", style="bold red")
            output.append(f"{first_borrow:.2f}% → {last_borrow:.2f}% ", style="white")
            output.append(f"({borrow_change:+.2f}%)\n", style=borrow_color)

            borrow_rates = [float(p.borrow_apy) * 100 for p in self._timeseries]
            output.append(f"  Min: {min(borrow_rates):.2f}%  ", style="dim")
            output.append(f"Max: {max(borrow_rates):.2f}%  ", style="dim")
            output.append(f"Avg: {sum(borrow_rates)/len(borrow_rates):.2f}%\n", style="dim")

            # Supply rate change
            first_supply = float(first.supply_apy) * 100
            last_supply = float(last.supply_apy) * 100
            supply_change = last_supply - first_supply
            supply_color = "green" if supply_change > 0 else "red"

            output.append(f"\nSupply APY: ", style="bold green")
            output.append(f"{first_supply:.2f}% → {last_supply:.2f}% ", style="white")
            output.append(f"({supply_change:+.2f}%)\n", style=supply_color)

            supply_rates = [float(p.supply_apy) * 100 for p in self._timeseries]
            output.append(f"  Min: {min(supply_rates):.2f}%  ", style="dim")
            output.append(f"Max: {max(supply_rates):.2f}%  ", style="dim")
            output.append(f"Avg: {sum(supply_rates)/len(supply_rates):.2f}%\n", style="dim")

            # Utilization change
            first_util = float(first.utilization) * 100
            last_util = float(last.utilization) * 100
            util_change = last_util - first_util

            output.append(f"\nUtilization: ", style="bold yellow")
            output.append(f"{first_util:.1f}% → {last_util:.1f}% ", style="white")
            output.append(f"({util_change:+.1f}%)\n", style="yellow")

            utils = [float(p.utilization) * 100 for p in self._timeseries]
            output.append(f"  Min: {min(utils):.1f}%  ", style="dim")
            output.append(f"Max: {max(utils):.1f}%  ", style="dim")
            output.append(f"Avg: {sum(utils)/len(utils):.1f}%\n", style="dim")

        else:
            output.append("\nNo data found for this market.\n", style="dim")

        return output

    def action_refresh(self) -> None:
        """Refresh data."""
        asyncio.create_task(self._load_data())

    def action_close(self) -> None:
        """Close the screen."""
        self.app.pop_screen()
