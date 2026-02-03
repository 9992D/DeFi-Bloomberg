"""Morpho protocol asset addresses (Ethereum mainnet)."""

# Common collateral assets
# Format: (display_name, address)
COLLATERAL_ASSETS = [
    ("wstETH", "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"),
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("cbETH", "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704"),
    ("rETH", "0xae78736Cd615f374D3085123A210448E74Fc6393"),
    ("weETH", "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee"),
    ("sDAI", "0x83F20F44975D03b1b09e64809B757c47f942BEeA"),
    ("WBTC", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"),
    ("Custom address...", "custom"),
]

# Common borrow assets
BORROW_ASSETS = [
    ("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
    ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
    ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
    ("DAI", "0x6B175474E89094C44Da98b954EesdeaFE3C4d256"),
    ("USDA", "0x0000206329b97DB379d5E1Bf586BbDB969C63274"),
    ("pyUSD", "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"),
    ("Custom address...", "custom"),
]

# Default collateral address (wstETH)
DEFAULT_COLLATERAL_ADDRESS = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"

# Default borrow address (WETH)
DEFAULT_BORROW_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


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
