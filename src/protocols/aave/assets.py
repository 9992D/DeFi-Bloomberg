"""Aave v3 protocol asset addresses (Ethereum mainnet)."""

# Common collateral assets for Aave v3
# Format: (display_name, address)
COLLATERAL_ASSETS = [
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("wstETH", "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"),
    ("WBTC", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),
    ("cbETH", "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704"),
    ("rETH", "0xae78736Cd615f374D3085123A210448E74Fc6393"),
    ("LINK", "0x514910771AF9Ca656af840dff83E8264EcF986CA"),
    ("AAVE", "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"),
    ("Custom address...", "custom"),
]

# Common borrow assets for Aave v3
BORROW_ASSETS = [
    ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
    ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
    ("DAI", "0x6B175474E89094C44Da98b954EesdeaFE3C4d256"),
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("GHO", "0x40D16FC0246aD3160Ccc09B8D0D3A2cD28aE6C2f"),
    ("LUSD", "0x5f98805A4E8be255a32880FDeC7F6728C6568bA0"),
    ("Custom address...", "custom"),
]

# Default collateral address (WETH)
DEFAULT_COLLATERAL_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

# Default borrow address (USDC)
DEFAULT_BORROW_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def get_asset_name(address: str, asset_list: list) -> str:
    """Get display name for an asset address.

    Args:
        address: Token address
        asset_list: List of (name, address) tuples

    Returns:
        Display name or shortened address if not found
    """
    for name, addr in asset_list:
        if addr.lower() == address.lower():
            return name
    # Return shortened address if not found
    return f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
