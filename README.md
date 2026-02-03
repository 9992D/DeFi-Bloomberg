# DeFi Bloomberg

Bloomberg-style Terminal UI for monitoring and simulating DeFi protocol positions, built with Python and Textual.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

### 📊 Morpho Blue Dashboard
- **Markets View**: Real-time monitoring of Morpho Blue lending markets
  - Supply/Borrow APY, Utilization, TVL
  - Historical data with sparklines
  - KPIs: Sharpe ratio, volatility, mean reversion
  
- **Vaults View**: MetaMorpho vault analytics
  - Share price evolution, TVL tracking
  - Allocation breakdown across markets
  - Performance metrics

### 🧪 Sandbox - Vault Allocation Simulator
Simulate vault allocation strategies across multiple Morpho markets.

**Strategies:**
- **Waterfill**: Optimize allocations to equalize marginal yields
- **Yield-Weighted**: Allocate proportionally to APY
- **Equal**: Simple 1/N allocation

**Features:**
- Filter markets by loan token (USDC, WETH, etc.)
- Configurable rebalancing frequency
- Min/Max allocation constraints
- Benchmark comparison (equal-weight, no rebalancing)
- Performance metrics: Return, Sharpe, Max Drawdown
- Charts: PnL evolution, Excess return, Weighted APY

### 💰 Debt Rebalancing Optimizer
Optimize debt positions across multiple lending markets to minimize borrowing costs while maintaining safe health factors.

**Features:**
- Accurate Health Factor calculation: `HF = (collateral × price × LLTV) / borrow`
- Per-position debt tracking with individual compound interest
- Linear price interpolation for realistic hourly simulation
- Dynamic rebalancing based on rate changes
- Risk analysis with price scenario modeling (5%-30% drops)
- Margin call detection and tracking

## Architecture

```
morpho_tracker/
├── config/
│   └── settings.py              # Pydantic settings (API keys, cache config)
├── src/
│   ├── core/
│   │   └── models/              # Market, Position, KPI dataclasses
│   ├── data/
│   │   ├── sources/
│   │   │   └── morpho_api.py    # GraphQL client for Morpho API
│   │   ├── cache/
│   │   │   └── disk_cache.py    # SQLite cache with TTL
│   │   └── pipeline.py          # Data fetching orchestration
│   ├── analytics/
│   │   └── kpis/                # KPI calculators (Sharpe, volatility, etc.)
│   ├── sandbox/
│   │   ├── models/              # Allocation configs and results
│   │   ├── engine/
│   │   │   └── allocator.py     # Allocation simulator with strategies
│   │   ├── data/
│   │   │   └── aggregator.py    # Unified data access layer
│   │   └── persistence/
│   │       └── storage.py       # JSON storage for strategies
│   └── ui/
│       ├── app.py               # Main Textual application
│       ├── screens/
│       │   ├── morpho.py        # Morpho protocol screen
│       │   ├── markets.py       # Markets tab
│       │   ├── vaults.py        # Vaults tab
│       │   └── sandbox.py       # Sandbox simulation tab
│       └── widgets/             # Custom UI components
└── tests/
```

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/defi-bloomberg.git
cd defi-bloomberg

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your settings (optional)
```

## Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the application
python -m src.ui.app
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Morpho tab |
| `2` | Sandbox tab |
| `M` | Markets view |
| `V` | Vaults view |
| `H` | Historical data |
| `R` | Refresh |
| `Q` | Quit |

### Sandbox Controls

| Key | Action |
|-----|--------|
| `A` | Add selected market |
| `C` | Clear selection |
| `Enter` | Run simulation |

## Configuration

Create a `.env` file:

```bash
# Optional: Alchemy API key for additional RPC data
ETH_ALCHEMY_API_KEY=your_key_here

# Cache settings
CACHE_DIR=.cache/morpho
CACHE_TTL_SECONDS=300

# UI settings
UI_REFRESH_INTERVAL=60
```

## Data Sources

- **Primary**: [Morpho GraphQL API](https://api.morpho.org/graphql)
  - Markets, vaults, positions, historical timeseries
  - Rate limit: 5000 requests/5min

- **Backup**: Direct RPC via web3.py (for real-time rates)

## KPIs Implemented

| KPI | Description |
|-----|-------------|
| Volatility | Annualized rate volatility |
| Sharpe Ratio | Risk-adjusted return with dynamic risk-free rates |
| Sortino Ratio | Downside-only risk adjustment with dynamic risk-free rates |
| Mean Reversion | Ornstein-Uhlenbeck half-life |
| Utilization-Adjusted Return | Yield penalized by utilization risk |

### Dynamic Risk-Free Rates

Sharpe and Sortino ratios use contextually appropriate risk-free rates based on the asset type:

| Asset Type | Risk-Free Rate Source |
|------------|----------------------|
| Stablecoins (USDC, USDT, DAI, etc.) | US Treasury Bills rate (FRED API) |
| ETH / WETH | Lido staking APR |
| wstETH | 0% (inherent staking yield) |
| Other tokens | 0% |

Risk-free rates are prefetched at application startup and cached for 1 hour to minimize API calls.

## Tech Stack

- **UI**: [Textual](https://textual.textualize.io/) - Modern TUI framework
- **Data**: [GQL](https://gql.readthedocs.io/) - GraphQL client
- **Analytics**: NumPy, SciPy
- **Config**: Pydantic Settings
- **Cache**: DiskCache (SQLite-based)

## Screenshots

```
┌─────────────────────────────────────────────────────────────┐
│ DeFi Protocol Tracker                                       │
├─────────────────────────────────────────────────────────────┤
│ ┌─Morpho─┐ ┌─Sandbox─┐                                      │
│ │Markets │ │ Vaults  │                                      │
│ ├────────┴─┴─────────────────────────────────────────────── │
│ │ Market          │ Supply │ Borrow │  Util  │    TVL      │
│ │─────────────────│────────│────────│────────│─────────────│
│ │ wstETH/WETH     │  3.82% │  4.12% │ 89.2%  │   $210.6M   │
│ │ cbBTC/USDC      │  3.30% │  3.58% │ 85.1%  │   $518.3M   │
│ │ WBTC/USDC       │  3.28% │  3.55% │ 84.7%  │   $171.7M   │
│ └────────────────────────────────────────────────────────── │
│ 1: Morpho  2: Sandbox | M: Markets  V: Vaults | R: Refresh  │
└─────────────────────────────────────────────────────────────┘
```

## Recent Improvements

### Dynamic Risk-Free Rates for Sharpe/Sortino (v1.1)
- Stablecoins (USDC, USDT, DAI, etc.) use US T-bills rate from FRED API
- ETH/WETH uses Lido staking APR as the opportunity cost
- wstETH uses 0% (already includes staking yield)
- Other tokens default to 0%
- Rates are prefetched at app startup and cached for 1 hour

### Debt Optimizer Enhancements (v1.1)
- **Fixed Health Factor calculation**: Now uses correct formula `HF = (collateral × price × LLTV) / borrow`
- **Per-position debt tracking**: Individual compound interest calculation instead of uniform scaling
- **Linear price interpolation**: Realistic hourly simulation with interpolated prices between data points
- **Proper error handling**: Raises exception when price data is missing instead of silent fallback
- **Preserved accumulated debt**: Debt properly persists after rebalancing events

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Morpho Labs](https://morpho.org/) for the excellent API
- [Textualize](https://www.textualize.io/) for the Textual framework
