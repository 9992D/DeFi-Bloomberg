# CLAUDE.md - DeFi Bloomberg Terminal

## Project Overview

DeFi-Bloomberg is a Bloomberg-style Terminal UI for monitoring and simulating DeFi lending positions. Built with Python and Textual TUI framework, it provides real-time analytics for decentralized finance markets with focus on **Morpho Blue** protocol.

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
│  ProtocolClients (MorphoClient GQL)             │
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
│   │   │   └── registry.py  # Client registration
│   │   └── sources/
│   │       └── morpho_api.py# Low-level GraphQL
│   │
│   ├── protocols/
│   │   └── morpho/
│   │       ├── config.py    # IRM params, addresses
│   │       ├── irm.py       # Interest Rate Model
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
│   │   └── test_morpho_api.py
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
- **`src/data/clients/morpho/client.py`**: `MorphoClient` - GraphQL API client
- **`src/data/cache/disk_cache.py`**: `DiskCache` - SQLite-based persistent cache

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
RISK_FREE_RATE=0                  # For Sharpe/Sortino
```

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

## Morpho Blue Specifics

### API Endpoint
GraphQL: `https://blue-api.morpho.org/graphql`
Rate limit: 5000 requests / 5 minutes

### Key Concepts
- **LLTV**: Liquidation Loan-to-Value (e.g., 0.86 = 86%)
- **Health Factor**: `(collateral * price * LLTV) / borrow`
- **IRM**: Interest Rate Model - Adaptive Curve IRM
- **Target Utilization**: 90% (where rates curve steepens)

### Price Calculations
```python
# Collateral price in loan terms (e.g., WBTC/USDC = 80000)
collateral_price = collateral_price_usd / loan_price_usd

# Borrow amount in loan tokens
borrow_amount = (collateral_amount * collateral_price * ltv)

# Health Factor
hf = (collateral_amount * collateral_price * lltv) / borrow_amount
```

## Tips for Development

1. **Always read files before editing** - Understand existing patterns
2. **Use Decimal for money** - Never `float` for financial values
3. **Check market cache** - `_market_cache` in `DebtRebalancingOptimizer` stores `Market` objects with prices
4. **Async everywhere** - Data layer is fully async
5. **Test with real data** - Run UI to verify changes visually
6. **Watch rate limits** - Morpho API has strict limits

## Recent Changes

### Debt Optimizer Enhancement (Latest)
- Added `_get_collateral_price()` for real prices from API
- Fixed borrow amount calculation: `collateral * price_usd * ltv / loan_price`
- Added dynamic price simulation in backtest
- Added compound interest tracking on debt
- Added margin call detection
- Updated UI to show USD values
