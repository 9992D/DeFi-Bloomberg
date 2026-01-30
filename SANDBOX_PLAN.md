# Sandbox - Plan d'Implémentation

## Overview

Module de simulation de stratégies DeFi utilisant les données Morpho. MVP: Leverage Loop wstETH/ETH.

## Architecture

```
src/
├── sandbox/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── position.py          # Position simulée (supply, borrow, collateral)
│   │   ├── strategy.py          # Base Strategy + configs
│   │   └── simulation.py        # Résultats de simulation
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseStrategy ABC
│   │   ├── leverage_loop.py     # Leverage looping strategy
│   │   ├── rebalancing.py       # (Phase 2)
│   │   └── yield_optimizer.py   # (Phase 2)
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── simulator.py         # Moteur de simulation temporelle
│   │   ├── risk.py              # Calculs de risque (health factor, liquidation)
│   │   └── optimizer.py         # Optimization de paramètres
│   ├── persistence/
│   │   ├── __init__.py
│   │   └── storage.py           # Sauvegarde/chargement strategies
│   └── data/
│       ├── __init__.py
│       └── aggregator.py        # Agrège données de tous les pipelines
└── ui/
    └── screens/
        └── sandbox.py           # UI Sandbox
```

## Phase 1: Foundation (MVP Leverage Loop)

### 1.1 Models

```python
# position.py
@dataclass
class SimulatedPosition:
    market_id: str
    supply_amount: Decimal      # Collateral deposited (e.g., wstETH)
    borrow_amount: Decimal      # Borrowed amount (e.g., ETH)
    supply_asset: str
    borrow_asset: str
    entry_price: Decimal        # Prix d'entrée du collateral
    entry_timestamp: datetime

    # Calculated
    leverage: Decimal           # effective leverage
    health_factor: Decimal
    liquidation_price: Decimal
    net_apy: Decimal            # supply_apy - borrow_apy * leverage

# strategy.py
@dataclass
class StrategyConfig:
    name: str
    strategy_type: str          # "leverage_loop", "rebalancing", etc.
    market_id: str
    initial_capital: Decimal    # USD or token amount
    parameters: Dict[str, Any]  # Strategy-specific params
    constraints: StrategyConstraints

@dataclass
class StrategyConstraints:
    max_leverage: Decimal = Decimal("5.0")
    min_health_factor: Decimal = Decimal("1.2")
    max_position_size_usd: Decimal = Decimal("1000000")
    rebalance_threshold: Decimal = Decimal("0.05")  # 5%
```

### 1.2 Leverage Loop Strategy

```python
# leverage_loop.py
class LeverageLoopStrategy(BaseStrategy):
    """
    Leverage Loop: Deposit collateral → Borrow → Swap to collateral → Re-deposit

    Example wstETH/ETH:
    1. Deposit 10 wstETH as collateral
    2. Borrow ETH (up to LLTV)
    3. Swap ETH → wstETH
    4. Re-deposit wstETH
    5. Repeat until target leverage

    Profit from: wstETH yield > ETH borrow rate
    Risk: wstETH/ETH depeg → liquidation
    """

    def __init__(self, config: StrategyConfig):
        self.target_leverage: Decimal  # e.g., 3x
        self.loops: int                 # Number of loop iterations
        self.market: Market

    def simulate(self,
                 timeseries: List[TimeseriesPoint],
                 initial_capital: Decimal) -> SimulationResult:
        """Run simulation over historical data."""

    def calculate_position(self,
                          capital: Decimal,
                          leverage: Decimal,
                          market_state: MarketState) -> SimulatedPosition:
        """Calculate position for given leverage."""

    def calculate_health_factor(self,
                                position: SimulatedPosition,
                                current_price: Decimal) -> Decimal:
        """Calculate current health factor."""
```

### 1.3 Risk Calculator

```python
# risk.py
class RiskCalculator:
    def health_factor(self, position: SimulatedPosition,
                      oracle_price: Decimal, lltv: Decimal) -> Decimal:
        """
        HF = (collateral_value * LLTV) / borrow_value
        HF < 1.0 → liquidation
        """

    def liquidation_price(self, position: SimulatedPosition,
                          lltv: Decimal) -> Decimal:
        """Price at which HF = 1.0"""

    def max_borrow(self, collateral_value: Decimal,
                   lltv: Decimal,
                   min_hf: Decimal = 1.2) -> Decimal:
        """Max borrow to maintain min health factor."""
```

### 1.4 Simulation Engine

```python
# simulator.py
class StrategySimulator:
    def __init__(self, data_aggregator: DataAggregator):
        self.data = data_aggregator

    async def run_simulation(self,
                            strategy: BaseStrategy,
                            start_date: datetime,
                            end_date: datetime,
                            interval: str = "HOUR") -> SimulationResult:
        """
        Run strategy simulation over time period.

        Returns:
            SimulationResult with:
            - positions over time
            - P&L curve
            - health factor curve
            - liquidation events
            - final metrics
        """

    async def optimize_parameters(self,
                                  strategy_type: str,
                                  market_id: str,
                                  param_ranges: Dict[str, Tuple],
                                  objective: str = "sharpe") -> OptimizationResult:
        """Find optimal parameters via grid search or bayesian optimization."""
```

### 1.5 Data Aggregator

```python
# aggregator.py
class DataAggregator:
    """Unified interface to all data pipelines."""

    def __init__(self, pipelines: Dict[str, DataPipeline]):
        self.pipelines = pipelines  # {"morpho": MorphoPipeline, ...}

    async def get_market_timeseries(self,
                                    protocol: str,
                                    market_id: str,
                                    interval: str = "HOUR",
                                    days: int = 90) -> List[TimeseriesPoint]:
        """Get hourly market data."""

    async def get_price_history(self,
                                asset: str,
                                interval: str = "HOUR",
                                days: int = 90) -> List[PricePoint]:
        """Get asset price history (from market data or external)."""
```

## Phase 2: UI

### 2.1 Sandbox Screen Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ SANDBOX - Strategy Simulator                                         │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────┐ ┌─────────────────────────────────────────┐ │
│ │ STRATEGY CONFIG     │ │ SIMULATION RESULTS                      │ │
│ │                     │ │                                         │ │
│ │ Type: [Leverage▼]   │ │ P&L Chart                               │ │
│ │ Market: [wstETH/ETH]│ │ ████████████████████████                │ │
│ │ Capital: [10] ETH   │ │                                         │ │
│ │ Leverage: [3.0]x    │ │ Health Factor                           │ │
│ │ Min HF: [1.2]       │ │ ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁                         │ │
│ │                     │ │                                         │ │
│ │ [Run Simulation]    │ ├─────────────────────────────────────────┤ │
│ │ [Optimize Params]   │ │ METRICS                                 │ │
│ │ [Save Strategy]     │ │ Net APY:      +12.5%                    │ │
│ │                     │ │ Total Return: +3.2%                     │ │
│ └─────────────────────┘ │ Max Drawdown: -1.5%                     │ │
│                         │ Sharpe:       2.34                      │ │
│ ┌─────────────────────┐ │ Liquidations: 0                         │ │
│ │ POSITION DETAILS    │ │ Avg HF:       1.45                      │ │
│ │                     │ │ Min HF:       1.21                      │ │
│ │ Supply:  30 wstETH  │ └─────────────────────────────────────────┘ │
│ │ Borrow:  20 ETH     │                                             │
│ │ Leverage: 3.0x      │                                             │
│ │ Health:   1.45      │                                             │ │
│ │ Liq Price: 0.92     │                                             │
│ └─────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Phase 3: Extensions

### 3.1 Additional Strategies
- **Rebalancing**: Auto-rebalance between markets based on APY
- **Yield Optimizer**: Find best vault allocation
- **Delta Neutral**: Hedge positions across protocols

### 3.2 Real Execution (Future)
- Transaction builder
- Wallet connection (WalletConnect)
- Multi-sig support

## Implementation Order

### Sprint 1: Core Models & Data (2-3h)
1. [ ] `sandbox/models/position.py` - Position model
2. [ ] `sandbox/models/strategy.py` - Strategy config
3. [ ] `sandbox/models/simulation.py` - Simulation results
4. [ ] `sandbox/data/aggregator.py` - Data aggregator
5. [ ] Update `morpho_api.py` - Add HOUR interval support (déjà fait)

### Sprint 2: Leverage Loop Strategy (2-3h)
1. [ ] `sandbox/strategies/base.py` - Base strategy ABC
2. [ ] `sandbox/strategies/leverage_loop.py` - Leverage loop impl
3. [ ] `sandbox/engine/risk.py` - Risk calculator
4. [ ] Tests unitaires

### Sprint 3: Simulation Engine (2h)
1. [ ] `sandbox/engine/simulator.py` - Time simulation
2. [ ] `sandbox/engine/optimizer.py` - Parameter optimization
3. [ ] Tests intégration

### Sprint 4: Persistence (1h)
1. [ ] `sandbox/persistence/storage.py` - JSON/SQLite storage
2. [ ] Save/Load strategies

### Sprint 5: UI (2-3h)
1. [ ] `ui/screens/sandbox.py` - Main sandbox screen
2. [ ] Strategy config panel
3. [ ] Results display
4. [ ] Charts (P&L, HF)

## Questions Ouvertes

1. **Prix wstETH/ETH**: Utiliser le ratio oracle Morpho ou source externe ?
2. **Swap simulation**: Supposer 0 slippage ou modéliser ?
3. **Compounding**: Réinvestir les yields automatiquement ?

---

Prêt à commencer ? On attaque Sprint 1 ?
