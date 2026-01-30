"""Pydantic settings for Morpho Tracker configuration."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Ethereum RPC
    eth_alchemy_api_key: Optional[str] = Field(default=None, description="Alchemy API key for Ethereum RPC")

    # Wallet addresses to track
    wallet_addresses: List[str] = Field(default_factory=list, description="Wallet addresses to monitor")

    # UI Configuration
    ui_refresh_interval: int = Field(default=60, ge=10, le=3600, description="UI refresh interval in seconds")

    # Cache Configuration
    cache_dir: Path = Field(default=Path(".cache/morpho"), description="Cache directory path")
    cache_ttl_seconds: int = Field(default=300, ge=60, le=3600, description="Cache TTL in seconds")

    # Morpho API
    morpho_api_url: str = Field(
        default="https://blue-api.morpho.org/graphql",
        description="Morpho GraphQL API URL",
    )

    # Analytics
    risk_free_rate: float = Field(default=0.00, ge=0.0, le=0.00, description="Risk-free rate for Sharpe/Sortino")

    @field_validator("wallet_addresses", mode="before")
    @classmethod
    def parse_wallet_addresses(cls, v):
        """Parse comma-separated wallet addresses."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [addr.strip() for addr in v.split(",") if addr.strip()]
        return v or []

    @field_validator("cache_dir", mode="before")
    @classmethod
    def parse_cache_dir(cls, v):
        """Convert string to Path."""
        if isinstance(v, str):
            return Path(v)
        return v

    @property
    def eth_rpc_url(self) -> Optional[str]:
        """Get Ethereum RPC URL from Alchemy API key."""
        if self.eth_alchemy_api_key:
            return f"https://eth-mainnet.g.alchemy.com/v2/{self.eth_alchemy_api_key}"
        return None

    @property
    def alchemy_rpc_url(self) -> Optional[str]:
        """Alias for eth_rpc_url for Alchemy provider."""
        return self.eth_rpc_url

    def ensure_cache_dir(self) -> Path:
        """Ensure cache directory exists and return it."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
