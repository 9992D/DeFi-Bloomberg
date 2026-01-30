"""GraphQL queries for Morpho Blue API."""


class MorphoQueries:
    """GraphQL query definitions for Morpho Blue API."""

    # Fetch all markets with current state
    MARKETS_QUERY = """
    query GetMarkets($first: Int!, $skip: Int, $chainId: Int!) {
        markets(
            first: $first
            skip: $skip
            where: { chainId_in: [$chainId] }
            orderBy: SupplyAssetsUsd
            orderDirection: Desc
        ) {
            items {
                id
                uniqueKey
                lltv
                oracleAddress
                irmAddress
                creationTimestamp
                loanAsset {
                    address
                    symbol
                    decimals
                    priceUsd
                }
                collateralAsset {
                    address
                    symbol
                    decimals
                    priceUsd
                }
                state {
                    borrowApy
                    supplyApy
                    fee
                    utilization
                    borrowAssets
                    supplyAssets
                    borrowShares
                    supplyShares
                    rateAtTarget
                    timestamp
                }
            }
        }
    }
    """

    # Fetch single market details with historical data
    MARKET_DETAIL_QUERY = """
    query GetMarket($uniqueKey: String!, $chainId: Int!) {
        marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
            id
            uniqueKey
            lltv
            oracleAddress
            irmAddress
            loanAsset {
                address
                symbol
                decimals
                priceUsd
            }
            collateralAsset {
                address
                symbol
                decimals
                priceUsd
            }
            state {
                borrowApy
                supplyApy
                fee
                utilization
                borrowAssets
                supplyAssets
                borrowShares
                supplyShares
                rateAtTarget
                timestamp
            }
            historicalState {
                borrowApy { x y }
                supplyApy { x y }
                utilization { x y }
                rateAtTarget { x y }
            }
        }
    }
    """

    # Fetch market timeseries (historical data points) with time options
    MARKET_TIMESERIES_QUERY = """
    query GetMarketTimeseries($uniqueKey: String!, $chainId: Int!, $options: TimeseriesOptions) {
        marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
            id
            uniqueKey
            historicalState {
                borrowApy(options: $options) { x y }
                supplyApy(options: $options) { x y }
                utilization(options: $options) { x y }
                rateAtTarget(options: $options) { x y }
            }
        }
    }
    """

    # Fetch positions for a user
    POSITIONS_QUERY = """
    query GetPositions($userAddress: String!, $chainId: Int!, $first: Int!) {
        positions(
            first: $first
            where: {
                chainId_in: [$chainId]
                userAddress_in: [$userAddress]
            }
        ) {
            items {
                id
                market {
                    uniqueKey
                    loanAsset {
                        symbol
                        decimals
                    }
                    collateralAsset {
                        symbol
                        decimals
                    }
                }
                user {
                    address
                }
                state {
                    supplyShares
                    supplyAssets
                    borrowShares
                    borrowAssets
                    collateral
                    timestamp
                }
            }
        }
    }
    """

    # Fetch multiple positions across wallets
    MULTI_WALLET_POSITIONS_QUERY = """
    query GetMultiWalletPositions($userAddresses: [String!]!, $chainId: Int!, $first: Int!) {
        positions(
            first: $first
            where: {
                chainId_in: [$chainId]
                userAddress_in: $userAddresses
            }
        ) {
            items {
                id
                market {
                    uniqueKey
                    loanAsset {
                        symbol
                        decimals
                    }
                    collateralAsset {
                        symbol
                        decimals
                    }
                }
                user {
                    address
                }
                state {
                    supplyShares
                    supplyAssets
                    borrowShares
                    borrowAssets
                    collateral
                    timestamp
                }
            }
        }
    }
    """

    # Lightweight query for rate data only
    RATES_QUERY = """
    query GetRates($chainId: Int!, $first: Int!) {
        markets(
            first: $first
            where: { chainId_in: [$chainId] }
            orderBy: SupplyAssetsUsd
            orderDirection: Desc
        ) {
            items {
                uniqueKey
                state {
                    borrowApy
                    supplyApy
                    utilization
                    rateAtTarget
                    timestamp
                }
            }
        }
    }
    """

    # ========== VAULT QUERIES ==========

    # Fetch all vaults with current state
    VAULTS_QUERY = """
    query GetVaults($first: Int!, $skip: Int, $chainId: Int!) {
        vaults(
            first: $first
            skip: $skip
            where: { chainId_in: [$chainId] }
            orderBy: TotalAssetsUsd
            orderDirection: Desc
        ) {
            items {
                address
                name
                symbol
                creationTimestamp
                asset {
                    address
                    symbol
                    decimals
                    priceUsd
                }
                state {
                    totalAssets
                    totalAssetsUsd
                    totalSupply
                    apy
                    netApy
                    fee
                    sharePriceNumber
                    sharePriceUsd
                    timestamp
                    allocation {
                        market {
                            uniqueKey
                            loanAsset { symbol }
                            collateralAsset { symbol }
                            lltv
                        }
                        supplyAssets
                        supplyAssetsUsd
                        supplyShares
                    }
                }
            }
            pageInfo {
                count
                countTotal
            }
        }
    }
    """

    # Fetch single vault with historical data
    VAULT_DETAIL_QUERY = """
    query GetVault($address: String!, $chainId: Int!) {
        vaults(first: 1, where: { chainId_in: [$chainId], address_in: [$address] }) {
            items {
                address
                name
                symbol
                asset {
                    address
                    symbol
                    decimals
                    priceUsd
                }
                state {
                    totalAssets
                    totalAssetsUsd
                    totalSupply
                    apy
                    netApy
                    fee
                    sharePriceNumber
                    sharePriceUsd
                    timestamp
                    allocation {
                        market {
                            uniqueKey
                            loanAsset { symbol }
                            collateralAsset { symbol }
                            lltv
                        }
                        supplyAssets
                        supplyAssetsUsd
                        supplyShares
                    }
                }
                historicalState {
                    apy { x y }
                    netApy { x y }
                    totalAssets { x y }
                    sharePriceNumber { x y }
                }
            }
        }
    }
    """

    # Fetch vault timeseries (historical data) with time options
    VAULT_TIMESERIES_QUERY = """
    query GetVaultTimeseries($address: String!, $chainId: Int!, $options: TimeseriesOptions) {
        vaults(first: 1, where: { chainId_in: [$chainId], address_in: [$address] }) {
            items {
                address
                historicalState {
                    apy(options: $options) { x y }
                    netApy(options: $options) { x y }
                    totalAssets(options: $options) { x y }
                    sharePriceNumber(options: $options) { x y }
                }
            }
        }
    }
    """
