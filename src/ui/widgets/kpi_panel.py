"""KPI Panel widget for displaying market analytics."""

from typing import Optional, Dict

from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from textual.widgets import Static

from src.core.models import Market, MarketKPIs, KPIType, KPIStatus


class KPIPanel(Static):
    """
    Panel widget for displaying KPIs for a selected market.

    Shows all calculated KPIs with formatting and signal indicators.
    """

    # KPI display configuration
    KPI_CONFIG = {
        KPIType.VOLATILITY: {
            "name": "Volatility (Ann.)",
            "description": "Annualized rate volatility",
            "icon": "📊",
        },
        KPIType.SHARPE_RATIO: {
            "name": "Sharpe Ratio",
            "description": "Risk-adjusted return",
            "icon": "📈",
        },
        KPIType.SORTINO_RATIO: {
            "name": "Sortino Ratio",
            "description": "Downside risk-adjusted",
            "icon": "📉",
        },
        KPIType.ELASTICITY: {
            "name": "Rate Elasticity",
            "description": "Sensitivity at 90% util",
            "icon": "⚡",
        },
        KPIType.IRM_EVOLUTION: {
            "name": "Rate at Target",
            "description": "IRM rateAtTarget",
            "icon": "🎯",
        },
        KPIType.MEAN_REVERSION: {
            "name": "Mean Reversion",
            "description": "Half-life (hours)",
            "icon": "🔄",
        },
        KPIType.UTIL_ADJUSTED_RETURN: {
            "name": "Util-Adj Return",
            "description": "Risk-penalized yield",
            "icon": "💰",
        },
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._market: Optional[Market] = None
        self._kpis: Optional[MarketKPIs] = None

    def update_market(self, market: Market, kpis: Optional[MarketKPIs] = None) -> None:
        """
        Update the panel with a new market and its KPIs.

        Args:
            market: Market object
            kpis: Pre-calculated KPIs (optional)
        """
        self._market = market
        self._kpis = kpis
        self._render()

    def clear(self) -> None:
        """Clear the panel."""
        self._market = None
        self._kpis = None
        self.update(self._empty_panel())

    def _render(self) -> None:
        """Render the KPI panel content."""
        if self._market is None:
            self.update(self._empty_panel())
            return

        content = self._build_content()
        self.update(content)

    def _empty_panel(self) -> Panel:
        """Create empty state panel."""
        return Panel(
            Text("Select a market to view KPIs", style="dim italic", justify="center"),
            title="[bold orange1]KPI Analytics[/]",
            border_style="dim",
        )

    def _build_content(self) -> Panel:
        """Build the full KPI panel content."""
        # Market header
        header = Text()
        header.append(f"{self._market.name}\n", style="bold cyan")
        header.append(f"Supply: ", style="dim")
        header.append(f"{float(self._market.supply_apy)*100:.2f}%", style="green")
        header.append(f"  Borrow: ", style="dim")
        header.append(f"{float(self._market.borrow_apy)*100:.2f}%", style="red")
        header.append(f"  Util: ", style="dim")
        header.append(f"{float(self._market.utilization)*100:.1f}%\n", style="yellow")

        # KPI table
        table = Table(
            show_header=True,
            header_style="bold orange1",
            border_style="dim",
            expand=True,
            padding=(0, 1),
        )
        table.add_column("KPI", style="cyan", width=18)
        table.add_column("Value", justify="right", width=12)
        table.add_column("Signal", justify="center", width=8)

        if self._kpis:
            for kpi_type in KPIType:
                result = self._kpis.get(kpi_type)
                config = self.KPI_CONFIG.get(kpi_type, {})

                name = config.get("name", kpi_type.value)

                if result is None:
                    value = Text("--", style="dim")
                    signal = Text("", style="dim")
                elif result.status == KPIStatus.SUCCESS:
                    value = Text(result.display_value, style=self._value_style(result.signal))
                    signal = Text(self._signal_icon(result.signal), style=self._signal_style(result.signal))
                elif result.status == KPIStatus.INSUFFICIENT_DATA:
                    value = Text("N/A", style="dim")
                    signal = Text("⚠", style="yellow")
                else:
                    value = Text("ERR", style="red")
                    signal = Text("✗", style="red")

                table.add_row(name, value, signal)
        else:
            # No KPIs calculated yet
            for kpi_type in KPIType:
                config = self.KPI_CONFIG.get(kpi_type, {})
                name = config.get("name", kpi_type.value)
                table.add_row(name, Text("...", style="dim"), Text("", style="dim"))

        return Panel(
            header + Text("\n") + table,
            title="[bold orange1]KPI Analytics[/]",
            border_style="orange1",
        )

    def _value_style(self, signal: str) -> str:
        """Get style for KPI value based on signal."""
        return {
            "positive": "green bold",
            "negative": "red bold",
            "neutral": "white",
        }.get(signal, "white")

    def _signal_style(self, signal: str) -> str:
        """Get style for signal indicator."""
        return {
            "positive": "green",
            "negative": "red",
            "neutral": "dim",
        }.get(signal, "dim")

    def _signal_icon(self, signal: str) -> str:
        """Get icon for signal."""
        return {
            "positive": "▲",
            "negative": "▼",
            "neutral": "◆",
        }.get(signal, "◆")


class KPIDetailPanel(Static):
    """
    Detailed KPI panel showing metadata and calculations.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._kpi_type: Optional[KPIType] = None
        self._kpis: Optional[MarketKPIs] = None

    def show_kpi_detail(self, kpi_type: KPIType, kpis: MarketKPIs) -> None:
        """Show detailed view for a specific KPI."""
        self._kpi_type = kpi_type
        self._kpis = kpis
        self._render()

    def _render(self) -> None:
        """Render the detail panel."""
        if not self._kpi_type or not self._kpis:
            self.update("")
            return

        result = self._kpis.get(self._kpi_type)
        if not result:
            self.update("")
            return

        config = KPIPanel.KPI_CONFIG.get(self._kpi_type, {})

        content = Text()
        content.append(f"{config.get('name', self._kpi_type.value)}\n", style="bold cyan")
        content.append(f"{config.get('description', '')}\n\n", style="dim italic")

        content.append("Value: ", style="dim")
        content.append(f"{result.display_value}\n", style="bold")

        content.append("Status: ", style="dim")
        content.append(f"{result.status.value}\n", style="green" if result.is_valid else "red")

        if result.window_hours:
            content.append("Window: ", style="dim")
            content.append(f"{result.window_hours} hours\n", style="white")

        if result.metadata:
            content.append("\nMetadata:\n", style="dim")
            for key, value in result.metadata.items():
                if isinstance(value, float):
                    value = f"{value:.4f}"
                content.append(f"  {key}: ", style="dim")
                content.append(f"{value}\n", style="white")

        self.update(Panel(content, title="[bold]KPI Detail[/]", border_style="dim"))
