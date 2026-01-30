"""Market DataTable widget."""

from decimal import Decimal
from typing import List, Optional, Callable

from rich.text import Text
from textual.widgets import DataTable
from textual.coordinate import Coordinate

from src.core.models import Market


class MarketTable(DataTable):
    """
    DataTable widget for displaying Morpho Blue markets.

    Shows market name, rates, utilization, and TVL.
    """

    COLUMNS = [
        ("Market", 20),
        ("Supply APY", 12),
        ("Borrow APY", 12),
        ("Utilization", 12),
        ("TVL", 15),
        ("LLTV", 8),
    ]

    def __init__(
        self,
        on_market_select: Optional[Callable[[Market], None]] = None,
        **kwargs,
    ):
        super().__init__(
            cursor_type="row",
            zebra_stripes=True,
            **kwargs,
        )
        self._markets: List[Market] = []
        self._on_market_select = on_market_select

    def on_mount(self) -> None:
        """Set up columns when widget is mounted."""
        for name, width in self.COLUMNS:
            self.add_column(name, width=width)

    def load_markets(self, markets: List[Market]) -> None:
        """
        Load markets into the table.

        Args:
            markets: List of Market objects to display
        """
        self._markets = markets
        self.clear()

        for market in markets:
            self.add_row(
                self._format_market_name(market),
                self._format_rate(market.supply_apy, "positive"),
                self._format_rate(market.borrow_apy, "negative"),
                self._format_utilization(market.utilization),
                self._format_tvl(market.total_supply_usd),
                self._format_lltv(market.lltv),
                key=market.id,
            )

    def refresh_market(self, market: Market) -> None:
        """
        Update a single market row.

        Args:
            market: Updated Market object
        """
        # Find the row index
        for idx, m in enumerate(self._markets):
            if m.id == market.id:
                self._markets[idx] = market
                # Update the row
                self.update_cell_at(
                    Coordinate(idx, 1),
                    self._format_rate(market.supply_apy, "positive"),
                )
                self.update_cell_at(
                    Coordinate(idx, 2),
                    self._format_rate(market.borrow_apy, "negative"),
                )
                self.update_cell_at(
                    Coordinate(idx, 3),
                    self._format_utilization(market.utilization),
                )
                break

    def get_selected_market(self) -> Optional[Market]:
        """Get the currently selected market."""
        if self.cursor_row is not None and self.cursor_row < len(self._markets):
            return self._markets[self.cursor_row]
        return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        if self._on_market_select and event.row_key:
            market = next(
                (m for m in self._markets if m.id == event.row_key.value),
                None,
            )
            if market:
                self._on_market_select(market)

    def _format_market_name(self, market: Market) -> Text:
        """Format market name with styling."""
        return Text(market.name, style="bold")

    def _format_rate(self, rate: Decimal, rate_type: str) -> Text:
        """Format rate as percentage with color."""
        if rate is None or rate == 0:
            return Text("--", style="dim")

        pct = float(rate) * 100
        text = f"{pct:.2f}%"

        if rate_type == "positive":
            style = "green" if pct > 5 else "yellow" if pct > 2 else "dim"
        else:
            style = "red" if pct > 10 else "yellow" if pct > 5 else "dim"

        return Text(text, style=style)

    def _format_utilization(self, util: Decimal) -> Text:
        """Format utilization with color coding."""
        if util is None:
            return Text("--", style="dim")

        pct = float(util) * 100
        text = f"{pct:.1f}%"

        # Color based on distance from 90% target
        if pct >= 95:
            style = "red bold"
        elif pct >= 90:
            style = "yellow"
        elif pct >= 80:
            style = "green"
        else:
            style = "cyan"

        return Text(text, style=style)

    def _format_tvl(self, tvl: Decimal) -> Text:
        """Format TVL with appropriate units."""
        if tvl is None or tvl == 0:
            return Text("--", style="dim")

        value = float(tvl)

        if value >= 1_000_000_000:
            text = f"${value/1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            text = f"${value/1_000_000:.2f}M"
        elif value >= 1_000:
            text = f"${value/1_000:.2f}K"
        else:
            text = f"${value:.2f}"

        return Text(text, style="bold")

    def _format_lltv(self, lltv: Decimal) -> Text:
        """Format LLTV percentage."""
        if lltv is None:
            return Text("--", style="dim")

        pct = float(lltv) * 100
        return Text(f"{pct:.0f}%", style="cyan")
