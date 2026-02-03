"""Aave v3 protocol screen for Lending & Borrowing category."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import TabbedContent, TabPane, DataTable

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.data.clients.base import ProtocolType
from src.ui.screens.lending.base import LendingProtocolScreen
from src.ui.screens.markets import MarketsScreen

logger = logging.getLogger(__name__)


class AaveLendingScreen(LendingProtocolScreen):
    """Aave v3 protocol screen with Markets tab.

    Note: Aave doesn't have MetaMorpho-style vaults, so only Markets tab is shown.
    """

    DEFAULT_CSS = """
    AaveLendingScreen {
        height: 100%;
        width: 100%;
    }
    AaveLendingScreen > TabbedContent {
        height: 100%;
    }
    AaveLendingScreen TabPane {
        height: 100%;
    }
    AaveLendingScreen ContentSwitcher {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("m", "show_markets", "Markets"),
    ]

    def __init__(
        self,
        pipeline: DataPipeline,
        settings: Settings,
        *args,
        **kwargs
    ):
        super().__init__(pipeline, settings, *args, **kwargs)

    @property
    def protocol_type(self) -> ProtocolType:
        return ProtocolType.AAVE

    @property
    def protocol_name(self) -> str:
        return "Aave v3"

    @property
    def supports_vaults(self) -> bool:
        return False

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="aave-markets", id="aave-tabs"):
            with TabPane("Markets", id="aave-markets"):
                yield MarketsScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    protocol=ProtocolType.AAVE,
                    id="aave-markets-screen"
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

        markets_screen = self.query_one("#aave-markets-screen", MarketsScreen)
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
        """Handle tab switches within Aave."""
        pane_id = event.pane.id if event.pane else None

        if pane_id == "aave-markets":
            markets_screen = self.query_one("#aave-markets-screen", MarketsScreen)
            if not markets_screen._markets:
                await markets_screen.refresh_data()
            try:
                table = markets_screen.query_one("#markets-table", DataTable)
                table.focus()
            except Exception:
                pass

    async def refresh_data(self) -> None:
        """Refresh data for the active tab."""
        try:
            markets_screen = self.query_one("#aave-markets-screen", MarketsScreen)
            await markets_screen.refresh_data()
        except Exception as e:
            logger.error(f"Error refreshing Aave data: {e}")

    def action_show_markets(self) -> None:
        """Switch to markets tab."""
        self.query_one("#aave-tabs", TabbedContent).active = "aave-markets"

    def action_show_vaults(self) -> None:
        """Aave doesn't support vaults."""
        pass
