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
| Sharpe Ratio | Risk-adjusted return (0% risk-free rate) |
| Sortino Ratio | Downside-only risk adjustment |
| Mean Reversion | Ornstein-Uhlenbeck half-life |
| Utilization-Adjusted Return | Yield penalized by utilization risk |

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

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Morpho Labs](https://morpho.org/) for the excellent API
- [Textualize](https://www.textualize.io/) for the Textual framework
