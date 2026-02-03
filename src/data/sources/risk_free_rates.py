"""Risk-free rate providers for different asset types.

Provides dynamic risk-free rates:
- Stablecoins (USDC, USDT, DAI, etc.): US T-bills rate from FRED API
- WETH/ETH: Lido staking APR
- wstETH: 0% (inherent staking yield)
- Other tokens: 0%
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Tuple
from collections import OrderedDict

import aiohttp

logger = logging.getLogger(__name__)


# Asset classifications
STABLECOINS = {
    # Addresses (lowercase for comparison)
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0x6b175474e89094c44da98b954eesdeafe3c4d256",  # DAI
    "0x83f20f44975d03b1b09e64809b757c47f942beea",  # sDAI
    "0x0000206329b97db379d5e1bf586bbdb969c63274",  # USDA
    "0x6c3ea9036406852006290770bedfcaba0e23a0e8",  # pyUSD
    "0x1abaea1f7c830bd89acc67ec4af516284b1bc33c",  # EURC
    "0x9c9e5fd8bbc25984b178fdce6117defa39d2db39",  # BUSD
    "0x853d955acef822db058eb8505911ed77f175b99e",  # FRAX
    "0x5f98805a4e8be255a32880fdec7f6728c6568ba0",  # LUSD
    # Symbols (for fallback matching)
    "usdc", "usdt", "dai", "sdai", "usda", "pyusd", "eurc", "busd", "frax", "lusd",
    "tusd", "gusd", "usdp", "fei", "rai", "mim", "dola", "crvusd",
}

ETH_TOKENS = {
    # Addresses
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0x0000000000000000000000000000000000000000",  # ETH
    # Symbols
    "weth", "eth",
}

WSTETH_TOKENS = {
    # wstETH has inherent staking yield - risk-free rate should be 0
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",  # wstETH
    "wsteth",
}

# Other staked ETH derivatives that should use Lido rate
STAKED_ETH_TOKENS = {
    "0xae78736cd615f374d3085123a210448e74fc6393",  # rETH
    "0xbe9895146f7af43049ca1c1ae358b0541ea49704",  # cbETH
    "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee",  # weETH
    "reth", "cbeth", "weeth", "steth",
}


class RiskFreeRateProvider:
    """
    Provides risk-free rates based on asset type.

    Caches rates with TTL to avoid excessive API calls.
    """

    # Cache configuration
    CACHE_TTL_SECONDS = 3600  # 1 hour

    # API endpoints
    FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
    LIDO_APR_URL = "https://eth-api.lido.fi/v1/protocol/steth/apr/sma"

    # Fallback rates (annualized, as decimals)
    FALLBACK_TBILL_RATE = 0.05  # 5% fallback
    FALLBACK_LIDO_RATE = 0.035  # 3.5% fallback

    def __init__(self, fred_api_key: Optional[str] = None):
        """
        Initialize provider.

        Args:
            fred_api_key: Optional FRED API key for T-bills data.
                         If not provided, uses fallback rate.
        """
        self.fred_api_key = fred_api_key
        self._cache: Dict[str, Tuple[float, datetime]] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_cached(self, key: str) -> Optional[float]:
        """Get cached value if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if (datetime.now(timezone.utc) - timestamp).total_seconds() < self.CACHE_TTL_SECONDS:
                return value
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value: float) -> None:
        """Cache a value with current timestamp."""
        self._cache[key] = (value, datetime.now(timezone.utc))

    async def get_tbill_rate(self) -> float:
        """
        Fetch current US T-bills rate (3-month).

        Returns annualized rate as decimal (e.g., 0.05 for 5%).
        """
        # Check cache
        cached = self._get_cached("tbill")
        if cached is not None:
            return cached

        # Try FRED API if we have a key
        if self.fred_api_key:
            try:
                rate = await self._fetch_fred_tbill()
                if rate is not None:
                    self._set_cached("tbill", rate)
                    logger.info(f"Fetched T-bill rate from FRED: {rate*100:.2f}%")
                    return rate
            except Exception as e:
                logger.warning(f"Failed to fetch T-bill rate from FRED: {e}")

        # Try alternative free API (Treasury.gov)
        try:
            rate = await self._fetch_treasury_rate()
            if rate is not None:
                self._set_cached("tbill", rate)
                logger.info(f"Fetched T-bill rate from Treasury: {rate*100:.2f}%")
                return rate
        except Exception as e:
            logger.warning(f"Failed to fetch T-bill rate from Treasury: {e}")

        # Use fallback
        logger.info(f"Using fallback T-bill rate: {self.FALLBACK_TBILL_RATE*100:.2f}%")
        return self.FALLBACK_TBILL_RATE

    async def _fetch_fred_tbill(self) -> Optional[float]:
        """Fetch T-bill rate from FRED API."""
        session = await self._get_session()

        # DGS3MO = 3-Month Treasury Constant Maturity Rate
        params = {
            "series_id": "DGS3MO",
            "api_key": self.fred_api_key,
            "file_type": "json",
            "limit": 1,
            "sort_order": "desc",
        }

        async with session.get(self.FRED_API_URL, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                observations = data.get("observations", [])
                if observations:
                    # Rate is in percentage, convert to decimal
                    value = observations[0].get("value")
                    if value and value != ".":
                        return float(value) / 100
        return None

    async def _fetch_treasury_rate(self) -> Optional[float]:
        """Fetch T-bill rate from Treasury.gov XML feed."""
        session = await self._get_session()

        # Treasury Daily Yield Curve Rates
        url = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/all?type=daily_treasury_bill_rates&field_tdr_date_value=2024&page&_format=csv"

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    lines = text.strip().split('\n')
                    if len(lines) > 1:
                        # Get most recent line, parse 4-week rate (column index may vary)
                        # This is a simplified parser
                        header = lines[0].split(',')
                        last_line = lines[-1].split(',')

                        # Look for "4 WEEKS" column
                        for i, col in enumerate(header):
                            if "4 WEEKS" in col.upper() or "4WEEK" in col.upper():
                                if i < len(last_line) and last_line[i]:
                                    try:
                                        return float(last_line[i]) / 100
                                    except ValueError:
                                        pass
        except Exception as e:
            logger.debug(f"Treasury.gov fetch failed: {e}")

        return None

    async def get_lido_staking_rate(self) -> float:
        """
        Fetch current Lido staking APR.

        Returns annualized rate as decimal (e.g., 0.035 for 3.5%).
        """
        # Check cache
        cached = self._get_cached("lido")
        if cached is not None:
            return cached

        try:
            session = await self._get_session()

            async with session.get(self.LIDO_APR_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Lido API returns APR as percentage in 'data.smaApr'
                    sma_apr = data.get("data", {}).get("smaApr")
                    if sma_apr is not None:
                        rate = float(sma_apr) / 100  # Convert percentage to decimal
                        self._set_cached("lido", rate)
                        logger.info(f"Fetched Lido staking rate: {rate*100:.2f}%")
                        return rate
        except Exception as e:
            logger.warning(f"Failed to fetch Lido staking rate: {e}")

        # Use fallback
        logger.info(f"Using fallback Lido rate: {self.FALLBACK_LIDO_RATE*100:.2f}%")
        return self.FALLBACK_LIDO_RATE

    def classify_asset(self, asset_address: str, asset_symbol: str) -> str:
        """
        Classify an asset to determine which risk-free rate to use.

        Args:
            asset_address: Token contract address
            asset_symbol: Token symbol

        Returns:
            One of: "stablecoin", "eth", "wsteth", "staked_eth", "other"
        """
        addr_lower = asset_address.lower() if asset_address else ""
        symbol_lower = asset_symbol.lower() if asset_symbol else ""

        # Check wstETH first (inherent yield)
        if addr_lower in WSTETH_TOKENS or symbol_lower in WSTETH_TOKENS:
            return "wsteth"

        # Check stablecoins
        if addr_lower in STABLECOINS or symbol_lower in STABLECOINS:
            return "stablecoin"

        # Check ETH tokens
        if addr_lower in ETH_TOKENS or symbol_lower in ETH_TOKENS:
            return "eth"

        # Check other staked ETH derivatives
        if addr_lower in STAKED_ETH_TOKENS or symbol_lower in STAKED_ETH_TOKENS:
            return "staked_eth"

        return "other"

    async def get_risk_free_rate(
        self,
        asset_address: str,
        asset_symbol: str,
    ) -> Tuple[float, str]:
        """
        Get the appropriate risk-free rate for an asset.

        Args:
            asset_address: Token contract address
            asset_symbol: Token symbol

        Returns:
            Tuple of (rate as decimal, rate_type description)
        """
        asset_type = self.classify_asset(asset_address, asset_symbol)

        if asset_type == "stablecoin":
            rate = await self.get_tbill_rate()
            return rate, "T-bill rate"

        elif asset_type == "eth":
            rate = await self.get_lido_staking_rate()
            return rate, "Lido staking rate"

        elif asset_type == "wsteth":
            # wstETH already has inherent staking yield
            return 0.0, "wstETH (inherent yield)"

        elif asset_type == "staked_eth":
            # Other staked ETH derivatives - use 0 as they have inherent yield
            return 0.0, f"{asset_symbol} (inherent yield)"

        else:
            # Other tokens - no meaningful risk-free rate
            return 0.0, "other (no risk-free rate)"


# Global instance with lazy initialization
_provider: Optional[RiskFreeRateProvider] = None


def get_risk_free_rate_provider(fred_api_key: Optional[str] = None) -> RiskFreeRateProvider:
    """Get or create the global risk-free rate provider.

    If fred_api_key is not provided, attempts to load from settings.
    """
    global _provider
    if _provider is None:
        # Try to get API key from settings if not provided
        if fred_api_key is None:
            try:
                from config.settings import get_settings
                settings = get_settings()
                fred_api_key = settings.fred_api_key
            except Exception:
                pass  # Settings not available, proceed without API key

        _provider = RiskFreeRateProvider(fred_api_key=fred_api_key)
    return _provider


async def get_risk_free_rate_for_market(
    loan_asset_address: str,
    loan_asset_symbol: str,
    fred_api_key: Optional[str] = None,
) -> Tuple[float, str]:
    """
    Convenience function to get risk-free rate for a market's loan asset.

    Args:
        loan_asset_address: Loan token contract address
        loan_asset_symbol: Loan token symbol
        fred_api_key: Optional FRED API key

    Returns:
        Tuple of (rate as decimal, rate_type description)
    """
    provider = get_risk_free_rate_provider(fred_api_key)
    return await provider.get_risk_free_rate(loan_asset_address, loan_asset_symbol)


def get_risk_free_rate_sync(
    loan_asset_address: str,
    loan_asset_symbol: str,
) -> Tuple[float, str]:
    """
    Synchronous version - uses cached values or fallbacks.

    This is useful when called from synchronous code that can't await.
    For fresh data, use the async version or pre-fetch rates.

    Args:
        loan_asset_address: Loan token contract address
        loan_asset_symbol: Loan token symbol

    Returns:
        Tuple of (rate as decimal, rate_type description)
    """
    provider = get_risk_free_rate_provider()
    asset_type = provider.classify_asset(loan_asset_address, loan_asset_symbol)

    if asset_type == "stablecoin":
        # Try cache first
        cached = provider._get_cached("tbill")
        if cached is not None:
            return cached, "T-bill rate (cached)"
        return provider.FALLBACK_TBILL_RATE, "T-bill rate (fallback)"

    elif asset_type == "eth":
        # Try cache first
        cached = provider._get_cached("lido")
        if cached is not None:
            return cached, "Lido staking rate (cached)"
        return provider.FALLBACK_LIDO_RATE, "Lido staking rate (fallback)"

    elif asset_type == "wsteth":
        return 0.0, "wstETH (inherent yield)"

    elif asset_type == "staked_eth":
        return 0.0, f"{loan_asset_symbol} (inherent yield)"

    else:
        return 0.0, "other (no risk-free rate)"


async def prefetch_risk_free_rates() -> Dict[str, float]:
    """
    Pre-fetch and cache all risk-free rates.

    Call this at startup or periodically to ensure fresh cached values.

    Returns:
        Dict with rate names and values
    """
    provider = get_risk_free_rate_provider()

    results = {}

    # Fetch T-bill rate
    try:
        tbill = await provider.get_tbill_rate()
        results["tbill"] = tbill
    except Exception as e:
        logger.warning(f"Failed to prefetch T-bill rate: {e}")
        results["tbill"] = provider.FALLBACK_TBILL_RATE

    # Fetch Lido rate
    try:
        lido = await provider.get_lido_staking_rate()
        results["lido"] = lido
    except Exception as e:
        logger.warning(f"Failed to prefetch Lido rate: {e}")
        results["lido"] = provider.FALLBACK_LIDO_RATE

    logger.info(f"Prefetched risk-free rates: T-bill={results['tbill']*100:.2f}%, Lido={results['lido']*100:.2f}%")
    return results
