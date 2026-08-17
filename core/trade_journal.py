# core/trade_journal.py

"""
PulseViper Trade Journal
========================

SQLite-backed source of truth for CLOSED trade outcomes.

Design rules
------------

1. Realized P&L belongs to CLOSE time, not entry time.
2. Entry and close timestamps are stored explicitly in UTC.
3. Original risk geometry is immutable:
       initial_sl
       initial_tp
       initial_risk_distance
4. Entry spread is captured at ENTRY, not when the trade closes.
5. rr_achieved is measured against ORIGINAL risk.
6. Existing databases are migrated in-place.
7. Existing CSV journals are migrated without deleting old rows.
8. SQLite is the authoritative store; CSV is an export/mirror.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import sqlite3
import threading

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


JOURNAL_DB = "data/trade_history.db"
JOURNAL_CSV = "logs/trade_journal.csv"


# =============================================================================
# SCHEMA
# =============================================================================


CSV_FIELDS = [
    # -------------------------------------------------------------------------
    # Legacy close-day fields retained for dashboard/report compatibility.
    # IMPORTANT: these now represent CLOSE date/time.
    # -------------------------------------------------------------------------
    "date",
    "time",

    # Explicit timestamps
    "entry_time_utc",
    "close_time_utc",

    # Identity
    "symbol",
    "action",

    # Price truth
    "entry_price",
    "close_price",

    # Original immutable risk geometry
    "initial_sl",
    "initial_tp",
    "initial_risk_distance",

    # Legacy aliases
    "sl",
    "tp",

    # Trade size/outcome
    "lot_size",
    "pnl",
    "rr_achieved",
    "close_reason",
    "duration_mins",

    # Entry costs/context
    "entry_spread_points",
    "spread_at_entry",

    # Strategy classification
    "setup_type",
    "fvg_class",
    "bias",
    "volatility_regime",

    # Quality classification
    "classification",
    "classification_reason",

    # Brain
    "brain_score",
    "brain_tier1",
    "brain_tier2",
    "brain_tier3",
    "brain_direction",
    "brain_block_reason",

    # Session / signal metadata
    "session",
    "vsa_signals",
    "entry_features",

    # Audit / strategy
    "audit_id",
    "strategy_name",
    "entry_pattern",

    # Decision lineage
    "decision_id",
    "decision_snapshot",
    "cycle_id",
    "execution_id",
]


SQL_COLUMN_DEFINITIONS = {
    "date": "TEXT",
    "time": "TEXT",

    "entry_time_utc": "TEXT",
    "close_time_utc": "TEXT",

    "symbol": "TEXT",
    "action": "TEXT",

    "entry_price": "REAL",
    "close_price": "REAL",

    "initial_sl": "REAL",
    "initial_tp": "REAL",
    "initial_risk_distance": "REAL",

    "sl": "REAL",
    "tp": "REAL",

    "lot_size": "REAL",
    "pnl": "REAL",
    "rr_achieved": "REAL",
    "close_reason": "TEXT",
    "duration_mins": "REAL",

    "entry_spread_points": "REAL",
    "spread_at_entry": "REAL",

    "setup_type": "TEXT",
    "fvg_class": "TEXT",
    "bias": "TEXT",
    "volatility_regime": "TEXT",

    "classification": "TEXT",
    "classification_reason": "TEXT",

    "brain_score": "REAL",
    "brain_tier1": "REAL",
    "brain_tier2": "REAL",
    "brain_tier3": "REAL",
    "brain_direction": "TEXT",
    "brain_block_reason": "TEXT",

    "session": "TEXT",
    "vsa_signals": "TEXT",
    "entry_features": "TEXT",

    "audit_id": "INTEGER",
    "strategy_name": "TEXT",
    "entry_pattern": "TEXT",

    "decision_id": "TEXT",
    "decision_snapshot": "TEXT",
    "cycle_id": "TEXT",
    "execution_id": "TEXT",
}


# =============================================================================
# HELPERS
# =============================================================================


def _finite_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)

        if math.isfinite(result):
            return result

    except (TypeError, ValueError):
        pass

    return default


def _finite_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)

    except (TypeError, ValueError):
        return default


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _ensure_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _parse_datetime_utc(
    value: Any,
) -> Optional[datetime]:
    """
    Parse common journal datetime representations.

    Naive legacy values are interpreted as UTC because old PulseViper
    journal timestamps were intended to represent UTC market time.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return _ensure_utc(
            value
        )

    text = str(
        value
    ).strip()

    if not text:
        return None

    normalized = text.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )

        return _ensure_utc(
            parsed
        )

    except ValueError:
        pass

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            parsed = datetime.strptime(
                text,
                fmt,
            )

            return parsed.replace(
                tzinfo=timezone.utc
            )

        except ValueError:
            continue

    return None


def _json_safe(
    value: Any,
) -> Any:
    """
    Convert nested values to basic JSON-safe representations.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return _ensure_utc(
            value
        ).isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    # NumPy compatibility without importing numpy.
    module = getattr(
        type(value),
        "__module__",
        "",
    )

    if module.startswith(
        "numpy"
    ):
        try:
            return value.item()

        except Exception:
            return str(
                value
            )

    return value


def _serialize_json(
    value: Any,
    default: str = "{}",
) -> str:
    if isinstance(
        value,
        str,
    ):
        # Preserve already serialized valid strings.
        return value

    try:
        return json.dumps(
            _json_safe(
                value
            ),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            default=str,
        )

    except Exception:
        return default


# =============================================================================
# JOURNAL
# =============================================================================


class TradeJournal:
    """
    Persistent structured trade outcome store.

    SQLite is authoritative.
    CSV is maintained for convenient external analysis.
    """

    def __init__(
        self,
    ):
        self.logger = logging.getLogger(
            "PulseViper.Journal"
        )

        self._lock = (
            threading.RLock()
        )

        self._ensure_storage()

    # =========================================================================
    # CONNECTION
    # =========================================================================

    @staticmethod
    def _connect() -> sqlite3.Connection:
        connection = sqlite3.connect(
            JOURNAL_DB,
            timeout=10.0,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        connection.execute(
            "PRAGMA synchronous=NORMAL"
        )

        connection.execute(
            "PRAGMA busy_timeout=10000"
        )

        return connection

    # =========================================================================
    # STORAGE / MIGRATION
    # =========================================================================

    def _ensure_storage(
        self,
    ) -> None:
        os.makedirs(
            "data",
            exist_ok=True,
        )

        os.makedirs(
            "logs",
            exist_ok=True,
        )

        os.makedirs(
            "logs/daily_reports",
            exist_ok=True,
        )

        with self._lock:
            connection = None

            try:
                connection = (
                    self._connect()
                )

                cursor = (
                    connection.cursor()
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT
                    )
                    """
                )

                cursor.execute(
                    "PRAGMA table_info(trades)"
                )

                existing_columns = {
                    str(
                        row["name"]
                    )
                    for row
                    in cursor.fetchall()
                }

                for (
                    column,
                    sql_type,
                ) in (
                    SQL_COLUMN_DEFINITIONS.items()
                ):
                    if (
                        column
                        in existing_columns
                    ):
                        continue

                    cursor.execute(
                        f"""
                        ALTER TABLE trades
                        ADD COLUMN {column} {sql_type}
                        """
                    )

                    self.logger.info(
                        (
                            "Journal schema migration: "
                            "added column %s"
                        ),
                        column,
                    )

                # Useful report/safety indexes.
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_trades_close_date
                    ON trades(date)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_trades_strategy
                    ON trades(strategy_name)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_trades_execution_id
                    ON trades(execution_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_trades_decision_id
                    ON trades(decision_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_trades_close_time_utc
                    ON trades(close_time_utc)
                    """
                )

                connection.commit()

                self._backfill_legacy_rows(
                    connection
                )

            except Exception as exc:
                self.logger.exception(
                    (
                        "Failed to initialize "
                        "journal storage: %s"
                    ),
                    exc,
                )

                raise

            finally:
                if connection is not None:
                    connection.close()

            self._ensure_csv_schema()

    def _backfill_legacy_rows(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Non-destructive legacy migration.

        We cannot know the historical true entry time/spread if the old journal
        recorded them incorrectly, so we never fabricate those values.

        What can be safely backfilled:
            close_time_utc <- legacy date/time
            initial_sl     <- sl
            initial_tp     <- tp
            initial risk   <- abs(entry - initial_sl)
            entry spread   <- legacy spread_at_entry
        """

        cursor = (
            connection.cursor()
        )

        cursor.execute(
            """
            SELECT
                id,
                date,
                time,
                entry_price,
                sl,
                tp,
                spread_at_entry,
                entry_time_utc,
                close_time_utc,
                initial_sl,
                initial_tp,
                initial_risk_distance,
                entry_spread_points
            FROM trades
            """
        )

        rows = (
            cursor.fetchall()
        )

        changed = 0

        for row in rows:
            updates: Dict[
                str,
                Any,
            ] = {}

            # -----------------------------------------------------------------
            # Legacy date/time represent the only known historical timestamp.
            # Treat as close time, not entry time.
            # -----------------------------------------------------------------

            if not row[
                "close_time_utc"
            ]:
                legacy_text = (
                    f"{row['date'] or ''} "
                    f"{row['time'] or ''}"
                ).strip()

                parsed = (
                    _parse_datetime_utc(
                        legacy_text
                    )
                )

                if parsed is not None:
                    updates[
                        "close_time_utc"
                    ] = (
                        parsed.isoformat()
                    )

            if (
                row["initial_sl"]
                is None
                and row["sl"]
                is not None
            ):
                updates[
                    "initial_sl"
                ] = _finite_float(
                    row["sl"]
                )

            if (
                row["initial_tp"]
                is None
                and row["tp"]
                is not None
            ):
                updates[
                    "initial_tp"
                ] = _finite_float(
                    row["tp"]
                )

            if (
                row[
                    "initial_risk_distance"
                ]
                is None
            ):
                entry = _finite_float(
                    row[
                        "entry_price"
                    ]
                )

                initial_sl = (
                    updates.get(
                        "initial_sl"
                    )
                    if (
                        "initial_sl"
                        in updates
                    )
                    else row[
                        "initial_sl"
                    ]
                )

                initial_sl = (
                    _finite_float(
                        initial_sl
                    )
                )

                if (
                    entry > 0.0
                    and initial_sl > 0.0
                ):
                    updates[
                        "initial_risk_distance"
                    ] = abs(
                        entry
                        - initial_sl
                    )

            if (
                row[
                    "entry_spread_points"
                ]
                is None
                and row[
                    "spread_at_entry"
                ]
                is not None
            ):
                # Historical accuracy depends on old producer.
                # Keep value as legacy-compatible data rather than inventing.
                updates[
                    "entry_spread_points"
                ] = (
                    _finite_float(
                        row[
                            "spread_at_entry"
                        ]
                    )
                )

            if not updates:
                continue

            assignments = (
                ", ".join(
                    f"{key} = ?"
                    for key
                    in updates
                )
            )

            params = list(
                updates.values()
            )

            params.append(
                row["id"]
            )

            cursor.execute(
                f"""
                UPDATE trades
                SET {assignments}
                WHERE id = ?
                """,
                tuple(
                    params
                ),
            )

            changed += 1

        if changed:
            connection.commit()

            self.logger.info(
                (
                    "Journal legacy migration "
                    "updated %d rows."
                ),
                changed,
            )

    # =========================================================================
    # CSV MIGRATION
    # =========================================================================

    def _ensure_csv_schema(
        self,
    ) -> None:
        """
        Upgrade existing CSV header to current schema without dropping rows.
        """

        if not os.path.exists(
            JOURNAL_CSV
        ):
            with open(
                JOURNAL_CSV,
                "w",
                newline="",
                encoding="utf-8",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        CSV_FIELDS
                    ),
                )

                writer.writeheader()

            return

        try:
            if os.path.getsize(
                JOURNAL_CSV
            ) == 0:
                with open(
                    JOURNAL_CSV,
                    "w",
                    newline="",
                    encoding="utf-8",
                ) as handle:
                    writer = (
                        csv.DictWriter(
                            handle,
                            fieldnames=(
                                CSV_FIELDS
                            ),
                        )
                    )

                    writer.writeheader()

                return

            with open(
                JOURNAL_CSV,
                "r",
                newline="",
                encoding="utf-8",
            ) as handle:
                reader = (
                    csv.DictReader(
                        handle
                    )
                )

                old_fields = (
                    reader.fieldnames
                    or []
                )

                if old_fields == CSV_FIELDS:
                    return

                old_rows = list(
                    reader
                )

            temp_path = (
                JOURNAL_CSV
                + ".migration.tmp"
            )

            with open(
                temp_path,
                "w",
                newline="",
                encoding="utf-8",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        CSV_FIELDS
                    ),
                    extrasaction="ignore",
                )

                writer.writeheader()

                for old_row in old_rows:
                    normalized = {
                        field: (
                            old_row.get(
                                field,
                                "",
                            )
                        )
                        for field
                        in CSV_FIELDS
                    }

                    writer.writerow(
                        normalized
                    )

            os.replace(
                temp_path,
                JOURNAL_CSV,
            )

            self.logger.info(
                (
                    "Migrated CSV journal "
                    "to current schema."
                )
            )

        except Exception as exc:
            self.logger.warning(
                (
                    "CSV schema migration "
                    "failed: %s"
                ),
                exc,
            )

    # =========================================================================
    # RECORD NORMALIZATION
    # =========================================================================

    def _normalize_record(
        self,
        incoming: Dict[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:
        record = dict(
            incoming
        )

        # ---------------------------------------------------------------------
        # TP compatibility
        # ---------------------------------------------------------------------

        if (
            "tp"
            not in record
            and "tp1"
            in record
        ):
            record[
                "tp"
            ] = record.get(
                "tp1"
            )

        # ---------------------------------------------------------------------
        # Core numeric values
        # ---------------------------------------------------------------------

        entry_price = (
            _finite_float(
                record.get(
                    "entry_price",
                    0.0,
                )
            )
        )

        close_price = (
            _finite_float(
                record.get(
                    "close_price",
                    entry_price,
                ),
                entry_price,
            )
        )

        initial_sl = (
            _finite_float(
                record.get(
                    "initial_sl",
                    record.get(
                        "sl",
                        0.0,
                    ),
                )
            )
        )

        initial_tp = (
            _finite_float(
                record.get(
                    "initial_tp",
                    record.get(
                        "tp",
                        0.0,
                    ),
                )
            )
        )

        initial_risk_distance = (
            _finite_float(
                record.get(
                    "initial_risk_distance",
                    0.0,
                )
            )
        )

        if (
            initial_risk_distance
            <= 0.0
            and entry_price > 0.0
            and initial_sl > 0.0
        ):
            initial_risk_distance = abs(
                entry_price
                - initial_sl
            )

        # ---------------------------------------------------------------------
        # Timestamp truth
        # ---------------------------------------------------------------------

        entry_time = (
            _parse_datetime_utc(
                record.get(
                    "entry_time_utc"
                )
            )
        )

        close_time = (
            _parse_datetime_utc(
                record.get(
                    "close_time_utc"
                )
            )
        )

        # Legacy callers may provide only date/time.
        #
        # Those values are now interpreted as CLOSE timestamp because realized
        # outcome accounting must belong to the close day.
        if close_time is None:
            legacy_date = str(
                record.get(
                    "date",
                    "",
                )
                or ""
            ).strip()

            legacy_time = str(
                record.get(
                    "time",
                    "",
                )
                or ""
            ).strip()

            if legacy_date:
                legacy_text = (
                    f"{legacy_date} "
                    f"{legacy_time}"
                ).strip()

                close_time = (
                    _parse_datetime_utc(
                        legacy_text
                    )
                )

        if close_time is None:
            close_time = (
                _utc_now()
            )

        # If no entry time exists, do NOT pretend close time is entry time.
        # Leave it NULL/blank.
        entry_time_text = (
            entry_time.isoformat()
            if entry_time
            is not None
            else None
        )

        close_time_text = (
            close_time.isoformat()
        )

        # Legacy date/time are always CLOSE day/time.
        record[
            "date"
        ] = close_time.strftime(
            "%Y-%m-%d"
        )

        record[
            "time"
        ] = close_time.strftime(
            "%H:%M:%S"
        )

        record[
            "entry_time_utc"
        ] = entry_time_text

        record[
            "close_time_utc"
        ] = close_time_text

        # ---------------------------------------------------------------------
        # Duration
        # ---------------------------------------------------------------------

        if (
            entry_time is not None
            and close_time
            >= entry_time
        ):
            duration = (
                (
                    close_time
                    - entry_time
                ).total_seconds()
                / 60.0
            )

        else:
            duration = max(
                0.0,
                _finite_float(
                    record.get(
                        "duration_mins",
                        0.0,
                    )
                ),
            )

        # ---------------------------------------------------------------------
        # Entry spread
        # ---------------------------------------------------------------------

        entry_spread = (
            _finite_float(
                record.get(
                    "entry_spread_points",
                    record.get(
                        "spread_at_entry",
                        0.0,
                    ),
                )
            )
        )

        # ---------------------------------------------------------------------
        # Realized R
        # ---------------------------------------------------------------------

        supplied_rr = record.get(
            "rr_achieved"
        )

        rr_achieved = (
            _finite_float(
                supplied_rr,
                float("nan"),
            )
        )

        if not math.isfinite(
            rr_achieved
        ):
            rr_achieved = (
                self._calculate_realized_r(
                    action=str(
                        record.get(
                            "action",
                            "",
                        )
                    ),
                    entry_price=(
                        entry_price
                    ),
                    close_price=(
                        close_price
                    ),
                    initial_risk_distance=(
                        initial_risk_distance
                    ),
                )
            )

        # ---------------------------------------------------------------------
        # Canonical values
        # ---------------------------------------------------------------------

        record[
            "entry_price"
        ] = entry_price

        record[
            "close_price"
        ] = close_price

        record[
            "initial_sl"
        ] = initial_sl

        record[
            "initial_tp"
        ] = initial_tp

        record[
            "initial_risk_distance"
        ] = (
            initial_risk_distance
        )

        # Legacy aliases intentionally represent ORIGINAL levels.
        record[
            "sl"
        ] = initial_sl

        record[
            "tp"
        ] = initial_tp

        record[
            "lot_size"
        ] = max(
            0.0,
            _finite_float(
                record.get(
                    "lot_size",
                    0.0,
                )
            ),
        )

        record[
            "pnl"
        ] = _finite_float(
            record.get(
                "pnl",
                0.0,
            )
        )

        record[
            "rr_achieved"
        ] = rr_achieved

        record[
            "duration_mins"
        ] = max(
            0.0,
            duration,
        )

        record[
            "entry_spread_points"
        ] = max(
            0.0,
            entry_spread,
        )

        # Old API alias.
        record[
            "spread_at_entry"
        ] = max(
            0.0,
            entry_spread,
        )

        record[
            "symbol"
        ] = str(
            record.get(
                "symbol",
                "",
            )
        ).strip()

        record[
            "action"
        ] = str(
            record.get(
                "action",
                "",
            )
        ).upper().strip()

        record[
            "close_reason"
        ] = str(
            record.get(
                "close_reason",
                "UNKNOWN",
            )
        )

        record[
            "setup_type"
        ] = str(
            record.get(
                "setup_type",
                "UNKNOWN",
            )
        )

        record[
            "fvg_class"
        ] = str(
            record.get(
                "fvg_class",
                "NONE",
            )
        )

        record[
            "volatility_regime"
        ] = str(
            record.get(
                "volatility_regime",
                "UNKNOWN",
            )
        )

        record[
            "strategy_name"
        ] = str(
            record.get(
                "strategy_name",
                "UNKNOWN",
            )
        )

        record[
            "entry_pattern"
        ] = str(
            record.get(
                "entry_pattern",
                "UNKNOWN",
            )
        )

        # ---------------------------------------------------------------------
        # Structured fields
        # ---------------------------------------------------------------------

        vsa = record.get(
            "vsa_signals",
            [],
        )

        if isinstance(
            vsa,
            str,
        ):
            record[
                "vsa_signals"
            ] = vsa

        else:
            record[
                "vsa_signals"
            ] = _serialize_json(
                vsa,
                default="[]",
            )

        record[
            "entry_features"
        ] = _serialize_json(
            record.get(
                "entry_features",
                {},
            )
        )

        decision_snapshot = (
            record.get(
                "decision_snapshot"
            )
        )

        if (
            decision_snapshot
            is not None
            and not isinstance(
                decision_snapshot,
                str,
            )
        ):
            record[
                "decision_snapshot"
            ] = _serialize_json(
                decision_snapshot,
                default="{}",
            )

        # ---------------------------------------------------------------------
        # Classification after all values are normalized.
        # ---------------------------------------------------------------------

        (
            classification,
            classification_reason,
        ) = self._classify_trade(
            record
        )

        record[
            "classification"
        ] = classification

        record[
            "classification_reason"
        ] = classification_reason

        return record

    # =========================================================================
    # REALIZED R
    # =========================================================================

    @staticmethod
    def _calculate_realized_r(
        action: str,
        entry_price: float,
        close_price: float,
        initial_risk_distance: float,
    ) -> float:
        if (
            initial_risk_distance
            <= 0.0
        ):
            return 0.0

        action = action.upper()

        if action == "BUY":
            return (
                close_price
                - entry_price
            ) / initial_risk_distance

        if action == "SELL":
            return (
                entry_price
                - close_price
            ) / initial_risk_distance

        return 0.0

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================

    def _classify_trade(
        self,
        record: Dict[
            str,
            Any,
        ],
    ) -> Tuple[str, str]:
        """
        Classify trade outcome without symbol-specific arbitrary thresholds.

        Classification is descriptive; it must not alter trading decisions.
        """

        pnl = _finite_float(
            record.get(
                "pnl",
                0.0,
            )
        )

        rr = _finite_float(
            record.get(
                "rr_achieved",
                0.0,
            )
        )

        close_reason = str(
            record.get(
                "close_reason",
                "",
            )
        ).upper()

        reasons: List[
            str
        ] = []

        if pnl > 0.0:
            classification = "GOOD"

            if rr >= 2.0:
                reasons.append(
                    f"Strong realized return ({rr:.2f}R)"
                )

            elif rr >= 1.0:
                reasons.append(
                    f"Positive realized return ({rr:.2f}R)"
                )

            elif rr > 0.0:
                reasons.append(
                    f"Partial positive return ({rr:.2f}R)"
                )

            else:
                reasons.append(
                    "Positive net PnL"
                )

            if (
                close_reason == "SL"
                and pnl > 0.0
            ):
                reasons.append(
                    "Protective/trailing stop closed in profit"
                )

            return (
                classification,
                "; ".join(
                    reasons
                ),
            )

        if pnl < 0.0:
            classification = "BAD"

            if rr <= -1.0:
                reasons.append(
                    f"Full or larger risk loss ({rr:.2f}R)"
                )

            elif rr < 0.0:
                reasons.append(
                    f"Partial risk loss ({rr:.2f}R)"
                )

            else:
                reasons.append(
                    "Negative net PnL"
                )

            if close_reason == "SL":
                reasons.append(
                    "Stopped out"
                )

            return (
                classification,
                "; ".join(
                    reasons
                ),
            )

        return (
            "NEUTRAL",
            "Breakeven / zero net PnL",
        )

    # =========================================================================
    # WRITE
    # =========================================================================

    def append_trade(
        self,
        record: Dict[
            str,
            Any,
        ],
    ) -> bool:
        """
        Persist one CLOSED logical trade.

        Returns True only if SQLite write succeeded.

        CSV failure does not invalidate authoritative SQLite persistence.
        """

        normalized = (
            self._normalize_record(
                record
            )
        )

        if not normalized.get(
            "symbol"
        ):
            self.logger.error(
                (
                    "Journal rejected record "
                    "without symbol."
                )
            )

            return False

        if normalized.get(
            "action"
        ) not in (
            "BUY",
            "SELL",
        ):
            self.logger.error(
                (
                    "Journal rejected record "
                    "with invalid action: %s"
                ),
                normalized.get(
                    "action"
                ),
            )

            return False

        db_success = False

        with self._lock:
            connection = None

            try:
                connection = (
                    self._connect()
                )

                cursor = (
                    connection.cursor()
                )

                columns = list(
                    CSV_FIELDS
                )

                placeholders = ",".join(
                    "?"
                    for _ in columns
                )

                column_sql = ",".join(
                    columns
                )

                values = tuple(
                    normalized.get(
                        field,
                        None,
                    )
                    for field
                    in columns
                )

                cursor.execute(
                    f"""
                    INSERT INTO trades (
                        {column_sql}
                    )
                    VALUES (
                        {placeholders}
                    )
                    """,
                    values,
                )

                connection.commit()

                db_success = True

            except Exception as exc:
                if connection is not None:
                    try:
                        connection.rollback()

                    except Exception:
                        pass

                self.logger.exception(
                    (
                        "Failed to write trade "
                        "to SQLite: %s"
                    ),
                    exc,
                )

                return False

            finally:
                if connection is not None:
                    connection.close()

            # -----------------------------------------------------------------
            # CSV mirror
            # -----------------------------------------------------------------

            if db_success:
                try:
                    self._append_csv(
                        normalized
                    )

                except Exception as exc:
                    self.logger.warning(
                        (
                            "SQLite journal succeeded "
                            "but CSV mirror failed: %s"
                        ),
                        exc,
                    )

        self.logger.info(
            (
                "Journal saved | "
                "%s %s | "
                "PnL=%.2f | "
                "R=%.3f | "
                "close=%s | "
                "class=%s"
            ),
            normalized.get(
                "action"
            ),
            normalized.get(
                "symbol"
            ),
            _finite_float(
                normalized.get(
                    "pnl"
                )
            ),
            _finite_float(
                normalized.get(
                    "rr_achieved"
                )
            ),
            normalized.get(
                "close_time_utc"
            ),
            normalized.get(
                "classification"
            ),
        )

        return True

    def _append_csv(
        self,
        record: Dict[
            str,
            Any,
        ],
    ) -> None:
        self._ensure_csv_schema()

        write_header = (
            not os.path.exists(
                JOURNAL_CSV
            )
            or os.path.getsize(
                JOURNAL_CSV
            )
            == 0
        )

        row = {
            field: (
                record.get(
                    field,
                    "",
                )
            )
            for field
            in CSV_FIELDS
        }

        with open(
            JOURNAL_CSV,
            "a",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    CSV_FIELDS
                ),
                extrasaction="ignore",
            )

            if write_header:
                writer.writeheader()

            writer.writerow(
                row
            )

    # =========================================================================
    # READ
    # =========================================================================

    def get_all_trades(
        self,
    ) -> List[
        Dict[str, Any]
    ]:
        try:
            with self._lock:
                connection = (
                    self._connect()
                )

                try:
                    cursor = (
                        connection.cursor()
                    )

                    cursor.execute(
                        """
                        SELECT *
                        FROM trades
                        ORDER BY id ASC
                        """
                    )

                    rows = (
                        cursor.fetchall()
                    )

                finally:
                    connection.close()

            return [
                dict(row)
                for row
                in rows
            ]

        except Exception as exc:
            self.logger.error(
                (
                    "Failed to read SQLite "
                    "journal: %s"
                ),
                exc,
            )

            return []

    def get_recent_trades(
        self,
        limit: int = 100,
    ) -> List[
        Dict[str, Any]
    ]:
        limit = max(
            1,
            min(
                5000,
                _finite_int(
                    limit,
                    100,
                ),
            ),
        )

        try:
            with self._lock:
                connection = (
                    self._connect()
                )

                try:
                    cursor = (
                        connection.cursor()
                    )

                    cursor.execute(
                        """
                        SELECT *
                        FROM trades
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (
                            limit,
                        ),
                    )

                    rows = (
                        cursor.fetchall()
                    )

                finally:
                    connection.close()

            # Existing API consumers typically want chronological display.
            return [
                dict(row)
                for row
                in reversed(
                    rows
                )
            ]

        except Exception as exc:
            self.logger.error(
                (
                    "Failed reading recent "
                    "journal rows: %s"
                ),
                exc,
            )

            return []

    def get_trades_for_date(
        self,
        target_date: date,
    ) -> List[
        Dict[str, Any]
    ]:
        """
        Query trades CLOSED on a UTC date.
        """

        date_string = (
            target_date.strftime(
                "%Y-%m-%d"
            )
        )

        try:
            with self._lock:
                connection = (
                    self._connect()
                )

                try:
                    cursor = (
                        connection.cursor()
                    )

                    cursor.execute(
                        """
                        SELECT *
                        FROM trades
                        WHERE date = ?
                        ORDER BY id ASC
                        """,
                        (
                            date_string,
                        ),
                    )

                    rows = (
                        cursor.fetchall()
                    )

                finally:
                    connection.close()

            return [
                dict(row)
                for row
                in rows
            ]

        except Exception as exc:
            self.logger.error(
                (
                    "Failed to query journal "
                    "by close date: %s"
                ),
                exc,
            )

            return []

    # =========================================================================
    # DAILY SUMMARY
    # =========================================================================

    def get_daily_summary(
        self,
        target_date: Optional[
            date
        ] = None,
    ) -> Dict[str, Any]:
        """
        Compute realized CLOSED-trade statistics for one UTC day.
        """

        if target_date is None:
            target_date = (
                _utc_now().date()
            )

        trades = (
            self.get_trades_for_date(
                target_date
            )
        )

        if not trades:
            return {
                "date": (
                    str(
                        target_date
                    )
                ),

                # Both names kept for compatibility.
                "trades": 0,
                "total_trades": 0,

                "wins": 0,
                "losses": 0,
                "breakeven": 0,
                "win_rate": 0.0,

                "total_pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,

                "avg_rr": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,

                "sl_hits": 0,
                "tp_hits": 0,

                "good_trades": 0,
                "bad_trades": 0,
                "neutral_trades": 0,

                "setup_breakdown": {},

                "message": (
                    "No trades closed "
                    "on this UTC day"
                ),
            }

        wins = []

        losses = []

        breakeven = []

        good = []

        bad = []

        neutral = []

        rr_values = []

        win_r_values = []

        loss_r_values = []

        sl_hits = 0

        tp_hits = 0

        setup_breakdown: Dict[
            str,
            Dict[str, Any],
        ] = {}

        total_pnl = 0.0

        for trade in trades:
            pnl = _finite_float(
                trade.get(
                    "pnl",
                    0.0,
                )
            )

            rr = _finite_float(
                trade.get(
                    "rr_achieved",
                    0.0,
                )
            )

            total_pnl += pnl

            rr_values.append(
                rr
            )

            if pnl > 0.0:
                wins.append(
                    trade
                )

                win_r_values.append(
                    rr
                )

            elif pnl < 0.0:
                losses.append(
                    trade
                )

                loss_r_values.append(
                    rr
                )

            else:
                breakeven.append(
                    trade
                )

            classification = str(
                trade.get(
                    "classification",
                    "",
                )
            ).upper()

            if classification == "GOOD":
                good.append(
                    trade
                )

            elif classification == "BAD":
                bad.append(
                    trade
                )

            else:
                neutral.append(
                    trade
                )

            reason = str(
                trade.get(
                    "close_reason",
                    "",
                )
            ).upper()

            if "SL" in reason:
                sl_hits += 1

            if "TP" in reason:
                tp_hits += 1

            setup = str(
                trade.get(
                    "setup_type",
                    "UNKNOWN",
                )
                or "UNKNOWN"
            )

            if (
                setup
                not in setup_breakdown
            ):
                setup_breakdown[
                    setup
                ] = {
                    "count": 0,
                    "wins": 0,
                    "losses": 0,
                    "breakeven": 0,
                    "pnl": 0.0,
                    "avg_r": 0.0,
                    "_r_values": [],
                }

            item = (
                setup_breakdown[
                    setup
                ]
            )

            item[
                "count"
            ] += 1

            item[
                "pnl"
            ] += pnl

            item[
                "_r_values"
            ].append(
                rr
            )

            if pnl > 0.0:
                item[
                    "wins"
                ] += 1

            elif pnl < 0.0:
                item[
                    "losses"
                ] += 1

            else:
                item[
                    "breakeven"
                ] += 1

        gross_profit = sum(
            _finite_float(
                trade.get(
                    "pnl"
                )
            )
            for trade
            in wins
        )

        gross_loss = abs(
            sum(
                _finite_float(
                    trade.get(
                        "pnl"
                    )
                )
                for trade
                in losses
            )
        )

        if gross_loss > 0.0:
            profit_factor = (
                gross_profit
                / gross_loss
            )

        elif gross_profit > 0.0:
            # Avoid pretending PF is a finite huge number.
            profit_factor = None

        else:
            profit_factor = 0.0

        total = len(
            trades
        )

        resolved = (
            len(wins)
            + len(losses)
        )

        win_rate = (
            len(wins)
            / resolved
            * 100.0
            if resolved > 0
            else 0.0
        )

        avg_rr = (
            sum(
                rr_values
            )
            / len(
                rr_values
            )
            if rr_values
            else 0.0
        )

        avg_win_r = (
            sum(
                win_r_values
            )
            / len(
                win_r_values
            )
            if win_r_values
            else 0.0
        )

        avg_loss_r = (
            sum(
                loss_r_values
            )
            / len(
                loss_r_values
            )
            if loss_r_values
            else 0.0
        )

        # Remove internal accumulator.
        for item in (
            setup_breakdown.values()
        ):
            r_values = (
                item.pop(
                    "_r_values",
                    [],
                )
            )

            item[
                "pnl"
            ] = round(
                _finite_float(
                    item[
                        "pnl"
                    ]
                ),
                2,
            )

            item[
                "avg_r"
            ] = round(
                (
                    sum(
                        r_values
                    )
                    / len(
                        r_values
                    )
                    if r_values
                    else 0.0
                ),
                3,
            )

        return {
            "date": (
                str(
                    target_date
                )
            ),

            # Compatibility aliases.
            "trades": total,
            "total_trades": (
                total
            ),

            "wins": len(
                wins
            ),

            "losses": len(
                losses
            ),

            "breakeven": len(
                breakeven
            ),

            "win_rate": round(
                win_rate,
                2,
            ),

            "total_pnl": round(
                total_pnl,
                2,
            ),

            "gross_profit": round(
                gross_profit,
                2,
            ),

            "gross_loss": round(
                gross_loss,
                2,
            ),

            "profit_factor": (
                round(
                    profit_factor,
                    3,
                )
                if profit_factor
                is not None
                else None
            ),

            "avg_rr": round(
                avg_rr,
                3,
            ),

            "avg_win_r": round(
                avg_win_r,
                3,
            ),

            "avg_loss_r": round(
                avg_loss_r,
                3,
            ),

            "sl_hits": (
                sl_hits
            ),

            "tp_hits": (
                tp_hits
            ),

            "good_trades": len(
                good
            ),

            "bad_trades": len(
                bad
            ),

            "neutral_trades": len(
                neutral
            ),

            "setup_breakdown": (
                setup_breakdown
            ),
        }

    # =========================================================================
    # RECENT SUMMARY
    # =========================================================================

    def get_recent_summary(
        self,
        n_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Summarize recent UTC close-days.
        """

        n_days = max(
            1,
            min(
                3650,
                _finite_int(
                    n_days,
                    7,
                ),
            ),
        )

        today = (
            _utc_now().date()
        )

        summaries = []

        for offset in range(
            n_days
        ):
            target = (
                today
                - timedelta(
                    days=offset
                )
            )

            summary = (
                self.get_daily_summary(
                    target
                )
            )

            if (
                summary.get(
                    "total_trades",
                    0,
                )
                > 0
            ):
                summaries.append(
                    summary
                )

        total_trades = sum(
            _finite_int(
                item.get(
                    "total_trades",
                    0,
                )
            )
            for item
            in summaries
        )

        total_pnl = sum(
            _finite_float(
                item.get(
                    "total_pnl",
                    0.0,
                )
            )
            for item
            in summaries
        )

        total_wins = sum(
            _finite_int(
                item.get(
                    "wins",
                    0,
                )
            )
            for item
            in summaries
        )

        total_losses = sum(
            _finite_int(
                item.get(
                    "losses",
                    0,
                )
            )
            for item
            in summaries
        )

        resolved = (
            total_wins
            + total_losses
        )

        return {
            "period_days": (
                n_days
            ),

            "active_days": len(
                summaries
            ),

            "total_trades": (
                total_trades
            ),

            "total_pnl": round(
                total_pnl,
                2,
            ),

            "wins": (
                total_wins
            ),

            "losses": (
                total_losses
            ),

            "win_rate": round(
                (
                    total_wins
                    / resolved
                    * 100.0
                    if resolved > 0
                    else 0.0
                ),
                2,
            ),

            "summaries": (
                summaries
            ),
        }

    # =========================================================================
    # STRATEGY HISTORY
    # =========================================================================

    def get_strategy_trades(
        self,
        strategy_name: str,
        limit: int = 500,
    ) -> List[
        Dict[str, Any]
    ]:
        """
        Convenience query used by later causal evaluation/backtester work.
        """

        strategy_name = str(
            strategy_name
            or ""
        ).upper().strip()

        if not strategy_name:
            return []

        limit = max(
            1,
            min(
                5000,
                _finite_int(
                    limit,
                    500,
                ),
            ),
        )

        try:
            with self._lock:
                connection = (
                    self._connect()
                )

                try:
                    cursor = (
                        connection.cursor()
                    )

                    cursor.execute(
                        """
                        SELECT *
                        FROM trades
                        WHERE UPPER(strategy_name) = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (
                            strategy_name,
                            limit,
                        ),
                    )

                    rows = (
                        cursor.fetchall()
                    )

                finally:
                    connection.close()

            return [
                dict(row)
                for row
                in rows
            ]

        except Exception as exc:
            self.logger.error(
                (
                    "Strategy journal query "
                    "failed: %s"
                ),
                exc,
            )

            return []


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================


trade_journal = TradeJournal()