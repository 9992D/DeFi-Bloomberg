"""Lending & Borrowing category screen containing protocol sub-tabs."""

import logging
from typing import Dict, Optional, Type

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static, TabbedContent, TabPane, DataTable

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.data.clients.base import ProtocolType
from src.ui.screens.lending.base import LendingProtocolScreen

logger = logging.getLogger(__name__)


class LendingCategoryScreen(Widget):
    """Container screen for all lending protocol screens.

    Provides tabbed navigation between different lending protocols
    (Morpho, Aave, Euler, etc.).
    """

    DEFAULT_CSS = """
    LendingCategoryScreen {
        height: 100%;
        width: 100%;
    }
    LendingCategoryScreen > TabbedContent {
        height: 100%;
    }
    LendingCategoryScreen TabPane {
        height: 100%;
    }
    LendingCategoryScreen ContentSwitcher {
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
        self._active_protocol: Optional[ProtocolType] = None
        self._protocol_screens: Dict[ProtocolType, LendingProtocolScreen] = {}

    def compose(self) -> ComposeResult:
        """Compose the lending category with protocol tabs."""
        # Import here to avoid circular imports
        from src.ui.screens.lending.morpho import MorphoLendingScreen
        from src.ui.screens.lending.aave import AaveLendingScreen

        with TabbedContent(initial="lending-morpho", id="lending-tabs"):
            with TabPane("Morpho", id="lending-morpho"):
                screen = MorphoLendingScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="morpho-lending-screen"
                )
                self._protocol_screens[ProtocolType.MORPHO] = screen
                yield screen

            with TabPane("Aave", id="lending-aave"):
                aave_screen = AaveLendingScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="aave-lending-screen"
                )
                self._protocol_screens[ProtocolType.AAVE] = aave_screen
                yield aave_screen

            # Future protocol tabs would be added here:
            # with TabPane("Euler", id="lending-euler"):
            #     yield EulerLendingScreen(...)

    async def on_mount(self) -> None:
        """Initialize when mounted."""
        if not self._initialized:
            await self.initialize()

    async def initialize(self) -> None:
        """Load initial data for the active protocol."""
        if self._initialized:
            return
        self._initialized = True
        self._active_protocol = ProtocolType.MORPHO

        # Initialize the Morpho screen
        morpho_screen = self._protocol_screens.get(ProtocolType.MORPHO)
        if morpho_screen:
            await morpho_screen.initialize()

    async def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Handle tab switches between protocols."""
        pane_id = event.pane.id if event.pane else None

        if pane_id == "lending-morpho":
            self._active_protocol = ProtocolType.MORPHO
            screen = self._protocol_screens.get(ProtocolType.MORPHO)
            if screen and not screen._initialized:
                await screen.initialize()

        elif pane_id == "lending-aave":
            self._active_protocol = ProtocolType.AAVE
            screen = self._protocol_screens.get(ProtocolType.AAVE)
            if screen and not screen._initialized:
                await screen.initialize()

        # Future protocol handling:
        # elif pane_id == "lending-euler":
        #     self._active_protocol = ProtocolType.EULER
        #     ...

    def get_active_screen(self) -> Optional[LendingProtocolScreen]:
        """Get the currently active protocol screen."""
        if self._active_protocol:
            return self._protocol_screens.get(self._active_protocol)
        return None

    async def refresh_data(self) -> None:
        """Refresh data for the active protocol screen."""
        screen = self.get_active_screen()
        if screen:
            await screen.refresh_data()

    def action_show_markets(self) -> None:
        """Switch to markets tab in the active protocol screen."""
        screen = self.get_active_screen()
        if screen:
            screen.action_show_markets()

    def action_show_vaults(self) -> None:
        """Switch to vaults tab in the active protocol screen."""
        screen = self.get_active_screen()
        if screen and screen.supports_vaults:
            screen.action_show_vaults()

    def switch_to_protocol(self, protocol: ProtocolType) -> None:
        """Switch to a specific protocol tab."""
        tabbed = self.query_one("#lending-tabs", TabbedContent)
        tab_id = f"lending-{protocol.value}"
        tabbed.active = tab_id
