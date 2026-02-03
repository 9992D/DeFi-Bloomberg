"""Protocol client registry for managing protocol-specific clients.

Provides a factory pattern for creating and retrieving protocol clients,
enabling the data pipeline to work with multiple protocols seamlessly.
"""

import logging
from typing import Dict, Optional, Type, Callable

from config.settings import Settings, get_settings
from src.data.clients.base import ProtocolClient, ProtocolType

logger = logging.getLogger(__name__)


class ProtocolClientRegistry:
    """Registry for protocol clients with lazy initialization.

    Provides factory methods for creating protocol clients and
    manages client lifecycle.
    """

    _client_factories: Dict[ProtocolType, Callable[..., ProtocolClient]] = {}
    _instances: Dict[ProtocolType, ProtocolClient] = {}

    @classmethod
    def register(
        cls,
        protocol_type: ProtocolType,
        factory: Callable[..., ProtocolClient],
    ) -> None:
        """Register a client factory for a protocol type.

        Args:
            protocol_type: The protocol type to register
            factory: A callable that creates a ProtocolClient instance
        """
        cls._client_factories[protocol_type] = factory
        logger.debug(f"Registered client factory for {protocol_type.value}")

    @classmethod
    def get_client(
        cls,
        protocol_type: ProtocolType,
        settings: Optional[Settings] = None,
        *,
        force_new: bool = False,
    ) -> ProtocolClient:
        """Get or create a client for the specified protocol.

        Args:
            protocol_type: The protocol type to get a client for
            settings: Optional settings to pass to the client factory
            force_new: If True, create a new instance even if one exists

        Returns:
            A ProtocolClient instance for the specified protocol

        Raises:
            ValueError: If no factory is registered for the protocol type
        """
        if not force_new and protocol_type in cls._instances:
            return cls._instances[protocol_type]

        if protocol_type not in cls._client_factories:
            raise ValueError(
                f"No client factory registered for protocol: {protocol_type.value}. "
                f"Available protocols: {[p.value for p in cls._client_factories.keys()]}"
            )

        settings = settings or get_settings()
        client = cls._client_factories[protocol_type](settings)
        cls._instances[protocol_type] = client
        logger.info(f"Created new client for {protocol_type.value}")
        return client

    @classmethod
    def get_all_clients(
        cls,
        settings: Optional[Settings] = None,
    ) -> Dict[ProtocolType, ProtocolClient]:
        """Get clients for all registered protocols.

        Args:
            settings: Optional settings to pass to client factories

        Returns:
            Dict mapping ProtocolType to ProtocolClient instances
        """
        clients = {}
        for protocol_type in cls._client_factories:
            clients[protocol_type] = cls.get_client(protocol_type, settings)
        return clients

    @classmethod
    def get_available_protocols(cls) -> list[ProtocolType]:
        """Get list of protocols with registered factories.

        Returns:
            List of ProtocolType values that have registered factories
        """
        return list(cls._client_factories.keys())

    @classmethod
    async def close_all(cls) -> None:
        """Close all active client instances."""
        for protocol_type, client in cls._instances.items():
            try:
                await client.close()
                logger.debug(f"Closed client for {protocol_type.value}")
            except Exception as e:
                logger.error(f"Error closing client for {protocol_type.value}: {e}")
        cls._instances.clear()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered factories and instances.

        Primarily useful for testing.
        """
        cls._client_factories.clear()
        cls._instances.clear()


def register_default_clients() -> None:
    """Register the default protocol clients.

    This function should be called during application initialization
    to register all available protocol clients.
    """
    # Import here to avoid circular imports
    from src.data.clients.morpho.client import MorphoClient
    from src.data.clients.aave.client import AaveClient

    ProtocolClientRegistry.register(
        ProtocolType.MORPHO,
        lambda settings: MorphoClient(settings),
    )

    ProtocolClientRegistry.register(
        ProtocolType.AAVE,
        lambda settings: AaveClient(settings),
    )

    logger.info("Registered default protocol clients")
