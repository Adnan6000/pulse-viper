# core/execution_service.py
import hashlib
import json
import time
import threading
import MetaTrader5 as raw_mt5
from datetime import datetime, timezone
from typing import Optional
from core.execution_token import ExecutionValidationToken, validation_token_store

def canonical_request_hash(request: dict) -> str:
    """Computes a canonical SHA-256 fingerprint for verification."""
    canonical = {
        "symbol": str(request.get("symbol", "")),
        "action": int(request.get("action", 0)),
        "type": int(request.get("type", 0)),
        "volume": round(float(request.get("volume", 0.0)), 4),
        "sl": round(float(request.get("sl", 0.0)), 5),
        "tp": round(float(request.get("tp", 0.0)), 5),
        "magic": int(request.get("magic", 0)),
        "price": round(float(request.get("price", 0.0)), 5)
    }
    dumped = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(dumped.encode('utf-8')).hexdigest()

class MT5ExecutionService:
    """Privileged service that acts as a secure boundary for MetaTrader 5 order execution."""
    def __init__(self, emergency_halt_event: threading.Event, token_store = None):
        self._emergency_halt_event = emergency_halt_event
        self._token_store = token_store if token_store is not None else validation_token_store
        self._execution_lock = threading.Lock()

    def submit_order(self, token: ExecutionValidationToken, request: dict):
        class RejectedResult:
            def __init__(self, comment: str, retcode: int = 10014):
                self.retcode = retcode
                self.comment = comment
                self.order = 0
                self.volume = 0.0
                self.price = 0.0

        with self._execution_lock:
            # 1. Immediate Halt Check
            if self._emergency_halt_event.is_set():
                return RejectedResult("REJECTED_EMERGENCY_HALT")

            # 2. Token Consumption
            stored_token = self._token_store.consume(token.token_id)
            if stored_token is None:
                return RejectedResult("TOKEN_UNKNOWN_OR_ALREADY_USED")

            # 3. Token Expiration
            if datetime.now(timezone.utc) > stored_token.expires_at_utc:
                return RejectedResult("TOKEN_EXPIRED")

            # 4. Fingerprint Matching
            fingerprint = canonical_request_hash(request)
            if fingerprint != stored_token.request_fingerprint:
                return RejectedResult("REQUEST_FINGERPRINT_MISMATCH")

            # 5. Final Submission Revalidation
            reval = self._final_submission_revalidation(stored_token, request)
            if not reval.allowed:
                return RejectedResult(reval.reason)

            # Double-check emergency halt before raw submit
            if self._emergency_halt_event.is_set():
                return RejectedResult("REJECTED_EMERGENCY_HALT")

            # 6. Execute via raw MetaTrader5
            return raw_mt5.order_send(request)  # type: ignore[attr-defined]

    def _final_submission_revalidation(self, token: ExecutionValidationToken, request: dict):
        class RevalResult:
            allowed = True
            reason = ""

        symbol = request.get("symbol", "")
        tick = raw_mt5.symbol_info_tick(symbol)  # type: ignore[attr-defined]
        if tick is None:
            res = RevalResult()
            res.allowed = False
            res.reason = "REVALIDATION_TICK_UNAVAILABLE"
            return res

        # Revalidate spread freshness
        now_ms = time.time()
        tick_time = tick.time_msc / 1000.0 if hasattr(tick, 'time_msc') else tick.time
        if abs(now_ms - tick_time) > 10.0:  # 10s threshold
            res = RevalResult()
            res.allowed = False
            res.reason = "REVALIDATION_TICK_STALE"
            return res

        return RevalResult()
