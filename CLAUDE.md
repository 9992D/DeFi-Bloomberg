# CLAUDE.md - DeFi Bloomberg Terminal

## Project Overview

DeFi-Bloomberg is a Bloomberg-style Terminal UI for monitoring and simulating DeFi lending positions. Built with Python and Textual TUI framework, it provides real-time analytics for decentralized finance markets with support for **Morpho Blue** and **Aave v3** protocols.

**Key Features:**
- Real-time lending/borrowing market monitoring
- Vault allocation simulation with multiple strategies
- Debt rebalancing optimization across markets
- Advanced financial KPIs (Sharpe, Sortino, volatility, mean reversion)
- Extensible architecture for multiple DeFi protocols

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure (optional)
cp .env.example .env

# Run application
python -m src.ui.app

# Run tests
pytest
```

**Keyboard Shortcuts:** `1`/`2` tabs, `M` markets, `V` vaults, `R` refresh, `Q` quit

## Architecture

```
┌─────────────────────────────────────────────────┐
│           UI Layer (Textual TUI)                │
│  Lending Tab │ Sandbox Allocator │ Debt Optimizer│
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              Data Layer                          │
│  DataPipeline ──► DataAggregator                │
│       │                                         │
│  ProtocolClients (MorphoClient, AaveClient GQL) │
│       │                                         │
│  Caching (Memory + SQLite DiskCache)            │
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│           Analytics & Sandbox                    │
│  AnalyticsEngine │ AllocationSimulator │         │
│  KPI Calculators │ DebtRebalancingOptimizer     │
└─────────────────────────────────────────────────┘
```

## Directory Structure

```
DeFi-Bloomberg/
├── config/
│   └── settings.py          # Pydantic settings (API keys, cache TTL)
│
├── src/
│   ├── core/                # Domain models
│   │   ├── constants/       # Chain IDs, generics
│   │   └── models/
│   │       ├── market.py    # Market, MarketState
│   │       ├── position.py  # Position (user positions)
│   │       ├── vault.py     # Vault data models
│   │       ├── timeseries.py# TimeseriesPoint
│   │       └── kpi.py       # KPI result types
│   │
│   ├── data/                # Data fetching & caching
│   │   ├── pipeline.py      # DataPipeline orchestrator
│   │   ├── cache/
│   │   │   └── disk_cache.py# SQLite cache with TTL
│   │   ├── clients/
│   │   │   ├── base.py      # ProtocolClient ABC
│   │   │   ├── morpho/
│   │   │   │   ├── client.py# MorphoClient (GraphQL)
│   │   │   │   └── parser.py
│   │   │   ├── aave/
│   │   │   │   ├── client.py# AaveClient (GraphQL subgraph)
│   │   │   │   └── parser.py# RAY/WAD conversions
│   │   │   └── registry.py  # Client registration
│   │   └── sources/
│   │       ├── morpho_api.py# Low-level GraphQL
│   │       └── risk_free_rates.py  # T-bills & Lido rates
│   │
│   ├── protocols/
│   │   ├── morpho/
│   │   │   ├── config.py    # IRM params, addresses
│   │   │   ├── assets.py    # Token addresses (collateral/borrow)
│   │   │   ├── irm.py       # Interest Rate Model
│   │   │   └── queries.py   # GraphQL queries
│   │   └── aave/
│   │       ├── config.py    # Rate limits, subgraph URL
│   │       └── queries.py   # GraphQL queries
│   │
│   ├── analytics/
│   │   ├── engine.py        # AnalyticsEngine
│   │   └── kpis/            # KPI calculators
│   │       ├── volatility.py
│   │       ├── risk_adjusted.py  # Sharpe, Sortino
│   │       ├── mean_reversion.py
│   │       ├── utilization.py
│   │       └── elasticity.py
│   │
│   ├── sandbox/             # Simulation & optimization
│   │   ├── models/
│   │   │   ├── allocation.py    # AllocationConfig, AllocationResult
│   │   │   ├── rebalancing.py   # RebalancingConfig, DebtPosition
│   │   │   ├── strategy.py      # StrategyConfig
│   │   │   └── simulation.py    # SimulationResult
│   │   ├── engine/
│   │   │   ├── allocator.py     # AllocationSimulator
│   │   │   ├── debt_optimizer.py# DebtRebalancingOptimizer
│   │   │   ├── risk.py          # RiskCalculator
│   │   │   └── simulator.py     # StrategySimulator
│   │   ├── data/
│   │   │   └── aggregator.py    # DataAggregator
│   │   └── persistence/
│   │       └── storage.py       # JSON/SQLite persistence
│   │
│   └── ui/
│       ├── app.py               # Main Textual app
│       ├── screens/
│       │   ├── lending/         # Lending tab screens
│       │   ├── sandbox.py       # Sandbox tabbed interface
│       │   ├── debt_optimizer.py# Debt optimizer UI
│       │   ├── markets.py       # Markets table
│       │   └── vaults.py        # Vaults table
│       └── widgets/             # Reusable UI components
│
├── tests/
│   ├── unit/
│   │   ├── test_kpis.py
│   │   ├── test_morpho_api.py
│   │   └── test_aave_api.py
│   └── integration/
│       └── test_pipeline.py
│
├── .env.example             # Environment template
├── pyproject.toml           # Project metadata
├── requirements.txt         # Dependencies
└── README.md
```

## Key Files to Know

### Core Models
- **`src/core/models/market.py`**: `Market`, `MarketState` dataclasses - lending market data
- **`src/core/models/vault.py`**: `Vault` dataclass - MetaMorpho vault representation
- **`src/core/models/timeseries.py`**: `TimeseriesPoint` - historical rate/utilization data

### Data Layer
- **`src/data/pipeline.py`**: `DataPipeline` - main data orchestrator, manages caching
- **`src/data/clients/morpho/client.py`**: `MorphoClient` - Morpho GraphQL API client
- **`src/data/clients/aave/client.py`**: `AaveClient` - Aave v3 subgraph client
- **`src/data/cache/disk_cache.py`**: `DiskCache` - SQLite-based persistent cache
- **`src/data/sources/risk_free_rates.py`**: `RiskFreeRateProvider` - T-bills and Lido rates

### Sandbox Engine
- **`src/sandbox/engine/allocator.py`**: `AllocationSimulator` - vault allocation strategies
- **`src/sandbox/engine/debt_optimizer.py`**: `DebtRebalancingOptimizer` - debt optimization
- **`src/sandbox/models/rebalancing.py`**: All debt rebalancing models

### UI
- **`src/ui/app.py`**: `DeFiTrackerApp` - main Textual application
- **`src/ui/screens/debt_optimizer.py`**: Debt optimizer screen

## Important Patterns

### 1. Decimal for Financial Calculations
Always use `Decimal` for prices, rates, amounts:
```python
from decimal import Decimal
price = Decimal("80000.50")  # Never use float for money
```

### 2. Async Data Fetching
All data fetching is async:
```python
async def get_data():
    markets = await pipeline.get_markets("morpho")
    timeseries = await pipeline.get_market_timeseries("morpho", market_id, days=30)
```

### 3. Protocol Client Interface
New protocols implement `ProtocolClient` ABC:
```python
class ProtocolClient(ABC):
    @abstractmethod
    async def get_markets(self, first: int = 100) -> List[Market]: ...
    @abstractmethod
    async def get_market_timeseries(self, market_id: str, ...) -> List[TimeseriesPoint]: ...
```

### 4. Caching Strategy
- Memory cache in `DataPipeline` for hot data
- SQLite `DiskCache` for persistence with TTL (default 300s)
- Cache keys use namespace pattern: `{protocol}:{entity}:{id}`

### 5. Dataclasses with to_dict()
All models have `to_dict()` for serialization:
```python
@dataclass
class Market:
    id: str
    name: str
    # ...
    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, ...}
```

## Configuration

### Environment Variables (.env)
```bash
ETH_ALCHEMY_API_KEY=your_key      # Optional Alchemy RPC
WALLET_ADDRESSES=0x...            # Addresses to track
UI_REFRESH_INTERVAL=60            # UI refresh (seconds)
CACHE_DIR=.cache/morpho           # Cache directory
CACHE_TTL_SECONDS=300             # Cache TTL
MORPHO_API_URL=https://blue-api.morpho.org/graphql
# AAVE_API_URL=https://api.v3.aave.com/graphql  # Official free API
RISK_FREE_RATE=0                  # Fallback for Sharpe/Sortino
FRED_API_KEY=your_key             # Optional: FRED API for T-bills rate
```

### Dynamic Risk-Free Rates for Sharpe/Sortino
Risk-free rates are automatically determined based on the market's **loan asset**:

| Asset Type | Examples | Risk-Free Rate | Source |
|------------|----------|----------------|--------|
| Stablecoins | USDC, USDT, DAI, EURC | ~5% | FRED API (T-bills) |
| ETH | WETH, ETH | ~3.5% | Lido API |
| wstETH | wstETH | 0% | Inherent yield |
| Staked ETH | rETH, cbETH, weETH | 0% | Inherent yield |
| Other | WBTC, etc. | 0% | No benchmark |

**Key files:**
- `src/data/sources/risk_free_rates.py` - Rate provider with caching
- `src/analytics/kpis/risk_adjusted.py` - Sharpe/Sortino calculators

**Usage:**
```python
from src.data.sources.risk_free_rates import get_risk_free_rate_sync, prefetch_risk_free_rates

# Sync (uses cache or fallback)
rate, rate_type = get_risk_free_rate_sync("0xA0b86991...", "USDC")

# Async (fetches fresh data)
await prefetch_risk_free_rates()  # Pre-fetch all rates
```

**APIs:**
- FRED: `https://api.stlouisfed.org/fred/series/observations` (DGS3MO series)
- Lido: `https://eth-api.lido.fi/v1/protocol/steth/apr/sma`

### Settings Class
```python
from config.settings import Settings, get_settings
settings = get_settings()
print(settings.cache_ttl_seconds)
```

## Common Tasks

### Add New KPI Calculator
1. Create file in `src/analytics/kpis/`
2. Inherit from `BaseKPICalculator`
3. Implement `calculate()` method
4. Register in `AnalyticsEngine`

### Add New Protocol
1. Create client in `src/data/clients/{protocol}/`
2. Implement `ProtocolClient` interface
3. Register in `ProtocolClientRegistry`
4. Add protocol config in `src/protocols/{protocol}/`

### Modify Debt Optimizer
Key files:
- `src/sandbox/engine/debt_optimizer.py` - Core logic
- `src/sandbox/models/rebalancing.py` - Data models
- `src/ui/screens/debt_optimizer.py` - UI

Important methods in `DebtRebalancingOptimizer`:
- `_get_collateral_price()` - Get real prices from market cache
- `_calculate_optimal_allocation()` - Greedy allocation algorithm
- `_simulate_with_rebalancing()` - Historical simulation with dynamic prices
- `_generate_position_summary()` - Risk analysis with price scenarios

### Run Specific Tests
```bash
pytest tests/unit/test_kpis.py -v
pytest tests/integration/ -v
pytest -k "test_sharpe"  # Run tests matching pattern
```

## Technology Stack

- **UI**: Textual 0.47+, Rich 13.7+
- **Data**: GQL 3.5+ (GraphQL), aiohttp 3.9+, aiolimiter 1.1+
- **Computation**: NumPy 1.26+, SciPy 1.11+, Decimal
- **Validation**: Pydantic 2.5+
- **Caching**: diskcache 5.6+ (SQLite)
- **Testing**: pytest, pytest-asyncio

## Protocol Specifics

### Morpho Blue

**API Endpoint:** `https://blue-api.morpho.org/graphql`
**Rate limit:** 5000 requests / 5 minutes

**Key Concepts:**
- **Markets**: Explicit collateral/loan pairs (e.g., WETH/USDC @ 86% LLTV)
- **LLTV**: Liquidation Loan-to-Value (e.g., 0.86 = 86%)
- **Health Factor**: `(collateral * price * LLTV) / borrow`
- **IRM**: Interest Rate Model - Adaptive Curve IRM
- **Target Utilization**: 90% (where rates curve steepens)

**Price Calculations:**
```python
# Collateral price in loan terms (e.g., WBTC/USDC = 80000)
collateral_price = collateral_price_usd / loan_price_usd

# Borrow amount in loan tokens
borrow_amount = (collateral_amount * collateral_price * ltv)

# Health Factor
hf = (collateral_amount * collateral_price * lltv) / borrow_amount
```

### Aave v3

**API Endpoint:** Official Aave API (FREE, no API key required)
```
https://api.v3.aave.com/graphql
```
**Documentation:** https://aave.com/docs/aave-v3/getting-started/graphql
**Rate limit:** 1000 requests / minute

**Key Concepts:**
- **Reserves**: Individual assets that can be supplied OR borrowed
- **Collateral Model**: Global pool - any enabled asset can be collateral
- **collateral_asset_symbol = "MULTI"**: Indicates any enabled collateral works
- **Data Format**: API returns values already in decimal format (no RAY/WAD conversion needed)
- **Historical Data**: Available via `supplyAPYHistory` and `borrowAPYHistory` queries

**Mapping Aave to Market model:**
| Aave Reserve | Market Model |
|--------------|--------------|
| `underlyingToken.address` | `loan_asset` |
| `underlyingToken.symbol` | `loan_asset_symbol` |
| `""` | `collateral_asset` |
| `"MULTI"` | `collateral_asset_symbol` |
| `supplyInfo.liquidationThreshold.value` | `lltv` |
| `supplyInfo.apy.value` | `supply_apy` |
| `borrowInfo.apy.value` | `borrow_apy` |
| `usdExchangeRate` | `loan_asset_price_usd` |

**Market ID format:** `{chain_id}-{token_address}` (e.g., `1-0xa0b86991...`)

## Tips for Development

1. **Always read files before editing** - Understand existing patterns
2. **Use Decimal for money** - Never `float` for financial values
3. **Check market cache** - `_market_cache` in `DebtRebalancingOptimizer` stores `Market` objects with prices
4. **Async everywhere** - Data layer is fully async
5. **Test with real data** - Run UI to verify changes visually
6. **Watch rate limits** - Morpho (5000/5min), Aave (1000/min)
7. **Both APIs are free** - No API keys required for Morpho or Aave

## Recent Changes

### Debt Optimizer: Aave & Cross-Protocol Support (Latest)
- **Aave integration**: Debt optimizer now supports Aave v3 protocol
- **Cross-protocol rebalancing**: New "Cross-Protocol" mode fetches markets from both Morpho and Aave
- Protocol selector in UI: Morpho Blue, Aave v3, or Cross-Protocol
- Markets table shows "Proto" column (M/A) in cross-protocol mode
- Proper handling of Aave's MULTI collateral model (matches only on loan asset)

**Key files:**
- `src/protocols/aave/assets.py` - Aave collateral/borrow asset addresses
- `src/sandbox/models/rebalancing.py` - Added `actual_collateral_asset`, `is_cross_protocol`, `protocols` properties
- `src/sandbox/engine/debt_optimizer.py` - Multi-protocol market discovery and price lookup
- `src/sandbox/data/aggregator.py` - Fixed protocol type conversion for proper API routing
- `src/ui/screens/debt_optimizer.py` - Protocol selector and dynamic asset options

**Bug fixes:**
- Fixed duplicate row key error in Aave markets (deduplicate by market ID)
- Fixed DataAggregator not passing protocol type to pipeline (always used Morpho)
- Fixed table column duplication on refresh (`table.clear(columns=True)`)

### Dynamic Risk-Free Rates
- Sharpe/Sortino now use asset-specific risk-free rates
- Stablecoins: T-bills rate from FRED API (~5%)
- WETH/ETH: Lido staking APR (~3.5%)
- wstETH and staked ETH derivatives: 0% (inherent yield)
- Added `src/data/sources/risk_free_rates.py` for rate fetching
- Added `FRED_API_KEY` config option for Treasury rates
- Rates cached for 1 hour to minimize API calls

### Code Quality Improvements
- Added `to_dict()` methods to all core models (Market, Vault, Position, etc.)
- Fixed `datetime.utcnow()` deprecation (Python 3.12+) → `datetime.now(timezone.utc)`
- Fixed `risk_free_rate` validator bug in settings
- Fixed `KPIStatus` import in analytics engine
- Added LRU cache eviction to `DebtRebalancingOptimizer` (TTL 5min, max 100 entries)
- Moved hardcoded addresses to `src/protocols/morpho/assets.py`

### Debt Optimizer Enhancement
- Added `_get_collateral_price()` for real prices from API
- Fixed borrow amount calculation: `collateral * price_usd * ltv / loan_price`
- Added dynamic price simulation in backtest
- Added compound interest tracking on debt
- Added margin call detection
- Updated UI to show USD values

### Debt Optimizer Math Fixes (v1.1)
- **Health Factor formula fixed**: Now uses correct `HF = (collateral × price × LLTV) / borrow`
- **Per-position debt tracking**: Each position accrues compound interest individually (instead of uniform scaling)
- **Linear price interpolation**: Realistic hourly price movement in simulations
- **Strict price validation**: Raises exception on missing price data (no silent fallback)
- **Preserved debt after rebalancing**: Accumulated interest is maintained when redistributing positions

### Aave v3 Integration (Latest)
- Added `AaveClient` implementing `ProtocolClient` interface
- **Uses official Aave API** at `https://api.v3.aave.com/graphql` (FREE, no API key!)
- Reserve-centric model: each reserve maps to a Market with `collateral_asset_symbol = "MULTI"`
- API returns decimal values directly (no RAY/WAD conversion needed)
- Market ID format: `{chain_id}-{token_address}`
- **Historical data support**: `supplyAPYHistory` and `borrowAPYHistory` queries
- Time windows: LAST_DAY, LAST_WEEK, LAST_MONTH, LAST_SIX_MONTHS, LAST_YEAR
- Full test coverage in `tests/unit/test_aave_api.py` (34 tests)

**UI Changes:**
- Added Aave tab in Lending & Borrowing screen
- Markets table now shows: Market ID, Loan, Collat, LLTV, Supply, **Borrow**, Util
- Removed "Created" column (not available from APIs)
- History (H) button works for Aave markets (uses Aave API, no Alchemy needed)

**Key files:**
- `src/data/clients/aave/client.py` - AaveClient with historical data
- `src/data/clients/aave/parser.py` - Response parsing
- `src/protocols/aave/config.py` - Rate limits, URLs, pool addresses
- `src/protocols/aave/queries.py` - GraphQL queries (markets + APY history)
- `src/ui/screens/lending/aave.py` - Aave lending screen
