"""Base class for lending protocol screens."""

from textual.app import ComposeResult
from textual.widget import Widget

from config.settings import Settings
from src.data.pipeline import DataPipeline
from src.data.clients.base import ProtocolType


class LendingProtocolScreen(Widget):
    """Base class for lending protocol screens.

    All lending protocol screens (Morpho, Aave, Euler, etc.) should inherit
    from this class to ensure consistent interface and behavior.

    Subclasses must override:
    - protocol_type (property)
    - protocol_name (property)
    - compose()
    - initialize()
    - refresh_data()
    - action_show_markets()
    """

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

    @property
    def protocol_type(self) -> ProtocolType:
        """Return the protocol type for this screen."""
        raise NotImplementedError("Subclasses must implement protocol_type")

    @property
    def protocol_name(self) -> str:
        """Return a human-readable protocol name."""
        raise NotImplementedError("Subclasses must implement protocol_name")

    @property
    def supports_vaults(self) -> bool:
        """Return True if this protocol supports vaults.

        Default implementation checks the protocol client.
        """
        client = self.pipeline.get_client(self.protocol_type)
        return client.supports_vaults

    def compose(self) -> ComposeResult:
        """Compose the screen's widgets."""
        raise NotImplementedError("Subclasses must implement compose")

    async def initialize(self) -> None:
        """Initialize the screen with data.

        Should be called after the screen is mounted.
        """
        raise NotImplementedError("Subclasses must implement initialize")

    async def refresh_data(self) -> None:
        """Refresh the screen's data."""
        raise NotImplementedError("Subclasses must implement refresh_data")

    def action_show_markets(self) -> None:
        """Switch to markets view."""
        raise NotImplementedError("Subclasses must implement action_show_markets")

    def action_show_vaults(self) -> None:
        """Switch to vaults view.

        Default implementation does nothing for protocols without vaults.
        """
        pass
