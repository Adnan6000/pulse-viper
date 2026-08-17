# core/safety_engine.py

from __future__ import annotations

import logging
import math
import os
import sqlite3
import threading
import time

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager


JOURNAL_DB = "data/trade_history.db"


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


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


# =============================================================================
# SAFETY ENGINE
# =============================================================================


class SafetyEngine:
    """
    Single authoritative account-level entry safety gate.

    Responsibilities
    ----------------

    SafetyEngine decides:

        - whether account-level drawdown permits a new trade
        - whether consecutive-loss policy permits a new trade

    RiskEngine decides:

        - how much risk to allocate if SafetyEngine allows an entry

    ExecutionValidator decides:

        - whether the exact final broker request is valid

    Important invariants
    --------------------

    1. P&L is always currency-denominated.
    2. Drawdown thresholds are always percentage-denominated.
    3. Currency P&L is converted to percentage BEFORE comparison.
    4. Paper mode does NOT secretly double configured safety limits.
    5. Live mode does NOT silently fall back to possibly stale paper DB data.
    6. Consecutive losses are counted as trades/positions, not arbitrary deals.
    7. Realized P&L belongs to CLOSE time/day.
    8. Missing live safety data fails closed.
    """

    CACHE_SECONDS = 0.50

    def __init__(self):
        self.logger = logging.getLogger(
            "PulseViper.SafetyEngine"
        )

        self._lock = threading.RLock()

        self._stats_cache: Optional[
            Dict[str, Any]
        ] = None

        self._stats_cache_at = 0.0

    # =========================================================================
    # PUBLIC STATS
    # =========================================================================

    def get_stats(
        self,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Return current realized safety statistics.

        Output keys
        -----------

        daily_pnl:
            Net realized P&L closed today UTC.

        weekly_pnl:
            Net realized P&L closed since Monday 00:00 UTC.

        consecutive_losses:
            Consecutive losing trades since the most recent profitable trade,
            scoped to the current UTC day for compatibility with existing
            PulseViper behavior.

        daily_trades:
            Number of logical closed trades today.

        data_ok:
            Whether the safety data source was successfully read.

        source:
            MT5_LIVE or SQLITE_PAPER.
        """

        with self._lock:
            now_monotonic = (
                time.monotonic()
            )

            if (
                not force_refresh
                and self._stats_cache
                is not None
                and (
                    now_monotonic
                    - self._stats_cache_at
                )
                <= self.CACHE_SECONDS
            ):
                return dict(
                    self._stats_cache
                )

        is_paper = bool(
            settings_manager.get(
                "paper_mode",
                True,
            )
        )

        if is_paper:
            stats = (
                self._get_paper_stats()
            )

        else:
            stats = (
                self._get_live_stats()
            )

        with self._lock:
            self._stats_cache = dict(
                stats
            )

            self._stats_cache_at = (
                time.monotonic()
            )

        return dict(
            stats
        )

    # =========================================================================
    # ENTRY GATE
    # =========================================================================

    def check_entry_allowed(
        self,
    ) -> Tuple[bool, str]:
        """
        Hard account-level entry permission.

        Returns:
            (allowed, reason)
        """

        if not bool(
            settings_manager.get(
                "safety_engine_enabled",
                True,
            )
        ):
            return (
                True,
                "SAFETY_ENGINE_DISABLED",
            )

        state = (
            self.get_risk_budget_state()
        )

        if not state.get(
            "data_ok",
            False,
        ):
            reason = str(
                state.get(
                    "reason",
                    "SAFETY_DATA_UNAVAILABLE",
                )
            )

            self.logger.error(
                (
                    "Entry blocked because "
                    "safety data is unavailable: %s"
                ),
                reason,
            )

            return (
                False,
                reason,
            )

        consecutive_losses = (
            _finite_int(
                state.get(
                    "consecutive_losses",
                    0,
                )
            )
        )

        max_consecutive_losses = (
            _finite_int(
                state.get(
                    "max_consecutive_losses",
                    0,
                )
            )
        )

        daily_drawdown_pct = (
            _finite_float(
                state.get(
                    "daily_drawdown_pct",
                    0.0,
                )
            )
        )

        weekly_drawdown_pct = (
            _finite_float(
                state.get(
                    "weekly_drawdown_pct",
                    0.0,
                )
            )
        )

        max_daily_drawdown_pct = (
            _finite_float(
                state.get(
                    "max_daily_drawdown_pct",
                    0.0,
                )
            )
        )

        max_weekly_drawdown_pct = (
            _finite_float(
                state.get(
                    "max_weekly_drawdown_pct",
                    0.0,
                )
            )
        )

        # ---------------------------------------------------------------------
        # Consecutive loss hard stop
        # ---------------------------------------------------------------------

        if (
            max_consecutive_losses > 0
            and consecutive_losses
            >= max_consecutive_losses
        ):
            reason = (
                "MAX_CONSECUTIVE_LOSSES:"
                f"{consecutive_losses}/"
                f"{max_consecutive_losses}"
            )

            self.logger.warning(
                "Safety halt: %s",
                reason,
            )

            return (
                False,
                reason,
            )

        # ---------------------------------------------------------------------
        # Daily drawdown hard stop
        # ---------------------------------------------------------------------

        if (
            max_daily_drawdown_pct
            >= 0.0
            and daily_drawdown_pct
            >= max_daily_drawdown_pct
            and (
                daily_drawdown_pct > 0.0
                or max_daily_drawdown_pct
                == 0.0
            )
        ):
            reason = (
                "MAX_DAILY_DRAWDOWN:"
                f"{daily_drawdown_pct:.4f}%/"
                f"{max_daily_drawdown_pct:.4f}%"
            )

            self.logger.warning(
                "Safety halt: %s",
                reason,
            )

            return (
                False,
                reason,
            )

        # ---------------------------------------------------------------------
        # Weekly drawdown hard stop
        # ---------------------------------------------------------------------

        if (
            max_weekly_drawdown_pct
            >= 0.0
            and weekly_drawdown_pct
            >= max_weekly_drawdown_pct
            and (
                weekly_drawdown_pct > 0.0
                or max_weekly_drawdown_pct
                == 0.0
            )
        ):
            reason = (
                "MAX_WEEKLY_DRAWDOWN:"
                f"{weekly_drawdown_pct:.4f}%/"
                f"{max_weekly_drawdown_pct:.4f}%"
            )

            self.logger.warning(
                "Safety halt: %s",
                reason,
            )

            return (
                False,
                reason,
            )

        return (
            True,
            "ALLOWED",
        )

    # =========================================================================
    # AUTHORITATIVE RISK BUDGET STATE
    # =========================================================================

    def get_risk_budget_state(
        self,
    ) -> Dict[str, Any]:
        """
        Single authoritative safety/risk-budget interface.

        Used directly by DynamicRiskEngine.

        Drawdown utilization:
            0.00 = no configured loss budget consumed
            0.50 = half consumed
            1.00 = hard limit reached
        """

        stats = self.get_stats()

        if not stats.get(
            "data_ok",
            False,
        ):
            return {
                **stats,
                "allowed": False,
                "reason": (
                    stats.get(
                        "error",
                        "SAFETY_DATA_UNAVAILABLE",
                    )
                ),
                "daily_drawdown_pct": 0.0,
                "weekly_drawdown_pct": 0.0,
                "daily_drawdown_utilization": 1.0,
                "weekly_drawdown_utilization": 1.0,
            }

        daily_pnl = _finite_float(
            stats.get(
                "daily_pnl",
                0.0,
            )
        )

        weekly_pnl = _finite_float(
            stats.get(
                "weekly_pnl",
                0.0,
            )
        )

        current_balance = (
            self._get_current_balance(
                daily_pnl=daily_pnl,
                weekly_pnl=weekly_pnl,
            )
        )

        if current_balance <= 0.0:
            return {
                **stats,
                "allowed": False,
                "reason": (
                    "INVALID_REFERENCE_BALANCE"
                ),
                "current_balance": (
                    current_balance
                ),
                "daily_drawdown_pct": 0.0,
                "weekly_drawdown_pct": 0.0,
                "daily_drawdown_utilization": 1.0,
                "weekly_drawdown_utilization": 1.0,
            }

        # ---------------------------------------------------------------------
        # Estimate beginning-of-period balance.
        #
        # If current balance already contains today's -$100 result:
        #
        # current = 9900
        # pnl     = -100
        # start   = 9900 - (-100) = 10000
        # ---------------------------------------------------------------------

        daily_reference_balance = (
            current_balance
            - daily_pnl
        )

        weekly_reference_balance = (
            current_balance
            - weekly_pnl
        )

        if daily_reference_balance <= 0.0:
            daily_reference_balance = (
                current_balance
            )

        if weekly_reference_balance <= 0.0:
            weekly_reference_balance = (
                current_balance
            )

        daily_drawdown_currency = max(
            0.0,
            -daily_pnl,
        )

        weekly_drawdown_currency = max(
            0.0,
            -weekly_pnl,
        )

        daily_drawdown_pct = (
            daily_drawdown_currency
            / daily_reference_balance
            * 100.0
            if daily_reference_balance
            > 0.0
            else 0.0
        )

        weekly_drawdown_pct = (
            weekly_drawdown_currency
            / weekly_reference_balance
            * 100.0
            if weekly_reference_balance
            > 0.0
            else 0.0
        )

        max_losses = max(
            0,
            _finite_int(
                settings_manager.get(
                    "max_consecutive_losses",
                    10,
                ),
                10,
            ),
        )

        max_daily_dd = max(
            0.0,
            _finite_float(
                settings_manager.get(
                    "max_daily_drawdown_pct",
                    10.0,
                ),
                10.0,
            ),
        )

        max_weekly_dd = max(
            0.0,
            _finite_float(
                settings_manager.get(
                    "max_weekly_drawdown_pct",
                    25.0,
                ),
                25.0,
            ),
        )

        daily_utilization = (
            self._utilization(
                daily_drawdown_pct,
                max_daily_dd,
            )
        )

        weekly_utilization = (
            self._utilization(
                weekly_drawdown_pct,
                max_weekly_dd,
            )
        )

        consecutive_losses = (
            _finite_int(
                stats.get(
                    "consecutive_losses",
                    0,
                )
            )
        )

        allowed = True
        reason = "ALLOWED"

        if (
            max_losses > 0
            and consecutive_losses
            >= max_losses
        ):
            allowed = False

            reason = (
                "MAX_CONSECUTIVE_LOSSES:"
                f"{consecutive_losses}/"
                f"{max_losses}"
            )

        elif (
            daily_drawdown_pct
            >= max_daily_dd
            and (
                daily_drawdown_pct > 0.0
                or max_daily_dd == 0.0
            )
        ):
            allowed = False

            reason = (
                "MAX_DAILY_DRAWDOWN:"
                f"{daily_drawdown_pct:.4f}%/"
                f"{max_daily_dd:.4f}%"
            )

        elif (
            weekly_drawdown_pct
            >= max_weekly_dd
            and (
                weekly_drawdown_pct > 0.0
                or max_weekly_dd == 0.0
            )
        ):
            allowed = False

            reason = (
                "MAX_WEEKLY_DRAWDOWN:"
                f"{weekly_drawdown_pct:.4f}%/"
                f"{max_weekly_dd:.4f}%"
            )

        return {
            **stats,

            "allowed": allowed,
            "reason": reason,

            "current_balance": (
                current_balance
            ),

            "daily_reference_balance": (
                daily_reference_balance
            ),

            "weekly_reference_balance": (
                weekly_reference_balance
            ),

            "daily_drawdown_currency": (
                daily_drawdown_currency
            ),

            "weekly_drawdown_currency": (
                weekly_drawdown_currency
            ),

            "daily_drawdown_pct": (
                daily_drawdown_pct
            ),

            "weekly_drawdown_pct": (
                weekly_drawdown_pct
            ),

            "max_consecutive_losses": (
                max_losses
            ),

            "max_daily_drawdown_pct": (
                max_daily_dd
            ),

            "max_weekly_drawdown_pct": (
                max_weekly_dd
            ),

            "daily_drawdown_utilization": (
                daily_utilization
            ),

            "weekly_drawdown_utilization": (
                weekly_utilization
            ),
        }

    # =========================================================================
    # PAPER STATS
    # =========================================================================

    def _get_paper_stats(
        self,
    ) -> Dict[str, Any]:
        """
        Paper mode uses PulseViper's journal.

        The corrected engine writes `date/time` from CLOSE time, so realized
        P&L is assigned to the correct UTC day.
        """

        now = datetime.now(
            timezone.utc
        )

        today = now.date().isoformat()

        monday = (
            now
            - timedelta(
                days=now.weekday()
            )
        ).date().isoformat()

        if not os.path.exists(
            JOURNAL_DB
        ):
            return {
                "daily_pnl": 0.0,
                "weekly_pnl": 0.0,
                "consecutive_losses": 0,
                "daily_trades": 0,
                "data_ok": True,
                "source": "SQLITE_PAPER",
                "error": None,
            }

        connection = None

        try:
            connection = sqlite3.connect(
                JOURNAL_DB
            )

            connection.row_factory = (
                sqlite3.Row
            )

            cursor = (
                connection.cursor()
            )

            # -----------------------------------------------------------------
            # Verify table/schema.
            # -----------------------------------------------------------------

            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name='trades'
                """
            )

            if cursor.fetchone() is None:
                return {
                    "daily_pnl": 0.0,
                    "weekly_pnl": 0.0,
                    "consecutive_losses": 0,
                    "daily_trades": 0,
                    "data_ok": True,
                    "source": "SQLITE_PAPER",
                    "error": None,
                }

            cursor.execute(
                "PRAGMA table_info(trades)"
            )

            columns = {
                str(row[1])
                for row
                in cursor.fetchall()
            }

            required = {
                "id",
                "date",
                "pnl",
            }

            if not required.issubset(
                columns
            ):
                return {
                    "daily_pnl": 0.0,
                    "weekly_pnl": 0.0,
                    "consecutive_losses": 0,
                    "daily_trades": 0,
                    "data_ok": False,
                    "source": "SQLITE_PAPER",
                    "error": (
                        "TRADE_JOURNAL_SCHEMA_INVALID"
                    ),
                }

            # -----------------------------------------------------------------
            # Daily P&L
            # -----------------------------------------------------------------

            cursor.execute(
                """
                SELECT COALESCE(SUM(pnl), 0.0)
                FROM trades
                WHERE date = ?
                  AND pnl IS NOT NULL
                """,
                (
                    today,
                ),
            )

            row = cursor.fetchone()

            daily_pnl = (
                _finite_float(
                    row[0]
                    if row
                    else 0.0
                )
            )

            # -----------------------------------------------------------------
            # Weekly P&L
            # -----------------------------------------------------------------

            cursor.execute(
                """
                SELECT COALESCE(SUM(pnl), 0.0)
                FROM trades
                WHERE date >= ?
                  AND date <= ?
                  AND pnl IS NOT NULL
                """,
                (
                    monday,
                    today,
                ),
            )

            row = cursor.fetchone()

            weekly_pnl = (
                _finite_float(
                    row[0]
                    if row
                    else 0.0
                )
            )

            # -----------------------------------------------------------------
            # Today's logical trades.
            #
            # New architecture:
            #     one validated request = one broker/paper position.
            #
            # For old journal rows, if decision_id/execution_id exists,
            # use it to group former sibling orders into one decision.
            # -----------------------------------------------------------------

            select_fields = [
                "id",
                "pnl",
            ]

            if "decision_id" in columns:
                select_fields.append(
                    "decision_id"
                )

            if "execution_id" in columns:
                select_fields.append(
                    "execution_id"
                )

            query = (
                "SELECT "
                + ", ".join(
                    select_fields
                )
                + """
                  FROM trades
                  WHERE date = ?
                    AND pnl IS NOT NULL
                  ORDER BY id DESC
                  LIMIT 500
                """
            )

            cursor.execute(
                query,
                (
                    today,
                ),
            )

            rows = (
                cursor.fetchall()
            )

            grouped = (
                self._group_journal_rows(
                    rows,
                    columns,
                )
            )

            consecutive_losses = (
                self._count_consecutive_losses(
                    grouped
                )
            )

            return {
                "daily_pnl": round(
                    daily_pnl,
                    2,
                ),
                "weekly_pnl": round(
                    weekly_pnl,
                    2,
                ),
                "consecutive_losses": (
                    consecutive_losses
                ),
                "daily_trades": (
                    len(
                        grouped
                    )
                ),
                "data_ok": True,
                "source": "SQLITE_PAPER",
                "error": None,
            }

        except Exception as exc:
            self.logger.exception(
                (
                    "Failed reading paper "
                    "safety statistics: %s"
                ),
                exc,
            )

            return {
                "daily_pnl": 0.0,
                "weekly_pnl": 0.0,
                "consecutive_losses": 0,
                "daily_trades": 0,
                "data_ok": False,
                "source": "SQLITE_PAPER",
                "error": (
                    "PAPER_SAFETY_DATA_ERROR"
                ),
            }

        finally:
            if connection is not None:
                try:
                    connection.close()

                except Exception:
                    pass

    # =========================================================================
    # LIVE STATS
    # =========================================================================

    def _get_live_stats(
        self,
    ) -> Dict[str, Any]:
        """
        Live safety data comes ONLY from MT5.

        No fallback to paper/local journal if MT5 is unavailable.
        """

        try:
            terminal = (
                mt5.terminal_info()
            )

            account = (
                mt5.account_info()
            )

            if (
                terminal is None
                or account is None
            ):
                return {
                    "daily_pnl": 0.0,
                    "weekly_pnl": 0.0,
                    "consecutive_losses": 0,
                    "daily_trades": 0,
                    "data_ok": False,
                    "source": "MT5_LIVE",
                    "error": (
                        "MT5_SAFETY_DATA_UNAVAILABLE"
                    ),
                }

            from configs.config import Config

            magic = _finite_int(
                Config.MAGIC_NUMBER,
                123456,
            )

            now = datetime.now(
                timezone.utc
            )

            today_start = (
                now.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            )

            week_start = (
                now
                - timedelta(
                    days=now.weekday()
                )
            ).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

            now_ts = int(
                now.timestamp()
            )

            today_ts = int(
                today_start.timestamp()
            )

            week_ts = int(
                week_start.timestamp()
            )

            weekly_deals = (
                mt5.history_deals_get(
                    week_ts,
                    now_ts,
                )
            )

            if weekly_deals is None:
                return {
                    "daily_pnl": 0.0,
                    "weekly_pnl": 0.0,
                    "consecutive_losses": 0,
                    "daily_trades": 0,
                    "data_ok": False,
                    "source": "MT5_LIVE",
                    "error": (
                        "MT5_HISTORY_UNAVAILABLE"
                    ),
                }

            exit_entries = {
                mt5.DEAL_ENTRY_OUT,
                mt5.DEAL_ENTRY_INOUT,
            }

            filtered_week = [
                deal
                for deal
                in weekly_deals
                if (
                    _finite_int(
                        getattr(
                            deal,
                            "magic",
                            -1,
                        ),
                        -1,
                    )
                    == magic
                    and getattr(
                        deal,
                        "entry",
                        None,
                    )
                    in exit_entries
                )
            ]

            weekly_pnl = sum(
                self._deal_net_pnl(
                    deal
                )
                for deal
                in filtered_week
            )

            filtered_today = [
                deal
                for deal
                in filtered_week
                if (
                    _finite_int(
                        getattr(
                            deal,
                            "time",
                            0,
                        )
                    )
                    >= today_ts
                )
            ]

            daily_pnl = sum(
                self._deal_net_pnl(
                    deal
                )
                for deal
                in filtered_today
            )

            grouped_today = (
                self._group_mt5_exit_deals(
                    filtered_today
                )
            )

            consecutive_losses = (
                self._count_consecutive_losses(
                    grouped_today
                )
            )

            return {
                "daily_pnl": round(
                    daily_pnl,
                    2,
                ),
                "weekly_pnl": round(
                    weekly_pnl,
                    2,
                ),
                "consecutive_losses": (
                    consecutive_losses
                ),
                "daily_trades": (
                    len(
                        grouped_today
                    )
                ),
                "data_ok": True,
                "source": "MT5_LIVE",
                "error": None,
            }

        except Exception as exc:
            self.logger.exception(
                (
                    "Failed reading live "
                    "MT5 safety statistics: %s"
                ),
                exc,
            )

            return {
                "daily_pnl": 0.0,
                "weekly_pnl": 0.0,
                "consecutive_losses": 0,
                "daily_trades": 0,
                "data_ok": False,
                "source": "MT5_LIVE",
                "error": (
                    "MT5_SAFETY_DATA_ERROR"
                ),
            }

    # =========================================================================
    # MT5 DEAL GROUPING
    # =========================================================================

    @staticmethod
    def _deal_net_pnl(
        deal: Any,
    ) -> float:
        return (
            _finite_float(
                getattr(
                    deal,
                    "profit",
                    0.0,
                )
            )
            + _finite_float(
                getattr(
                    deal,
                    "commission",
                    0.0,
                )
            )
            + _finite_float(
                getattr(
                    deal,
                    "swap",
                    0.0,
                )
            )
            + _finite_float(
                getattr(
                    deal,
                    "fee",
                    0.0,
                )
            )
        )

    def _group_mt5_exit_deals(
        self,
        deals: List[Any],
    ) -> List[Dict[str, Any]]:
        """
        Aggregate multiple exit deals belonging to the same MT5 position.

        This handles:
            - partial closes
            - split broker fills
            - CLOSE_BY resulting deal fragments

        without the old "same symbol within 60 seconds" guess.
        """

        groups: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for deal in deals:
            position_id = (
                _finite_int(
                    getattr(
                        deal,
                        "position_id",
                        0,
                    )
                )
            )

            if position_id <= 0:
                position_id = (
                    _finite_int(
                        getattr(
                            deal,
                            "position",
                            0,
                        )
                    )
                )

            if position_id <= 0:
                # Last-resort unique deal key.
                position_id = (
                    _finite_int(
                        getattr(
                            deal,
                            "ticket",
                            0,
                        )
                    )
                )

            key = (
                f"POS-{position_id}"
            )

            timestamp = (
                _finite_int(
                    getattr(
                        deal,
                        "time_msc",
                        0,
                    )
                )
            )

            if timestamp <= 0:
                timestamp = (
                    _finite_int(
                        getattr(
                            deal,
                            "time",
                            0,
                        )
                    )
                    * 1000
                )

            if key not in groups:
                groups[
                    key
                ] = {
                    "key": key,
                    "pnl": 0.0,
                    "time": timestamp,
                }

            groups[
                key
            ][
                "pnl"
            ] += self._deal_net_pnl(
                deal
            )

            groups[
                key
            ][
                "time"
            ] = max(
                _finite_int(
                    groups[
                        key
                    ][
                        "time"
                    ]
                ),
                timestamp,
            )

        ordered = list(
            groups.values()
        )

        ordered.sort(
            key=lambda item: (
                _finite_int(
                    item.get(
                        "time",
                        0,
                    )
                )
            ),
            reverse=True,
        )

        return ordered

    # =========================================================================
    # PAPER JOURNAL GROUPING
    # =========================================================================

    @staticmethod
    def _group_journal_rows(
        rows,
        columns,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate old sibling rows where possible.

        Priority:
            execution_id
            decision_id
            row id
        """

        groups: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for row in rows:
            row_id = _finite_int(
                row[
                    "id"
                ]
            )

            execution_id = None
            decision_id = None

            if (
                "execution_id"
                in columns
            ):
                execution_id = (
                    row[
                        "execution_id"
                    ]
                )

            if (
                "decision_id"
                in columns
            ):
                decision_id = (
                    row[
                        "decision_id"
                    ]
                )

            if execution_id:
                key = (
                    f"EXEC-{execution_id}"
                )

            elif decision_id:
                key = (
                    f"DEC-{decision_id}"
                )

            else:
                key = (
                    f"ROW-{row_id}"
                )

            if key not in groups:
                groups[
                    key
                ] = {
                    "key": key,
                    "pnl": 0.0,
                    "time": row_id,
                }

            groups[
                key
            ][
                "pnl"
            ] += _finite_float(
                row[
                    "pnl"
                ]
            )

            groups[
                key
            ][
                "time"
            ] = max(
                _finite_int(
                    groups[
                        key
                    ][
                        "time"
                    ]
                ),
                row_id,
            )

        ordered = list(
            groups.values()
        )

        ordered.sort(
            key=lambda item: (
                _finite_int(
                    item.get(
                        "time",
                        0,
                    )
                )
            ),
            reverse=True,
        )

        return ordered

    # =========================================================================
    # CONSECUTIVE LOSS COUNT
    # =========================================================================

    @staticmethod
    def _count_consecutive_losses(
        trades: List[
            Dict[str, Any]
        ],
    ) -> int:
        """
        Input is newest -> oldest.

        Zero-PnL trades are ignored rather than breaking or extending the
        losing streak.
        """

        losses = 0

        for trade in trades:
            pnl = _finite_float(
                trade.get(
                    "pnl",
                    0.0,
                )
            )

            if pnl < 0.0:
                losses += 1

            elif pnl > 0.0:
                break

        return losses

    # =========================================================================
    # BALANCE
    # =========================================================================

    def _get_current_balance(
        self,
        daily_pnl: float,
        weekly_pnl: float,
    ) -> float:
        del daily_pnl
        del weekly_pnl

        is_paper = bool(
            settings_manager.get(
                "paper_mode",
                True,
            )
        )

        if not is_paper:
            try:
                account = (
                    mt5.account_info()
                )

                if account is None:
                    return 0.0

                return max(
                    0.0,
                    _finite_float(
                        getattr(
                            account,
                            "balance",
                            0.0,
                        )
                    ),
                )

            except Exception:
                return 0.0

        return (
            self._get_paper_balance()
        )

    def _get_paper_balance(
        self,
    ) -> float:
        """
        Reconstruct paper balance from initial balance + realized journal P&L.

        This avoids relying on the old non-schema `virtual_balance` setting.
        """

        try:
            from configs.config import Config

            initial_balance = (
                max(
                    0.0,
                    _finite_float(
                        Config.INITIAL_BALANCE,
                        10000.0,
                    ),
                )
            )

        except Exception:
            initial_balance = 10000.0

        if not os.path.exists(
            JOURNAL_DB
        ):
            return initial_balance

        connection = None

        try:
            connection = sqlite3.connect(
                JOURNAL_DB
            )

            cursor = (
                connection.cursor()
            )

            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name='trades'
                """
            )

            if cursor.fetchone() is None:
                return initial_balance

            cursor.execute(
                """
                SELECT COALESCE(SUM(pnl), 0.0)
                FROM trades
                WHERE pnl IS NOT NULL
                """
            )

            row = (
                cursor.fetchone()
            )

            realized = (
                _finite_float(
                    row[0]
                    if row
                    else 0.0
                )
            )

            return max(
                0.01,
                initial_balance
                + realized,
            )

        except Exception:
            return initial_balance

        finally:
            if connection is not None:
                try:
                    connection.close()

                except Exception:
                    pass

    # =========================================================================
    # UTILIZATION
    # =========================================================================

    @staticmethod
    def _utilization(
        drawdown_pct: float,
        max_drawdown_pct: float,
    ) -> float:
        drawdown_pct = max(
            0.0,
            _finite_float(
                drawdown_pct
            ),
        )

        max_drawdown_pct = max(
            0.0,
            _finite_float(
                max_drawdown_pct
            ),
        )

        if max_drawdown_pct <= 0.0:
            return (
                1.0
                if drawdown_pct > 0.0
                else 0.0
            )

        return _clamp(
            drawdown_pct
            / max_drawdown_pct,
            0.0,
            1.0,
        )

    # =========================================================================
    # CALLBACK
    # =========================================================================

    def record_trade_result(
        self,
        pnl: float,
    ) -> None:
        """
        Notify SafetyEngine that realized account state changed.

        The journal / MT5 remains authoritative; this only invalidates cache.
        """

        with self._lock:
            self._stats_cache = None
            self._stats_cache_at = 0.0

        self.logger.info(
            (
                "Safety state invalidated "
                "after realized trade PnL %.2f"
            ),
            _finite_float(
                pnl
            ),
        )