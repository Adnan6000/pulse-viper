# core/learning_engine.py
import threading
import copy

class AsynchronousMultiTimeframeTrainer:
    def __init__(self, neural_net_model, learning_pipeline):
        self.model = neural_net_model
        self.pipeline = learning_pipeline
        self.worker_lock = threading.Lock()

    def trigger_background_timeframe_training(self, historical_market_matrix):
        """
        Invokes multi-timeframe model adjustments safely on background threads
        """
        if not self.worker_lock.acquire(blocking=False):
            return # Skip iteration if a background training task is currently active
            
        # Spawn off-thread worker to protect main loop execution speed
        threading.Thread(
            target=self._async_training_worker_routine, 
            args=(historical_market_matrix,),
            daemon=True
        ).start()

    def _async_training_worker_routine(self, historical_market_matrix):
        try:
            # 1. Create a deep-copied candidate model for training
            candidate_model = copy.deepcopy(self.model)
            
            # Sequentially optimize networks across M1, M5, H1, H4, D1 datasets
            for timeframe in ["M1", "M5", "H1", "H4", "D1"]:
                timeframe_data = historical_market_matrix.get(timeframe)
                if timeframe_data is not None:
                    self.pipeline.train_timeframe_layer(candidate_model, timeframe_data)
            
            # 2. Validate and promote candidate model
            # Extract validation features from M5 timeframe data if available
            validation_data = historical_market_matrix.get("M5")
            inputs_val, targets_val = None, None
            if validation_data is not None:
                inputs_val, targets_val = self.pipeline.extract_vectorized_features(validation_data)
            
            if self.pipeline._validate_and_promote(candidate_model, inputs_val, targets_val):
                with self.pipeline.model_lock:
                    # Atomic swap of the live inference model reference
                    self.pipeline.nn_model = candidate_model
                    self.model = candidate_model
                    self.pipeline.nn_ready = True
                self.pipeline.save_nn_model()
                self.pipeline.logger.info("🏆 Asynchronous challenger model promoted successfully to live champion.")
            else:
                self.pipeline.logger.warning("⚠️ Asynchronous challenger model failed promotion benchmarks.")
        finally:
            self.worker_lock.release()
