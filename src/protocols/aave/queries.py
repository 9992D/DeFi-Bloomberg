"""GraphQL queries for Aave v3 official API.

API Documentation: https://aave.com/docs/aave-v3/getting-started/graphql
Endpoint: https://api.v3.aave.com/graphql
"""


class AaveQueries:
    """GraphQL query definitions for Aave v3 official API."""

    # Fetch all reserves (markets) for specified chains
    MARKETS_QUERY = """
    query GetMarkets($chainIds: [ChainId!]!) {
        markets(request: { chainIds: $chainIds }) {
            name
            chain {
                chainId
                name
            }
            reserves {
                underlyingToken {
                    address
                    symbol
                    name
                    decimals
                }
                usdExchangeRate
                supplyInfo {
                    apy { value }
                    maxLTV { value }
                    liquidationThreshold { value }
                    total { value }
                    canBeCollateral
                }
                borrowInfo {
                    apy { value }
                    total {
                        amount { value }
                        usd
                    }
                    utilizationRate { value }
                    availableLiquidity {
                        amount { value }
                        usd
                    }
                }
                isFrozen
                isPaused
            }
        }
    }
    """

    # Fetch user positions across reserves
    USER_POSITIONS_QUERY = """
    query GetUserPositions($chainIds: [ChainId!]!, $user: EvmAddress!) {
        markets(request: { chainIds: $chainIds }) {
            name
            chain { chainId }
            reserves {
                underlyingToken {
                    address
                    symbol
                    decimals
                }
                userState(user: $user) {
                    suppliedAmount {
                        amount { value }
                        usd
                    }
                    borrowedAmount {
                        amount { value }
                        usd
                    }
                    collateralEnabled
                }
            }
        }
    }
    """

    # Lightweight query for rates only
    RATES_QUERY = """
    query GetRates($chainIds: [ChainId!]!) {
        markets(request: { chainIds: $chainIds }) {
            reserves {
                underlyingToken {
                    address
                    symbol
                }
                supplyInfo {
                    apy { value }
                }
                borrowInfo {
                    apy { value }
                    utilizationRate { value }
                }
            }
        }
    }
    """

    # Get supported chains
    CHAINS_QUERY = """
    query GetChains {
        chains {
            name
            chainId
        }
    }
    """

    # Historical supply APY for a reserve
    SUPPLY_APY_HISTORY_QUERY = """
    query GetSupplyAPYHistory(
        $chainId: ChainId!,
        $market: EvmAddress!,
        $underlyingToken: EvmAddress!,
        $window: TimeWindow!
    ) {
        supplyAPYHistory(request: {
            chainId: $chainId
            market: $market
            underlyingToken: $underlyingToken
            window: $window
        }) {
            date
            avgRate { value }
        }
    }
    """

    # Historical borrow APY for a reserve
    BORROW_APY_HISTORY_QUERY = """
    query GetBorrowAPYHistory(
        $chainId: ChainId!,
        $market: EvmAddress!,
        $underlyingToken: EvmAddress!,
        $window: TimeWindow!
    ) {
        borrowAPYHistory(request: {
            chainId: $chainId
            market: $market
            underlyingToken: $underlyingToken
            window: $window
        }) {
            date
            avgRate { value }
        }
    }
    """

    # Combined historical APY query (supply + borrow in one request)
    APY_HISTORY_QUERY = """
    query GetAPYHistory(
        $chainId: ChainId!,
        $market: EvmAddress!,
        $underlyingToken: EvmAddress!,
        $window: TimeWindow!
    ) {
        supplyAPYHistory(request: {
            chainId: $chainId
            market: $market
            underlyingToken: $underlyingToken
            window: $window
        }) {
            date
            avgRate { value }
        }
        borrowAPYHistory(request: {
            chainId: $chainId
            market: $market
            underlyingToken: $underlyingToken
            window: $window
        }) {
            date
            avgRate { value }
        }
    }
    """
