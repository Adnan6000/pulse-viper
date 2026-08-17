from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Mapping


SETTINGS_FILE = "configs/settings.json"
AUDIT_LOG_FILE = "configs/settings_audit.json"

CONTROL_TOKEN_ENV = "PULSE_VIPER_CONTROL_TOKEN"


MODE_PROFILES = {
    "scalping": {
        "primary_timeframe": "M1",
        "context_timeframe": "M5",
        "higher_timeframe": "H1",
        "allow_overnight": False,
        "style": "FAST_INTRADAY",
    },

    "intraday": {
        "primary_timeframe": "M5",
        "context_timeframe": "M15",
        "higher_timeframe": "H1",
        "allow_overnight": False,
        "style": "SESSION_INTRADAY",
    },

    "swing": {
        "primary_timeframe": "M15",
        "context_timeframe": "H1",
        "higher_timeframe": "D1",
        "allow_overnight": True,
        "style": "MULTI_DAY",
    },
}


DEFAULT_SETTINGS: Dict[str, Any] = {
    # ---------------------------------------------------------------------
    # CORE EXECUTION
    # ---------------------------------------------------------------------

    "paper_mode": True,

    # Safe default.
    # Must be explicitly enabled by operator.
    "auto_trade_enabled": False,

    "trading_mode": "scalping",
    "primary_timeframe": "M1",

    "active_symbol": "XAUUSDm",

    # ---------------------------------------------------------------------
    # DATA / STRATEGY
    # ---------------------------------------------------------------------

    "use_tick_order_flow": True,

    "dynamic_regime_filter": False,
    "killzone_filter_enabled": False,
    "vsa_filter_enabled": False,

    "self_learning_filter": True,

    "disabled_setups": [],

    # ---------------------------------------------------------------------
    # SESSIONS
    # ---------------------------------------------------------------------

    "london_session_enabled": True,
    "ny_session_enabled": True,
    "asian_session_enabled": False,

    # ---------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ---------------------------------------------------------------------

    "break_even_enabled": True,
    "break_even_pips": 8.0,

    "trailing_stop_enabled": True,
    "trailing_stop_pips": 10.0,

    "hedging_mode": False,

    # Emergency hedge opening is not a safe default.
    "emergency_hedging_enabled": False,

    # ---------------------------------------------------------------------
    # RISK
    #
    # IMPORTANT:
    #
    # risk_percent uses PERCENT units.
    #
    # 0.05 = 0.05%
    # NOT 5%
    # ---------------------------------------------------------------------

    "risk_percent": 0.05,

    "dynamic_risk_enabled": True,

    "max_portfolio_heat": 5.0,

    "max_daily_trades": 100,

    # Compounding changes the sizing reference.
    # It NEVER bypasses SafetyEngine/RiskEngine/ExecutionValidator.
    "compounding_mode": False,

    # Manual lot means "requested fixed lot".
    # It is still rejected if actual monetary risk exceeds budget.
    "use_manual_lot": True,
    "manual_lot_size": 0.01,

    # ---------------------------------------------------------------------
    # ENTRY / GEOMETRY
    # ---------------------------------------------------------------------

    "max_spread_points": 120,

    "min_rr_ratio": 1.5,

    "max_sl_pips": 12.0,
    "default_tp_pips": 24.0,

    "min_ai_confidence": 0.75,

    "max_entry_distance_atr_coef": 3.0,

    # ---------------------------------------------------------------------
    # NEWS
    #
    # Real Forex Factory feed.
    # Manual schedule remains explicit opt-in.
    # ---------------------------------------------------------------------

    "news_filter_enabled": True,

    "use_live_news_feed": True,

    "use_manual_news_schedule": False,

    "news_lockout_minutes": 5,
    "news_cooldown_minutes": 5,

    # ---------------------------------------------------------------------
    # SAFETY ENGINE
    # ---------------------------------------------------------------------

    "safety_engine_enabled": True,

    "max_consecutive_losses": 10,

    "max_daily_drawdown_pct": 10.0,

    "max_weekly_drawdown_pct": 25.0,

    # ---------------------------------------------------------------------
    # EXECUTION VALIDATION
    # ---------------------------------------------------------------------

    "token_expiry_seconds": 30.0,

    "max_validation_token_age_ms": 5000.0,

    "max_price_drift_points": 50.0,

    "allow_untokenized_orders": False,

    "strict_mode": False,

    # ---------------------------------------------------------------------
    # CAUSAL SMC / HISTORY
    # ---------------------------------------------------------------------

    "smc_swing_window": 3,

    "smc_lookback_sweep": 20,

    "smc_lookback_mss": 15,

    "smc_fvg_lookback": 8,

    # ---------------------------------------------------------------------
    # INTERNAL
    # ---------------------------------------------------------------------

    "settings_version": 1,

    # Runtime secret only.
    #
    # Actual value is read from:
    #
    # PULSE_VIPER_CONTROL_TOKEN
    #
    # and is never persisted by this manager.
    "control_token": "",
}


SCHEMA: Dict[str, Dict[str, Any]] = {
    # Core execution
    "paper_mode": {
        "type": bool,
    },

    "auto_trade_enabled": {
        "type": bool,
    },

    "trading_mode": {
        "type": str,
        "choices": list(
            MODE_PROFILES
        ),
    },

    "primary_timeframe": {
        "type": str,
        "choices": [
            "M1",
            "M5",
            "M15",
        ],
    },

    "active_symbol": {
        "type": str,
        "min_length": 1,
        "max_length": 64,
    },

    # Strategy/data
    "use_tick_order_flow": {
        "type": bool,
    },

    "dynamic_regime_filter": {
        "type": bool,
    },

    "killzone_filter_enabled": {
        "type": bool,
    },

    "vsa_filter_enabled": {
        "type": bool,
    },

    "self_learning_filter": {
        "type": bool,
    },

    "disabled_setups": {
        "type": list,
    },

    # Sessions
    "london_session_enabled": {
        "type": bool,
    },

    "ny_session_enabled": {
        "type": bool,
    },

    "asian_session_enabled": {
        "type": bool,
    },

    # Trade management
    "break_even_enabled": {
        "type": bool,
    },

    "break_even_pips": {
        "type": float,
        "min": 0.0,
        "max": 500.0,
    },

    "trailing_stop_enabled": {
        "type": bool,
    },

    "trailing_stop_pips": {
        "type": float,
        "min": 0.0,
        "max": 500.0,
    },

    "hedging_mode": {
        "type": bool,
    },

    "emergency_hedging_enabled": {
        "type": bool,
    },

    # Risk
    "risk_percent": {
        "type": float,
        "min": 0.0,
        "max": 1.0,
    },

    "dynamic_risk_enabled": {
        "type": bool,
    },

    "max_portfolio_heat": {
        "type": float,
        "min": 0.1,
        "max": 10.0,
    },

    "max_daily_trades": {
        "type": int,
        "min": 1,
        "max": 1000,
    },

    "compounding_mode": {
        "type": bool,
    },

    "use_manual_lot": {
        "type": bool,
    },

    "manual_lot_size": {
        "type": float,
        "min": 0.01,
        "max": 100.0,
    },

    # Geometry
    "max_spread_points": {
        "type": int,
        "min": 1,
        "max": 10000,
    },

    "min_rr_ratio": {
        "type": float,
        "min": 1.0,
        "max": 10.0,
    },

    "max_sl_pips": {
        "type": float,
        "min": 1.0,
        "max": 500.0,
    },

    "default_tp_pips": {
        "type": float,
        "min": 1.0,
        "max": 1000.0,
    },

    "min_ai_confidence": {
        "type": float,
        "min": 0.0,
        "max": 1.0,
    },

    "max_entry_distance_atr_coef": {
        "type": float,
        "min": 0.1,
        "max": 50.0,
    },

    # News
    "news_filter_enabled": {
        "type": bool,
    },

    "use_live_news_feed": {
        "type": bool,
    },

    "use_manual_news_schedule": {
        "type": bool,
    },

    "news_lockout_minutes": {
        "type": int,
        "min": 0,
        "max": 1440,
    },

    "news_cooldown_minutes": {
        "type": int,
        "min": 0,
        "max": 1440,
    },

    # Safety
    "safety_engine_enabled": {
        "type": bool,
    },

    "max_consecutive_losses": {
        "type": int,
        "min": 1,
        "max": 100,
    },

    "max_daily_drawdown_pct": {
        "type": float,
        "min": 0.1,
        "max": 100.0,
    },

    "max_weekly_drawdown_pct": {
        "type": float,
        "min": 0.1,
        "max": 100.0,
    },

    # Execution validator
    "token_expiry_seconds": {
        "type": float,
        "min": 1.0,
        "max": 60.0,
    },

    "max_validation_token_age_ms": {
        "type": float,
        "min": 100.0,
        "max": 60000.0,
    },

    "max_price_drift_points": {
        "type": float,
        "min": 0.0,
        "max": 200.0,
    },

    "allow_untokenized_orders": {
        "type": bool,
    },

    "strict_mode": {
        "type": bool,
    },

    # SMC/history
    "smc_swing_window": {
        "type": int,
        "min": 1,
        "max": 20,
    },

    "smc_lookback_sweep": {
        "type": int,
        "min": 2,
        "max": 500,
    },

    "smc_lookback_mss": {
        "type": int,
        "min": 2,
        "max": 500,
    },

    "smc_fvg_lookback": {
        "type": int,
        "min": 1,
        "max": 500,
    },

    # Internal/runtime
    "settings_version": {
        "type": int,
        "min": 1,
        "max": 1000000,
    },

    "control_token": {
        "type": str,
    },
}


_RUNTIME_ONLY_KEYS = frozenset(
    {
        "control_token",
    }
)

_INTERNAL_ONLY_KEYS = frozenset(
    {
        "settings_version",
    }
)


class SettingsManager:
    """
    Thread-safe validated settings manager.

    Runtime trading configuration has one source of truth:
        this object.

    Settings are:
        - schema validated
        - atomically persisted
        - versioned
        - audited
        - cross-field normalized
        - secret-safe
    """

    def __init__(
        self,
        filepath: str = SETTINGS_FILE,
    ):
        self.filepath = (
            filepath
        )

        self.logger = logging.getLogger(
            "PulseViper.SettingsManager"
        )

        self.settings: Dict[
            str,
            Any,
        ] = {}

        self.last_mtime = (
            0.0
        )

        self._lock = (
            threading.RLock()
        )

        self.load_settings(
            force=True
        )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_value(
        self,
        key: str,
        value: Any,
    ) -> Any:

        if key not in SCHEMA:

            raise KeyError(
                (
                    f"Setting key "
                    f"'{key}' is not "
                    f"whitelisted."
                )
            )

        rule = (
            SCHEMA[
                key
            ]
        )

        expected_type = (
            rule[
                "type"
            ]
        )

        # bool is a subclass of int in Python.
        if (
            expected_type
            in (
                int,
                float,
            )
            and isinstance(
                value,
                bool,
            )
        ):

            raise ValueError(
                (
                    f"Setting '{key}' "
                    f"cannot be bool."
                )
            )

        if (
            expected_type
            is float
            and isinstance(
                value,
                int,
            )
        ):

            value = float(
                value
            )

        if not isinstance(
            value,
            expected_type,
        ):

            raise ValueError(
                (
                    f"Setting '{key}' "
                    f"expected "
                    f"{expected_type.__name__}, "
                    f"got "
                    f"{type(value).__name__}."
                )
            )

        choices = (
            rule.get(
                "choices"
            )
        )

        if (
            choices is not None
            and value
            not in choices
        ):

            raise ValueError(
                (
                    f"Setting '{key}' "
                    f"must be one of "
                    f"{choices}."
                )
            )

        if expected_type in (
            int,
            float,
        ):

            minimum = (
                rule.get(
                    "min"
                )
            )

            maximum = (
                rule.get(
                    "max"
                )
            )

            if (
                minimum
                is not None
                and value
                < minimum
            ):

                raise ValueError(
                    (
                        f"Setting '{key}' "
                        f"below minimum "
                        f"{minimum}."
                    )
                )

            if (
                maximum
                is not None
                and value
                > maximum
            ):

                raise ValueError(
                    (
                        f"Setting '{key}' "
                        f"above maximum "
                        f"{maximum}."
                    )
                )

        if expected_type is str:

            min_length = (
                rule.get(
                    "min_length"
                )
            )

            max_length = (
                rule.get(
                    "max_length"
                )
            )

            if (
                min_length
                is not None
                and len(
                    value
                )
                < min_length
            ):

                raise ValueError(
                    (
                        f"Setting '{key}' "
                        f"is too short."
                    )
                )

            if (
                max_length
                is not None
                and len(
                    value
                )
                > max_length
            ):

                raise ValueError(
                    (
                        f"Setting '{key}' "
                        f"is too long."
                    )
                )

        if key == "disabled_setups":

            cleaned = []

            seen = set()

            for item in value:

                name = (
                    str(
                        item
                    )
                    .strip()
                    .upper()
                )

                if (
                    not name
                    or name
                    in seen
                ):

                    continue

                seen.add(
                    name
                )

                cleaned.append(
                    name
                )

            return cleaned

        return value

    def _apply_cross_field_invariants(
        self,
        settings: Dict[
            str,
            Any,
        ],
    ) -> Dict[
        str,
        Any,
    ]:

        result = dict(
            settings
        )

        mode = result.get(
            "trading_mode",
            "scalping",
        )

        if mode not in (
            MODE_PROFILES
        ):

            mode = (
                "scalping"
            )

            result[
                "trading_mode"
            ] = mode

        # -------------------------------------------------------------
        # One mode = one canonical decision timeframe.
        #
        # Prevents contradictory states such as:
        #
        # trading_mode = swing
        # primary_timeframe = M1
        # -------------------------------------------------------------

        result[
            "primary_timeframe"
        ] = (
            MODE_PROFILES[
                mode
            ][
                "primary_timeframe"
            ]
        )

        # Secret never comes from disk.
        result[
            "control_token"
        ] = ""

        return result

    # =========================================================================
    # LOAD / SAVE
    # =========================================================================

    def load_settings(
        self,
        force: bool = False,
    ) -> None:

        with self._lock:

            try:

                if os.path.exists(
                    self.filepath
                ):

                    mtime = (
                        os.path.getmtime(
                            self.filepath
                        )
                    )

                    if (
                        not force
                        and self.settings
                        and self.last_mtime
                        and mtime
                        == self.last_mtime
                    ):

                        return

                    with open(
                        self.filepath,
                        "r",
                        encoding="utf-8",
                    ) as handle:

                        file_data = (
                            json.load(
                                handle
                            )
                        )

                    if not isinstance(
                        file_data,
                        Mapping,
                    ):

                        raise ValueError(
                            (
                                "settings JSON "
                                "root must be "
                                "an object"
                            )
                        )

                    merged = copy.deepcopy(
                        DEFAULT_SETTINGS
                    )

                    for (
                        key,
                        raw_value,
                    ) in (
                        file_data.items()
                    ):

                        if key not in SCHEMA:

                            self.logger.warning(
                                (
                                    "Ignoring unknown "
                                    "setting '%s'."
                                ),
                                key,
                            )

                            continue

                        if key in (
                            _RUNTIME_ONLY_KEYS
                        ):

                            continue

                        try:

                            merged[
                                key
                            ] = (
                                self._validate_value(
                                    key,
                                    raw_value,
                                )
                            )

                        except Exception as exc:

                            self.logger.error(
                                (
                                    "Rejected invalid "
                                    "setting '%s' "
                                    "during load: %s"
                                ),
                                key,
                                exc,
                            )

                    self.settings = (
                        self
                        ._apply_cross_field_invariants(
                            merged
                        )
                    )

                    self.last_mtime = (
                        mtime
                    )

                else:

                    self.settings = (
                        self
                        ._apply_cross_field_invariants(
                            copy.deepcopy(
                                DEFAULT_SETTINGS
                            )
                        )
                    )

                    self._save_settings_locked()

                self.logger.info(
                    (
                        "Settings loaded | "
                        "version=%s "
                        "mode=%s "
                        "paper=%s "
                        "auto=%s"
                    ),
                    self.settings.get(
                        "settings_version"
                    ),
                    self.settings.get(
                        "trading_mode"
                    ),
                    self.settings.get(
                        "paper_mode"
                    ),
                    self.settings.get(
                        "auto_trade_enabled"
                    ),
                )

            except Exception as exc:

                self.logger.exception(
                    (
                        "Settings load "
                        "failed; using "
                        "safe in-memory "
                        "defaults: %s"
                    ),
                    exc,
                )

                self.settings = (
                    self
                    ._apply_cross_field_invariants(
                        copy.deepcopy(
                            DEFAULT_SETTINGS
                        )
                    )
                )

    def _persistent_snapshot_locked(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        return {
            key: copy.deepcopy(
                value
            )
            for key, value
            in self.settings.items()
            if key
            not in _RUNTIME_ONLY_KEYS
        }

    def _save_settings_locked(
        self,
    ) -> None:

        directory = os.path.dirname(
            self.filepath
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True,
            )

        temp_path = (
            self.filepath
            + ".tmp"
        )

        try:

            with open(
                temp_path,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    self._persistent_snapshot_locked(),
                    handle,
                    indent=2,
                    allow_nan=False,
                )

                handle.flush()

                try:

                    os.fsync(
                        handle.fileno()
                    )

                except OSError:

                    pass

            os.replace(
                temp_path,
                self.filepath,
            )

            self.last_mtime = (
                os.path.getmtime(
                    self.filepath
                )
            )

        except Exception:

            try:

                if os.path.exists(
                    temp_path
                ):

                    os.remove(
                        temp_path
                    )

            except OSError:

                pass

            raise

    # =========================================================================
    # READ API
    # =========================================================================

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:

        self.load_settings()

        if key == "control_token":

            return os.environ.get(
                CONTROL_TOKEN_ENV,
                "",
            )

        with self._lock:

            if key in self.settings:

                return copy.deepcopy(
                    self.settings[
                        key
                    ]
                )

        if default is not None:

            return default

        return copy.deepcopy(
            DEFAULT_SETTINGS.get(
                key
            )
        )

    def get_all(
        self,
        include_secrets: bool = False,
    ) -> Dict[
        str,
        Any,
    ]:

        self.load_settings()

        with self._lock:

            snapshot = (
                copy.deepcopy(
                    self.settings
                )
            )

        if include_secrets:

            snapshot[
                "control_token"
            ] = (
                os.environ.get(
                    CONTROL_TOKEN_ENV,
                    "",
                )
            )

        else:

            snapshot.pop(
                "control_token",
                None,
            )

        return snapshot

    # =========================================================================
    # MODE API
    # =========================================================================

    def get_mode_profile(
        self,
        mode: str | None = None,
    ) -> Dict[
        str,
        Any,
    ]:

        selected = str(
            mode
            or self.get(
                "trading_mode",
                "scalping",
            )
        ).lower()

        if selected not in (
            MODE_PROFILES
        ):

            raise ValueError(
                (
                    f"Unknown trading "
                    f"mode '{selected}'."
                )
            )

        return copy.deepcopy(
            MODE_PROFILES[
                selected
            ]
        )

    # =========================================================================
    # COMPOUNDING REFERENCE
    # =========================================================================

    def get_risk_reference_balance(
        self,
        account_balance: float,
        account_equity: float,
        reference_balance: float | None = None,
    ) -> float:
        """
        Determine only the balance reference used for sizing.

        Compounding ON:
            use current equity.

        Compounding OFF:
            use supplied reference balance if available;
            otherwise current realized balance.

        This function DOES NOT approve a trade.

        SafetyEngine
            ↓
        RiskEngine
            ↓
        ExecutionValidator

        still own the actual risk gates.
        """

        balance = float(
            account_balance
        )

        equity = float(
            account_equity
        )

        if (
            balance <= 0.0
            or equity <= 0.0
        ):

            raise ValueError(
                (
                    "Balance and "
                    "equity must "
                    "both be positive."
                )
            )

        if bool(
            self.get(
                "compounding_mode",
                False,
            )
        ):

            return equity

        if reference_balance is not None:

            reference = float(
                reference_balance
            )

            if reference <= 0.0:

                raise ValueError(
                    (
                        "reference_balance "
                        "must be positive."
                    )
                )

            return reference

        return balance

    # =========================================================================
    # WRITE API
    # =========================================================================

    def set(
        self,
        key: str,
        value: Any,
        source: str = "SYSTEM",
        reason: str = "Unspecified",
    ) -> None:

        if key in (
            _RUNTIME_ONLY_KEYS
        ):

            raise ValueError(
                (
                    f"'{key}' is "
                    f"runtime-only. "
                    f"Set environment "
                    f"variable "
                    f"{CONTROL_TOKEN_ENV} "
                    f"instead."
                )
            )

        if key in (
            _INTERNAL_ONLY_KEYS
        ):

            raise ValueError(
                (
                    f"'{key}' is "
                    f"internally managed."
                )
            )

        validated = (
            self._validate_value(
                key,
                value,
            )
        )

        self.load_settings()

        with self._lock:

            old_snapshot = (
                copy.deepcopy(
                    self.settings
                )
            )

            old_value = (
                copy.deepcopy(
                    self.settings.get(
                        key
                    )
                )
            )

            # ---------------------------------------------------------
            # primary_timeframe cannot contradict trading_mode.
            # ---------------------------------------------------------

            if key == "primary_timeframe":

                expected = (
                    MODE_PROFILES[
                        self.settings.get(
                            "trading_mode",
                            "scalping",
                        )
                    ][
                        "primary_timeframe"
                    ]
                )

                if validated != expected:

                    raise ValueError(
                        (
                            "primary_timeframe "
                            "is derived from "
                            "trading_mode; "
                            f"expected "
                            f"'{expected}'."
                        )
                    )

            self.settings[
                key
            ] = validated

            # Mode transition atomically changes the canonical TF.
            if key == "trading_mode":

                self.settings[
                    "primary_timeframe"
                ] = (
                    MODE_PROFILES[
                        validated
                    ][
                        "primary_timeframe"
                    ]
                )

            self.settings = (
                self
                ._apply_cross_field_invariants(
                    self.settings
                )
            )

            if (
                old_snapshot
                == self.settings
            ):

                return

            new_version = (
                int(
                    old_snapshot.get(
                        "settings_version",
                        1,
                    )
                )
                + 1
            )

            self.settings[
                "settings_version"
            ] = new_version

            try:

                self._save_settings_locked()

            except Exception:

                self.settings = (
                    old_snapshot
                )

                raise

            self._log_audit_record(
                key=key,

                old_value=(
                    old_value
                ),

                new_value=(
                    copy.deepcopy(
                        self.settings.get(
                            key
                        )
                    )
                ),

                version=(
                    new_version
                ),

                source=(
                    source
                ),

                reason=(
                    reason
                ),
            )

            if key == "trading_mode":

                self._log_audit_record(
                    key=(
                        "primary_timeframe"
                    ),

                    old_value=(
                        old_snapshot.get(
                            "primary_timeframe"
                        )
                    ),

                    new_value=(
                        self.settings.get(
                            "primary_timeframe"
                        )
                    ),

                    version=(
                        new_version
                    ),

                    source=(
                        source
                    ),

                    reason=(
                        "Derived from "
                        f"trading_mode="
                        f"{validated}"
                    ),
                )

            self.logger.info(
                (
                    "Setting updated: "
                    "%s=%r "
                    "version=%d "
                    "source=%s"
                ),
                key,
                self.settings.get(
                    key
                ),
                new_version,
                source,
            )

    def set_many(
        self,
        changes: Mapping[
            str,
            Any,
        ],
        source: str = "SYSTEM",
        reason: str = "Batch update",
    ) -> None:
        """
        Validate every change first.

        Persist all changes atomically.
        """

        if (
            not isinstance(
                changes,
                Mapping,
            )
            or not changes
        ):

            return

        prepared: Dict[
            str,
            Any,
        ] = {}

        for (
            key,
            value,
        ) in changes.items():

            if (
                key
                in _RUNTIME_ONLY_KEYS
                or key
                in _INTERNAL_ONLY_KEYS
            ):

                raise ValueError(
                    (
                        f"Setting '{key}' "
                        f"cannot be "
                        f"batch-written."
                    )
                )

            prepared[
                key
            ] = (
                self._validate_value(
                    key,
                    value,
                )
            )

        self.load_settings()

        with self._lock:

            old_snapshot = (
                copy.deepcopy(
                    self.settings
                )
            )

            candidate = (
                copy.deepcopy(
                    self.settings
                )
            )

            for (
                key,
                value,
            ) in (
                prepared.items()
            ):

                candidate[
                    key
                ] = value

            if (
                "trading_mode"
                in prepared
            ):

                candidate[
                    "primary_timeframe"
                ] = (
                    MODE_PROFILES[
                        candidate[
                            "trading_mode"
                        ]
                    ][
                        "primary_timeframe"
                    ]
                )

            candidate = (
                self
                ._apply_cross_field_invariants(
                    candidate
                )
            )

            if (
                "primary_timeframe"
                in prepared
            ):

                expected = (
                    MODE_PROFILES[
                        candidate[
                            "trading_mode"
                        ]
                    ][
                        "primary_timeframe"
                    ]
                )

                if (
                    prepared[
                        "primary_timeframe"
                    ]
                    != expected
                ):

                    raise ValueError(
                        (
                            "primary_timeframe "
                            f"must be "
                            f"'{expected}' "
                            f"for mode "
                            f"'{candidate['trading_mode']}'."
                        )
                    )

            if (
                candidate
                == old_snapshot
            ):

                return

            new_version = (
                int(
                    old_snapshot.get(
                        "settings_version",
                        1,
                    )
                )
                + 1
            )

            candidate[
                "settings_version"
            ] = new_version

            self.settings = (
                candidate
            )

            try:

                self._save_settings_locked()

            except Exception:

                self.settings = (
                    old_snapshot
                )

                raise

            for key in prepared:

                self._log_audit_record(
                    key=(
                        key
                    ),

                    old_value=(
                        old_snapshot.get(
                            key
                        )
                    ),

                    new_value=(
                        self.settings.get(
                            key
                        )
                    ),

                    version=(
                        new_version
                    ),

                    source=(
                        source
                    ),

                    reason=(
                        reason
                    ),
                )

    def toggle(
        self,
        key: str,
        source: str = "SYSTEM",
        reason: str = "Toggle request",
    ) -> bool:

        current = (
            self.get(
                key
            )
        )

        if not isinstance(
            current,
            bool,
        ):

            raise ValueError(
                (
                    f"Setting '{key}' "
                    f"is not boolean."
                )
            )

        new_value = (
            not current
        )

        self.set(
            key,
            new_value,
            source=source,
            reason=reason,
        )

        return new_value

    def reset_all(
        self,
        source: str = "SYSTEM",
    ) -> None:

        with self._lock:

            old_snapshot = (
                copy.deepcopy(
                    self.settings
                )
            )

            self.settings = (
                self
                ._apply_cross_field_invariants(
                    copy.deepcopy(
                        DEFAULT_SETTINGS
                    )
                )
            )

            new_version = (
                int(
                    old_snapshot.get(
                        "settings_version",
                        1,
                    )
                )
                + 1
            )

            self.settings[
                "settings_version"
            ] = new_version

            try:

                self._save_settings_locked()

            except Exception:

                self.settings = (
                    old_snapshot
                )

                raise

            self._log_audit_record(
                key="ALL_KEYS",

                old_value=(
                    "PRE_RESET"
                ),

                new_value=(
                    "SAFE_DEFAULTS"
                ),

                version=(
                    new_version
                ),

                source=(
                    source
                ),

                reason=(
                    "Reset settings requested"
                ),
            )

    # =========================================================================
    # AUDIT
    # =========================================================================

    def _log_audit_record(
        self,
        key: str,
        old_value: Any,
        new_value: Any,
        version: int,
        source: str,
        reason: str,
    ) -> None:

        record = {
            "timestamp": (
                time.time()
            ),

            "key": (
                key
            ),

            "old_value": (
                old_value
            ),

            "new_value": (
                new_value
            ),

            "settings_version": (
                int(
                    version
                )
            ),

            "source": (
                str(
                    source
                )
            ),

            "reason": (
                str(
                    reason
                )
            ),
        }

        try:

            directory = os.path.dirname(
                AUDIT_LOG_FILE
            )

            if directory:

                os.makedirs(
                    directory,
                    exist_ok=True,
                )

            records = []

            if os.path.exists(
                AUDIT_LOG_FILE
            ):

                with open(
                    AUDIT_LOG_FILE,
                    "r",
                    encoding="utf-8",
                ) as handle:

                    try:

                        loaded = (
                            json.load(
                                handle
                            )
                        )

                        if isinstance(
                            loaded,
                            list,
                        ):

                            records = (
                                loaded
                            )

                    except Exception:

                        records = []

            records.append(
                record
            )

            records = (
                records[
                    -1000:
                ]
            )

            temp_path = (
                AUDIT_LOG_FILE
                + ".tmp"
            )

            with open(
                temp_path,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    records,
                    handle,
                    indent=2,
                    allow_nan=False,
                )

                handle.flush()

                try:

                    os.fsync(
                        handle.fileno()
                    )

                except OSError:

                    pass

            os.replace(
                temp_path,
                AUDIT_LOG_FILE,
            )

        except Exception as exc:

            self.logger.error(
                (
                    "Failed to write "
                    "settings audit "
                    "log: %s"
                ),
                exc,
            )


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

settings_manager = (
    SettingsManager()
)


# ============================================================================
# LEGACY PRE-VALIDATION HELPERS
# ============================================================================

def clamp_m1_trade_levels(
    order_type: str,
    entry_price: float,
    raw_sl: float,
    raw_tp: float,
    point_size: float = 0.1,
    symbol: str = "XAUUSDm",
) -> tuple:
    """
    Legacy PRE-VALIDATION helper.

    It may only REDUCE an oversized M1 risk distance.

    It must never silently enlarge a stop after risk sizing.

    Final result must still pass ExecutionValidator.
    """

    order_type = (
        str(
            order_type
        )
        .upper()
    )

    if order_type not in {
        "BUY",
        "SELL",
    }:

        raise ValueError(
            (
                "order_type must "
                "be BUY or SELL"
            )
        )

    entry = float(
        entry_price
    )

    sl = float(
        raw_sl
    )

    tp = float(
        raw_tp
    )

    point = float(
        point_size
    )

    if point <= 0.0:

        raise ValueError(
            (
                "point_size must "
                "be positive"
            )
        )

    max_sl_pips = float(
        settings_manager.get(
            "max_sl_pips",
            12.0,
        )
    )

    default_tp_pips = float(
        settings_manager.get(
            "default_tp_pips",
            24.0,
        )
    )

    max_sl_dist = (
        max_sl_pips
        * point
    )

    target_tp_dist = (
        default_tp_pips
        * point
    )

    if order_type == "BUY":

        # Bring an oversized stop CLOSER.
        sl = max(
            sl,
            (
                entry
                - max_sl_dist
            ),
        )

        if (
            tp
            - entry
        ) > (
            35.0
            * point
        ):

            tp = (
                entry
                + target_tp_dist
            )

    else:

        # Bring an oversized stop CLOSER.
        sl = min(
            sl,
            (
                entry
                + max_sl_dist
            ),
        )

        if (
            entry
            - tp
        ) > (
            35.0
            * point
        ):

            tp = (
                entry
                - target_tp_dist
            )

    return validate_and_clamp_stops(
        symbol,
        order_type,
        entry,
        sl,
        tp,
    )


def validate_and_clamp_stops(
    symbol: str,
    order_type: str,
    entry_price: float,
    raw_sl: float,
    raw_tp: float,
) -> tuple:
    """
    Legacy compatibility helper.

    Historical implementation could move an SL farther away in order
    to satisfy broker stops level.

    That is unsafe after sizing.

    New behavior:
        broker minimum violation -> ERROR

    Caller must rebuild, re-size and revalidate the candidate instead.
    """

    from utils.mt5_gateway import (
        mt5_gateway as mt5,
    )

    order_type = (
        str(
            order_type
        )
        .upper()
    )

    entry = float(
        entry_price
    )

    sl = float(
        raw_sl
    )

    tp = float(
        raw_tp
    )

    if order_type == "BUY":

        if not (
            sl
            < entry
            < tp
        ):

            raise ValueError(
                "INVALID_BUY_GEOMETRY"
            )

    elif order_type == "SELL":

        if not (
            tp
            < entry
            < sl
        ):

            raise ValueError(
                "INVALID_SELL_GEOMETRY"
            )

    else:

        raise ValueError(
            "INVALID_ACTION"
        )

    info = (
        mt5.symbol_info(
            symbol
        )
    )

    if info is None:

        # ExecutionValidator will fail closed later if live metadata
        # remains unavailable.
        return (
            sl,
            tp,
        )

    point = float(
        getattr(
            info,
            "point",
            0.0,
        )
        or 0.0
    )

    digits = int(
        getattr(
            info,
            "digits",
            5,
        )
        or 5
    )

    stops_level = int(
        getattr(
            info,
            "trade_stops_level",
            0,
        )
        or 0
    )

    if (
        point > 0.0
        and stops_level > 0
    ):

        min_dist = (
            point
            * stops_level
        )

        if (
            abs(
                entry
                - sl
            )
            + 1e-12
            < min_dist
        ):

            raise ValueError(
                (
                    "SL_INSIDE_BROKER_"
                    "STOPS_LEVEL"
                )
            )

        if (
            abs(
                tp
                - entry
            )
            + 1e-12
            < min_dist
        ):

            raise ValueError(
                (
                    "TP_INSIDE_BROKER_"
                    "STOPS_LEVEL"
                )
            )

    return (
        round(
            sl,
            digits,
        ),

        round(
            tp,
            digits,
        ),
    )