"""Aave v3 protocol-specific configuration and constants."""

# GraphQL API rate limits (official Aave API)
AAVE_API_RATE_LIMIT = 1000  # requests per minute
AAVE_API_RATE_WINDOW = 60  # seconds

# Official Aave v3 GraphQL API (FREE, no API key required)
# Documentation: https://aave.com/docs/aave-v3/getting-started/graphql
AAVE_V3_API_URL = "https://api.v3.aave.com/graphql"

# Aave v3 contract addresses (Ethereum Mainnet)
AAVE_V3_POOL_ADDRESS = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
AAVE_V3_POOL_DATA_PROVIDER = "0x7B4EB56E7CD4b454BA8ff71E4518426369a138a3"

# Supported chain IDs
ETHEREUM_MAINNET = 1
POLYGON = 137
ARBITRUM = 42161
OPTIMISM = 10
AVALANCHE = 43114
BASE = 8453

# Reserve status flags
RESERVE_ACTIVE = "active"
RESERVE_FROZEN = "frozen"
RESERVE_PAUSED = "paused"
