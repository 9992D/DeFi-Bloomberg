"""Main Textual application for DeFi Protocol Tracker."""

import asyncio
import logging
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane

from config.settings import get_settings
from src.data.pipeline import DataPipeline
from src.ui.screens.lending.category import LendingCategoryScreen
from src.ui.screens.sandbox import SandboxScreen

# Suppress INFO logs in UI - only show warnings and errors
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class DeFiTrackerApp(App):
    """Bloomberg-style Terminal UI for monitoring DeFi protocol positions."""

    TITLE = "DeFi Protocol Tracker"

    CSS = """
    Screen { background: #000000; }

    /* Tab styling */
    TabbedContent {
        height: 100%;
    }
    TabbedContent Tabs {
        background: #111;
    }
    TabbedContent Tab {
        background: #111;
        color: #888;
        padding: 0 2;
    }
    TabbedContent Tab:hover {
        background: #222;
        color: #ff8c00;
    }
    TabbedContent Tab.-active {
        background: #222;
        color: #ff8c00;
        text-style: bold;
    }
    TabbedContent Underline {
        background: #333;
    }
    TabbedContent Underline .underline--bar {
        background: #ff8c00;
    }
    TabbedContent TabPane {
        height: 100%;
    }
    TabbedContent ContentSwitcher {
        height: 100%;
    }

    #status {
        dock: bottom;
        height: 1;
        background: #111;
        color: #888;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "show_lending", "Lending"),
        Binding("2", "show_sandbox", "Sandbox"),
        Binding("m", "show_markets", "Markets"),
        Binding("v", "show_vaults", "Vaults"),
    ]

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.pipeline = DataPipeline(settings=self.settings)
        self._active_tab = "lending"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="tab-lending", id="main-tabs"):
            with TabPane("Lending & Borrowing", id="tab-lending"):
                yield LendingCategoryScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="lending-screen"
                )
            with TabPane("Sandbox", id="tab-sandbox"):
                yield SandboxScreen(
                    pipeline=self.pipeline,
                    settings=self.settings,
                    id="sandbox-screen"
                )
        yield Static(
            "1: Lending  2: Sandbox | M: Markets  V: Vaults | R: Refresh  Q: Quit",
            id="status"
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize after app is mounted."""
        lending_screen = self.query_one("#lending-screen", LendingCategoryScreen)
        await lending_screen.initialize()

    async def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Handle main tab switches."""
        pane_id = event.pane.id if event.pane else None

        if pane_id == "tab-lending":
            self._active_tab = "lending"
        elif pane_id == "tab-sandbox":
            self._active_tab = "sandbox"

    async def action_refresh(self) -> None:
        """Refresh data for the current view."""
        try:
            if self._active_tab == "lending":
                lending_screen = self.query_one("#lending-screen", LendingCategoryScreen)
                await lending_screen.refresh_data()
        except Exception as e:
            logger.error(f"Error refreshing: {e}")

    def action_show_lending(self) -> None:
        """Switch to Lending & Borrowing tab."""
        self.query_one("#main-tabs", TabbedContent).active = "tab-lending"

    def action_show_sandbox(self) -> None:
        """Switch to Sandbox tab."""
        self.query_one("#main-tabs", TabbedContent).active = "tab-sandbox"

    def action_show_markets(self) -> None:
        """Switch to markets tab."""
        self.action_show_lending()
        lending_screen = self.query_one("#lending-screen", LendingCategoryScreen)
        lending_screen.action_show_markets()

    def action_show_vaults(self) -> None:
        """Switch to vaults tab."""
        self.action_show_lending()
        lending_screen = self.query_one("#lending-screen", LendingCategoryScreen)
        lending_screen.action_show_vaults()


def main():
    DeFiTrackerApp().run()


if __name__ == "__main__":
    main()
