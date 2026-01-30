"""Morpho protocol screen containing Markets and Vaults tabs."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane, DataTable

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.ui.screens.markets import MarketsScreen
from src.ui.screens.vaults import VaultsScreen

logger = logging.getLogger(__name__)


class MorphoScreen(Widget):
    """Morpho protocol screen with Markets and Vaults tabs."""

    DEFAULT_CSS = """
    MorphoScreen {
        height: 100%;
        width: 100%;
    }
    MorphoScreen > TabbedContent {
        height: 100%;
    }
    MorphoScreen TabPane {
        height: 100%;
    }
    MorphoScreen ContentSwitcher {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("m", "show_markets", "Markets"),
        Binding("v", "show_vaults", "Vaults"),
    ]

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
        self._initialized = False

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="morpho-markets", id="morpho-tabs"):
            with TabPane("Markets", id="morpho-markets"):
                yield MarketsScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="morpho-markets-screen"
                )
            with TabPane("Vaults", id="morpho-vaults"):
                yield VaultsScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="morpho-vaults-screen"
                )

    async def on_mount(self) -> None:
        """Initialize when mounted."""
        if not self._initialized:
            await self.initialize()

    async def initialize(self) -> None:
        """Load initial data for markets."""
        if self._initialized:
            return
        self._initialized = True

        markets_screen = self.query_one("#morpho-markets-screen", MarketsScreen)
        await markets_screen.refresh_data()

        # Focus the markets table
        try:
            table = markets_screen.query_one("#markets-table", DataTable)
            table.focus()
        except Exception:
            pass

    async def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Handle tab switches within Morpho."""
        pane_id = event.pane.id if event.pane else None

        if pane_id == "morpho-markets":
            markets_screen = self.query_one("#morpho-markets-screen", MarketsScreen)
            if not markets_screen._markets:
                await markets_screen.refresh_data()
            try:
                table = markets_screen.query_one("#markets-table", DataTable)
                table.focus()
            except Exception:
                pass

        elif pane_id == "morpho-vaults":
            vaults_screen = self.query_one("#morpho-vaults-screen", VaultsScreen)
            if not vaults_screen._vaults:
                await vaults_screen.refresh_data()
            try:
                table = vaults_screen.query_one("#vaults-table", DataTable)
                table.focus()
            except Exception:
                pass

    async def refresh_data(self) -> None:
        """Refresh data for the active tab."""
        try:
            tabbed = self.query_one("#morpho-tabs", TabbedContent)
            if tabbed.active == "morpho-markets":
                markets_screen = self.query_one("#morpho-markets-screen", MarketsScreen)
                await markets_screen.refresh_data()
            else:
                vaults_screen = self.query_one("#morpho-vaults-screen", VaultsScreen)
                await vaults_screen.refresh_data()
        except Exception as e:
            logger.error(f"Error refreshing Morpho data: {e}")

    def action_show_markets(self) -> None:
        """Switch to markets tab."""
        self.query_one("#morpho-tabs", TabbedContent).active = "morpho-markets"

    def action_show_vaults(self) -> None:
        """Switch to vaults tab."""
        self.query_one("#morpho-tabs", TabbedContent).active = "morpho-vaults"
