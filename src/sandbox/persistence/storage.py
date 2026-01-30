"""Strategy and simulation result storage."""

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.sandbox.models import StrategyConfig, SimulationResult, StrategyType

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class StrategyStorage:
    """
    Persistent storage for strategy configurations and simulation results.
    
    Uses JSON files for simplicity and human-readability.
    Directory structure:
        storage_dir/
            strategies/
                {strategy_id}.json
            results/
                {strategy_id}/
                    {timestamp}.json
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize storage.
        
        Args:
            storage_dir: Base directory for storage (default: ~/.morpho_sandbox)
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".morpho_sandbox"
        
        self.storage_dir = Path(storage_dir)
        self.strategies_dir = self.storage_dir / "strategies"
        self.results_dir = self.storage_dir / "results"
        
        # Ensure directories exist
        self.strategies_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    # Strategy Configuration Methods
    
    def save_strategy(self, config: StrategyConfig, strategy_id: Optional[str] = None) -> str:
        """
        Save a strategy configuration.
        
        Args:
            config: Strategy configuration to save
            strategy_id: Optional custom ID (default: auto-generated)
            
        Returns:
            Strategy ID
        """
        if strategy_id is None:
            strategy_id = self._generate_strategy_id(config)
        
        file_path = self.strategies_dir / f"{strategy_id}.json"
        
        data = config.to_dict()
        data["_id"] = strategy_id
        data["_saved_at"] = datetime.utcnow().isoformat()
        
        with open(file_path, "w") as f:
            json.dump(data, f, cls=DecimalEncoder, indent=2)
        
        logger.info(f"Saved strategy: {strategy_id}")
        return strategy_id
    
    def load_strategy(self, strategy_id: str) -> Optional[StrategyConfig]:
        """
        Load a strategy configuration.
        
        Args:
            strategy_id: Strategy ID to load
            
        Returns:
            StrategyConfig or None if not found
        """
        file_path = self.strategies_dir / f"{strategy_id}.json"
        
        if not file_path.exists():
            logger.warning(f"Strategy not found: {strategy_id}")
            return None
        
        with open(file_path, "r") as f:
            data = json.load(f)
        
        # Remove metadata fields before parsing
        data.pop("_id", None)
        data.pop("_saved_at", None)
        
        return StrategyConfig.from_dict(data)
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """
        List all saved strategies.
        
        Returns:
            List of strategy summaries (id, name, type, market)
        """
        strategies = []
        
        for file_path in self.strategies_dir.glob("*.json"):
            with open(file_path, "r") as f:
                data = json.load(f)
            
            strategies.append({
                "id": data.get("_id", file_path.stem),
                "name": data.get("name"),
                "strategy_type": data.get("strategy_type"),
                "market_id": data.get("market_id"),
                "initial_capital": data.get("initial_capital"),
                "saved_at": data.get("_saved_at"),
            })
        
        # Sort by saved_at descending
        strategies.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
        return strategies
    
    def delete_strategy(self, strategy_id: str) -> bool:
        """
        Delete a strategy configuration.
        
        Args:
            strategy_id: Strategy ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        file_path = self.strategies_dir / f"{strategy_id}.json"
        
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted strategy: {strategy_id}")
            return True
        
        return False
    
    # Simulation Result Methods
    
    def save_result(
        self,
        result: SimulationResult,
        strategy_id: str,
        result_id: Optional[str] = None,
    ) -> str:
        """
        Save a simulation result.
        
        Args:
            result: Simulation result to save
            strategy_id: Associated strategy ID
            result_id: Optional custom result ID
            
        Returns:
            Result ID
        """
        if result_id is None:
            result_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Create strategy results directory
        result_dir = self.results_dir / strategy_id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = result_dir / f"{result_id}.json"
        
        data = result.to_dict()
        data["_id"] = result_id
        data["_strategy_id"] = strategy_id
        
        with open(file_path, "w") as f:
            json.dump(data, f, cls=DecimalEncoder, indent=2)
        
        logger.info(f"Saved result: {strategy_id}/{result_id}")
        return result_id
    
    def load_result(self, strategy_id: str, result_id: str) -> Optional[SimulationResult]:
        """
        Load a simulation result.
        
        Args:
            strategy_id: Strategy ID
            result_id: Result ID
            
        Returns:
            SimulationResult or None if not found
        """
        file_path = self.results_dir / strategy_id / f"{result_id}.json"
        
        if not file_path.exists():
            logger.warning(f"Result not found: {strategy_id}/{result_id}")
            return None
        
        with open(file_path, "r") as f:
            data = json.load(f)
        
        return self._parse_result(data)
    
    def list_results(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        List all results for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            List of result summaries
        """
        result_dir = self.results_dir / strategy_id
        
        if not result_dir.exists():
            return []
        
        results = []
        for file_path in result_dir.glob("*.json"):
            with open(file_path, "r") as f:
                data = json.load(f)
            
            metrics = data.get("metrics", {})
            results.append({
                "id": data.get("_id", file_path.stem),
                "strategy_id": strategy_id,
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time"),
                "success": data.get("success"),
                "total_return_percent": metrics.get("total_return_percent"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "max_drawdown": metrics.get("max_drawdown"),
            })
        
        # Sort by start_time descending
        results.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        return results
    
    def get_latest_result(self, strategy_id: str) -> Optional[SimulationResult]:
        """
        Get the most recent result for a strategy.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Most recent SimulationResult or None
        """
        results = self.list_results(strategy_id)
        
        if not results:
            return None
        
        return self.load_result(strategy_id, results[0]["id"])
    
    def delete_result(self, strategy_id: str, result_id: str) -> bool:
        """
        Delete a simulation result.
        
        Args:
            strategy_id: Strategy ID
            result_id: Result ID
            
        Returns:
            True if deleted, False if not found
        """
        file_path = self.results_dir / strategy_id / f"{result_id}.json"
        
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted result: {strategy_id}/{result_id}")
            return True
        
        return False
    
    # Helper Methods
    
    def _generate_strategy_id(self, config: StrategyConfig) -> str:
        """Generate a unique strategy ID from config."""
        # Use name + type + timestamp
        import re
        safe_name = config.name.lower()
        safe_name = re.sub(r'[^a-z0-9]+', '_', safe_name)[:20]
        safe_name = safe_name.strip('_')
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{timestamp}"
    
    def _parse_result(self, data: Dict[str, Any]) -> SimulationResult:
        """Parse a simulation result from JSON data."""
        from src.sandbox.models import (
            SimulationResult,
            SimulationPoint,
            SimulationMetrics,
            SimulatedPosition,
        )
        
        # Parse points
        points = []
        for p_data in data.get("points", []):
            point = SimulationPoint(
                timestamp=datetime.fromisoformat(p_data["timestamp"]),
                supply_amount=Decimal(p_data["supply_amount"]),
                borrow_amount=Decimal(p_data["borrow_amount"]),
                leverage=Decimal(p_data["leverage"]),
                health_factor=Decimal(p_data["health_factor"]),
                collateral_price=Decimal(p_data["collateral_price"]),
                supply_apy=Decimal(p_data["supply_apy"]),
                borrow_apy=Decimal(p_data["borrow_apy"]),
                pnl=Decimal(p_data["pnl"]),
                pnl_percent=Decimal(p_data["pnl_percent"]),
                net_apy=Decimal(p_data["net_apy"]),
                liquidated=p_data.get("liquidated", False),
                rebalanced=p_data.get("rebalanced", False),
                action=p_data.get("action", ""),
            )
            points.append(point)
        
        # Parse metrics
        metrics = None
        if data.get("metrics"):
            m = data["metrics"]
            metrics = SimulationMetrics(
                total_return=Decimal(m["total_return"]),
                total_return_percent=Decimal(m["total_return_percent"]),
                annualized_return=Decimal(m["annualized_return"]),
                max_drawdown=Decimal(m["max_drawdown"]),
                volatility=Decimal(m["volatility"]),
                sharpe_ratio=Decimal(m["sharpe_ratio"]),
                sortino_ratio=Decimal(m["sortino_ratio"]),
                avg_health_factor=Decimal(m["avg_health_factor"]),
                min_health_factor=Decimal(m["min_health_factor"]),
                max_health_factor=Decimal(m["max_health_factor"]),
                liquidation_count=m["liquidation_count"],
                rebalance_count=m["rebalance_count"],
                avg_leverage=Decimal(m["avg_leverage"]),
                max_leverage=Decimal(m["max_leverage"]),
                simulation_days=m["simulation_days"],
                data_points=m["data_points"],
            )
        
        # Parse final position
        final_position = None
        if data.get("final_position"):
            final_position = SimulatedPosition.from_dict(data["final_position"])
        
        return SimulationResult(
            strategy_name=data["strategy_name"],
            strategy_type=data["strategy_type"],
            market_id=data["market_id"],
            initial_capital=Decimal(data["initial_capital"]),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            final_position=final_position,
            points=points,
            metrics=metrics,
            success=data.get("success", True),
            error_message=data.get("error_message", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            parameters=data.get("parameters", {}),
        )
