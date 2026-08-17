# core/execution_token.py
import threading
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Dict

@dataclass(frozen=True)
class ExecutionValidationToken:
    token_id: str
    decision_id: str
    candidate_id: str
    symbol: str
    action: str
    request_fingerprint: str
    issued_at_utc: datetime
    expires_at_utc: datetime
    validation_id: str

class ValidationTokenStore:
    """Thread-safe storage for one-time execution validation tokens."""
    def __init__(self):
        self._tokens: Dict[str, ExecutionValidationToken] = {}
        self._lock = threading.Lock()

    def store(self, token: ExecutionValidationToken) -> None:
        """Register a new token in the store."""
        with self._lock:
            # First clean up expired tokens to prevent leak
            self._purge_expired_locked()
            self._tokens[token.token_id] = token

    def consume(self, token_id: str) -> Optional[ExecutionValidationToken]:
        """Atomically consume and return a token, or return None if already consumed/expired."""
        with self._lock:
            self._purge_expired_locked()
            return self._tokens.pop(token_id, None)

    def consume_by_fingerprint(self, request_fingerprint: str) -> Optional[ExecutionValidationToken]:
        with self._lock:
            self._purge_expired_locked()
            for tid, tok in list(self._tokens.items()):
                if tok.request_fingerprint == request_fingerprint:
                    return self._tokens.pop(tid, None)
            return None

    def _purge_expired_locked(self) -> None:
        """Helper to remove expired tokens. Must be called while holding self._lock."""
        now = datetime.now(timezone.utc)
        expired_ids = [tid for tid, tok in self._tokens.items() if tok.expires_at_utc < now]
        for tid in expired_ids:
            self._tokens.pop(tid, None)

# Singleton global token store for engine composition
validation_token_store = ValidationTokenStore()
