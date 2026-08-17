# core/model_registry.py
import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class ModelBundle:
    model_version: str
    feature_schema_hash: str
    model_weights_path: str
    calibrator_params: Dict[str, Any]
    policy_version: int
    timestamp: float
    dataset_id: str

REGISTRY_FILE = "configs/model_registry.json"

class ModelRegistry:
    """Manages atomic active model bundle promotion, tracking, and rollbacks thread-safely."""
    
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.ModelRegistry")
        self.active_bundle: Optional[ModelBundle] = None
        self.history: List[ModelBundle] = []
        self._lock = threading.Lock()
        self.load_registry()

    def load_registry(self) -> None:
        """Loads the registry state from configs."""
        with self._lock:
            try:
                if os.path.exists(REGISTRY_FILE):
                    with open(REGISTRY_FILE, "r") as f:
                        data = json.load(f)
                    
                    hist_data = data.get("history", [])
                    self.history = [ModelBundle(**b) for b in hist_data]
                    
                    active_data = data.get("active")
                    if active_data:
                        self.active_bundle = ModelBundle(**active_data)
                else:
                    # Initialize default bundle state
                    self.active_bundle = ModelBundle(
                        model_version="NN-CHAMPION-V1",
                        feature_schema_hash="DEFAULT_HASH",
                        model_weights_path="models/champion.pt",
                        calibrator_params={"temperature": 1.0},
                        policy_version=1,
                        timestamp=0.0,
                        dataset_id="INITIAL_BOOTSTRAP"
                    )
                    self._save_registry_locked()
            except Exception as e:
                self.logger.error(f"Failed to load model registry: {e}")

    def get_active_bundle(self) -> Optional[ModelBundle]:
        self.load_registry()
        with self._lock:
            return self.active_bundle

    def promote_bundle(self, bundle: ModelBundle) -> None:
        """Promotes a new challenger model bundle to champion and persists registry state atomically."""
        with self._lock:
            if self.active_bundle:
                self.history.append(self.active_bundle)
                # Keep history size to last 5 bundles
                if len(self.history) > 5:
                    self.history.pop(0)
            
            self.active_bundle = bundle
            self._save_registry_locked()
            self.logger.warning(
                f"🎉 Model bundle promoted successfully: version={bundle.model_version} "
                f"schema={bundle.feature_schema_hash[:8]} weights={bundle.model_weights_path}"
            )

    def rollback(self) -> bool:
        """Rolls back to the previous champion bundle if history exists."""
        with self._lock:
            if not self.history:
                self.logger.error("Rollback failed: No model history available.")
                return False
            
            previous = self.history.pop()
            self.active_bundle = previous
            self._save_registry_locked()
            self.logger.warning(f"↩️ Rolled back active model bundle to: version={previous.model_version}")
            return True

    def _save_registry_locked(self) -> None:
        """Saves registry metadata atomically to file. Must hold self._lock."""
        try:
            os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
            temp_file = REGISTRY_FILE + ".tmp"
            
            data = {
                "active": asdict(self.active_bundle) if self.active_bundle else None,
                "history": [asdict(b) for b in self.history]
            }
            
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=4)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(temp_file, REGISTRY_FILE)
        except Exception as e:
            self.logger.error(f"Failed to save model registry atomically: {e}")

# Global instance for registry coordination
model_registry = ModelRegistry()
