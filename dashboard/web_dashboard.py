from __future__ import annotations

import json
import logging
import math
import os
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping, Optional

import numpy as np

from core.news_schedule import news_schedule
from dashboard.html_template import HTML_TEMPLATE
from utils.mt5_gateway import mt5_gateway as mt5
from utils.settings_manager import settings_manager
from utils.snapshot_helper import deep_thaw

LOG = logging.getLogger("PulseViper.WebDashboard")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 64 * 1024
SECRET_WORDS = ("token", "secret", "password", "api_key", "apikey")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, (float, np.floating)):
        value = float(value)
        return value if math.isfinite(value) else None

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, Mapping):
        return {
            str(k): json_safe(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            json_safe(v)
            for v in value
        ]

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return str(value)


def redact(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, val in value.items():
        name = str(key)

        if any(
            word in name.lower()
            for word in SECRET_WORDS
        ):
            continue

        out[name] = (
            redact(val)
            if isinstance(val, Mapping)
            else json_safe(val)
        )

    return out


def validate_settings(
    values: Mapping[str, Any],
) -> None:
    if not isinstance(
        values,
        Mapping,
    ):
        raise ValueError(
            "Settings payload must be an object"
        )

    for key, value in values.items():
        if str(key).lower() == "control_token":
            raise ValueError(
                "control_token is runtime-only"
            )

        settings_manager._validate_value(
            str(key),
            value,
        )


def resolve_broker_symbol(
    symbol: str,
    engine=None,
) -> str:
    symbol = str(
        symbol or ""
    ).strip()

    if not symbol:
        return ""

    info = mt5.symbol_info(
        symbol
    )

    if info is not None:
        return str(
            info.name
        )

    symbols = (
        mt5.symbols_get()
        or []
    )

    names = [
        str(
            getattr(
                item,
                "name",
                "",
            )
        )
        for item
        in symbols
    ]

    wanted = symbol.upper()

    for name in names:
        if name.upper() == wanted:
            return name

    if (
        engine is not None
        and hasattr(
            engine,
            "find_equivalent_symbol",
        )
    ):
        try:
            found = (
                engine.find_equivalent_symbol(
                    symbol,
                    names,
                )
            )

            if found:
                return str(
                    found
                )

        except Exception:
            pass

    matches = [
        name
        for name
        in names
        if name.upper().startswith(
            wanted
        )
    ]

    return (
        matches[0]
        if len(matches) == 1
        else symbol
    )


class DashboardRequestHandler(
    BaseHTTPRequestHandler
):
    server_version = (
        "PulseViperDashboard/2"
    )

    def __init__(
        self,
        engine,
        *args,
        **kwargs,
    ):
        self.engine = engine

        super().__init__(
            *args,
            **kwargs,
        )

    def log_message(
        self,
        fmt: str,
        *args,
    ) -> None:
        LOG.debug(
            "dashboard: "
            + fmt,
            *args,
        )

    # ================================================================
    # SECURITY
    # ================================================================

    def _local_url(
        self,
        value: Optional[str],
    ) -> bool:
        if not value:
            return False

        try:
            return (
                urllib.parse
                .urlparse(
                    value
                )
                .hostname
                in LOCAL_HOSTS
            )

        except Exception:
            return False

    def _request_allowed(
        self,
    ) -> bool:
        host = str(
            self.headers.get(
                "Host",
                "",
            )
        ).strip()

        host_only = (
            host.rsplit(
                ":",
                1,
            )[0]
            .strip("[]")
            .lower()
            if host
            else ""
        )

        if host_only not in LOCAL_HOSTS:
            self.send_error(
                400,
                "Invalid Host header",
            )

            return False

        if self.command not in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            return True

        if (
            self._local_url(
                self.headers.get(
                    "Origin"
                )
            )
            or self._local_url(
                self.headers.get(
                    "Referer"
                )
            )
        ):
            return True

        supplied = self.headers.get(
            "X-PulseViper-Control-Token",
            "",
        )

        expected = str(
            settings_manager.get(
                "control_token",
                "",
            )
            or ""
        )

        if (
            supplied
            and expected
            and secrets.compare_digest(
                supplied,
                expected,
            )
        ):
            return True

        self.send_error(
            403,
            (
                "Mutation requires "
                "local origin or "
                "valid control token"
            ),
        )

        return False

    def _headers(
        self,
        content_type=(
            "application/json; "
            "charset=utf-8"
        ),
        status=200,
        nonce=None,
    ) -> None:
        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            content_type,
        )

        self.send_header(
            "Cache-Control",
            (
                "no-store, no-cache, "
                "must-revalidate, "
                "max-age=0"
            ),
        )

        self.send_header(
            "X-Content-Type-Options",
            "nosniff",
        )

        self.send_header(
            "Referrer-Policy",
            "no-referrer",
        )

        self.send_header(
            "X-Frame-Options",
            "DENY",
        )

        self.send_header(
            "Cross-Origin-Resource-Policy",
            "same-origin",
        )

        self.send_header(
            "Permissions-Policy",
            (
                "camera=(), "
                "microphone=(), "
                "geolocation=()"
            ),
        )

        origin = self.headers.get(
            "Origin"
        )

        if self._local_url(
            origin
        ):
            self.send_header(
                "Access-Control-Allow-Origin",
                str(
                    origin
                ),
            )

            self.send_header(
                "Vary",
                "Origin",
            )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            (
                "Content-Type, "
                "X-PulseViper-Control-Token"
            ),
        )

        script_src = (
            f"'self' 'nonce-{nonce}'"
            if nonce
            else "'self'"
        )

        self.send_header(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                f"script-src {script_src}; "
                "object-src 'none'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "style-src 'self' "
                "'unsafe-inline' "
                "https://fonts.googleapis.com; "
                "font-src 'self' "
                "https://fonts.gstatic.com "
                "data:; "
                "img-src 'self' "
                "data: blob:; "
                "connect-src 'self';"
            ),
        )

        self.end_headers()

    def _json(
        self,
        payload: Any,
        status=200,
    ) -> None:
        self._headers(
            status=status
        )

        self.wfile.write(
            json.dumps(
                json_safe(
                    payload
                ),
                ensure_ascii=False,
                allow_nan=False,
            ).encode(
                "utf-8"
            )
        )

    def _body(
        self,
    ) -> Dict[str, Any]:
        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

        except ValueError as exc:
            raise ValueError(
                "Invalid Content-Length"
            ) from exc

        if (
            length < 0
            or length > MAX_BODY
        ):
            raise ValueError(
                "Request body too large"
            )

        if length == 0:
            return {}

        value = json.loads(
            self.rfile.read(
                length
            ).decode(
                "utf-8"
            )
        )

        if not isinstance(
            value,
            dict,
        ):
            raise ValueError(
                (
                    "JSON body must "
                    "be an object"
                )
            )

        return value

    # ================================================================
    # SNAPSHOT
    # ================================================================

    def _snapshot(
        self,
    ) -> Dict[str, Any]:
        if (
            self.engine is None
            or not hasattr(
                self.engine,
                "get_dashboard_snapshot",
            )
        ):
            return {}

        snap = (
            self.engine
            .get_dashboard_snapshot()
        )

        if not snap:
            return {}

        value = deep_thaw(
            snap
        )

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else {}
        )

    @staticmethod
    def _number(
        value: Any,
    ) -> Optional[float]:
        try:
            value = float(
                value
            )

            return (
                value
                if math.isfinite(
                    value
                )
                else None
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    def _settings(
        self,
    ) -> Dict[str, Any]:
        try:
            values = (
                settings_manager
                .get_all()
            )

        except Exception:
            values = {}

        return redact(
            (
                values
                if isinstance(
                    values,
                    Mapping,
                )
                else {}
            )
        )

    def _quote(
        self,
        snap: Mapping[
            str,
            Any,
        ],
    ) -> Dict[str, Any]:
        market = snap.get(
            "market",
            {},
        )

        market = (
            market
            if isinstance(
                market,
                Mapping,
            )
            else {}
        )

        quote = market.get(
            "quote",
            {},
        )

        quote = (
            quote
            if isinstance(
                quote,
                Mapping,
            )
            else {}
        )

        spread = market.get(
            "spread",
            {},
        )

        spread = (
            spread
            if isinstance(
                spread,
                Mapping,
            )
            else {}
        )

        bid = self._number(
            quote.get(
                "bid",
                market.get(
                    "bid",
                    spread.get(
                        "bid"
                    ),
                ),
            )
        )

        ask = self._number(
            quote.get(
                "ask",
                market.get(
                    "ask",
                    spread.get(
                        "ask"
                    ),
                ),
            )
        )

        return {
            "symbol": quote.get(
                "symbol",
                market.get(
                    "symbol"
                ),
            ),

            "bid": bid,

            "ask": ask,

            "mid": (
                (
                    bid
                    + ask
                )
                / 2.0
                if (
                    bid is not None
                    and ask is not None
                )
                else None
            ),

            "spread_points": (
                self._number(
                    spread.get(
                        "current",
                        market.get(
                            "spread_points"
                        ),
                    )
                )
            ),
        }

    # ================================================================
    # ROUTING
    # ================================================================

    def do_OPTIONS(
        self,
    ) -> None:
        if self._request_allowed():
            self._headers(
                status=204
            )

    def do_GET(
        self,
    ) -> None:
        if not self._request_allowed():
            return

        parsed = (
            urllib.parse
            .urlparse(
                self.path
            )
        )

        path = parsed.path

        if path == "/login":
            self.send_response(
                302
            )

            self.send_header(
                "Location",
                "/",
            )

            self.end_headers()
            return

        if path in {
            "/",
            "/broadcast",
        }:
            self._serve_html(
                path == "/broadcast"
            )
            return

        if path == "/api/broadcast/stream":
            self._serve_sse()
            return

        if path == "/api/status":
            self._json(
                self._status()
            )
            return

        if path == "/api/chart":
            self._chart(
                parsed
            )
            return

        if path == "/api/journal":
            self._journal()
            return

        if path == "/api/daily_report":
            self._daily()
            return

        if path == "/api/backtest_results":
            self._backtest_results()
            return

        if path == "/api/audit_evaluations":
            self._audit()
            return

        if path == "/api/logs":
            self._logs()
            return

        if path == "/api/news_schedule":
            self._json(
                {
                    "events": (
                        news_schedule
                        .get_all_events()
                    )
                }
            )
            return

        self._headers(
            "text/plain; charset=utf-8",
            404,
        )

        self.wfile.write(
            b"Not Found"
        )

    def do_POST(
        self,
    ) -> None:
        if not self._request_allowed():
            return

        path = (
            urllib.parse
            .urlparse(
                self.path
            )
            .path
        )

        try:
            data = self._body()

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

            return

        if path == "/api/settings":
            self._write_settings(
                data
            )
            return

        if path == "/api/reset_settings":
            self._reset_settings()
            return

        if path == "/api/news_schedule/add":
            self._news_add(
                data
            )
            return

        if path == "/api/news_schedule/remove":
            self._news_remove(
                data
            )
            return

        if path == "/api/news_schedule/update":
            self._news_update(
                data
            )
            return

        if path == "/api/execute_trade":
            self._manual_execute(
                data
            )
            return

        if path == "/api/add_symbol":
            self._add_symbol(
                data
            )
            return

        if path == "/api/train":
            self._train()
            return

        if path == "/api/close_all":
            self._close_all()
            return

        if path == "/api/run_analysis":
            self._run_analysis()
            return

        if path == "/api/run_backtest":
            self._run_backtest()
            return

        if path == "/api/run_test":
            self._json(
                {
                    "error": (
                        "DASHBOARD_SUBPROCESS_"
                        "EXECUTION_DISABLED"
                    )
                },
                410,
            )

            return

        self._headers(
            "text/plain; charset=utf-8",
            404,
        )

        self.wfile.write(
            b"Not Found"
        )

    # ================================================================
    # HTML + SSE
    # ================================================================

    def _serve_html(
        self,
        broadcast=False,
    ) -> None:
        nonce = (
            secrets
            .token_urlsafe(
                24
            )
        )

        self._headers(
            (
                "text/html; "
                "charset=utf-8"
            ),
            nonce=nonce,
        )

        template = (
            HTML_TEMPLATE
        )

        if broadcast:
            try:
                from dashboard.html_template import (
                    BROADCAST_TEMPLATE,
                )

                template = (
                    BROADCAST_TEMPLATE
                )

            except Exception:
                pass

        self.wfile.write(
            str(
                template
            )
            .replace(
                "{{NONCE}}",
                nonce,
            )
            .encode(
                "utf-8"
            )
        )

    def _serve_sse(
        self,
    ) -> None:
        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            (
                "text/event-stream; "
                "charset=utf-8"
            ),
        )

        self.send_header(
            "Cache-Control",
            (
                "no-cache, "
                "no-transform"
            ),
        )

        self.send_header(
            "Connection",
            "keep-alive",
        )

        self.send_header(
            "X-Accel-Buffering",
            "no",
        )

        origin = self.headers.get(
            "Origin"
        )

        if self._local_url(
            origin
        ):
            self.send_header(
                "Access-Control-Allow-Origin",
                str(
                    origin
                ),
            )

            self.send_header(
                "Vary",
                "Origin",
            )

        self.end_headers()

        last_cycle = None

        try:
            while True:
                snap = (
                    self._snapshot()
                )

                if not snap:
                    self._sse(
                        "status",
                        {
                            "connected": False,
                            "reason": (
                                "SNAPSHOT_UNAVAILABLE"
                            ),
                        },
                    )

                else:
                    cycle = (
                        snap.get(
                            "cycle_id"
                        )
                    )

                    account = (
                        snap.get(
                            "account",
                            {},
                        )
                    )

                    account = (
                        account
                        if isinstance(
                            account,
                            Mapping,
                        )
                        else {}
                    )

                    self._sse(
                        "tick",
                        {
                            **self._quote(
                                snap
                            ),

                            "pnl": (
                                self._number(
                                    account.get(
                                        "profit"
                                    )
                                )
                            ),

                            "cycle_id": (
                                cycle
                            ),
                        },
                    )

                    if (
                        cycle
                        != last_cycle
                    ):
                        self._sse(
                            "chart_snapshot",
                            snap,
                        )

                        last_cycle = (
                            cycle
                        )

                time.sleep(
                    0.5
                )

        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            OSError,
        ):
            return

    def _sse(
        self,
        event: str,
        payload: Any,
    ) -> None:
        body = json.dumps(
            json_safe(
                payload
            ),
            ensure_ascii=False,
            allow_nan=False,
        )

        self.wfile.write(
            (
                f"event: {event}\n"
                f"data: {body}\n\n"
            ).encode(
                "utf-8"
            )
        )

        self.wfile.flush()

    # ================================================================
    # STATUS
    # ================================================================

    def _status(
        self,
    ) -> Dict[str, Any]:
        """
        Pure dashboard projection.

        Does NOT call:
          - evaluate_entry_rules()
          - get_trading_signal()
          - TradeBrain.evaluate()
          - strategy evaluators
          - sentiment refresh
          - optimizer
        """

        snap = self._snapshot()

        if not snap:
            return {
                "connected": False,
                "status": "INITIALIZING",
                "settings": self._settings(),
                "symbols": [],
                "account": {},
                "positions": [],
                "history": self._history(),
                "market_regime": "UNKNOWN",
                "prediction": {},
                "spread": {
                    "current": None,
                    "bid": None,
                    "ask": None,
                },
                "strategy_suggestion": None,
                "strategy_rankings": [],
                "diagnostics_status": (
                    "UNAVAILABLE"
                ),
            }

        account = snap.get(
            "account",
            {},
        )

        account = (
            account
            if isinstance(
                account,
                Mapping,
            )
            else {}
        )

        risk = snap.get(
            "risk_status",
            {},
        )

        risk = (
            risk
            if isinstance(
                risk,
                Mapping,
            )
            else {}
        )

        market = snap.get(
            "market",
            {},
        )

        market = (
            market
            if isinstance(
                market,
                Mapping,
            )
            else {}
        )

        diag = snap.get(
            "diagnostics",
            {},
        )

        diag = (
            diag
            if isinstance(
                diag,
                Mapping,
            )
            else {}
        )

        model = snap.get(
            "model_status",
            {},
        )

        model = (
            model
            if isinstance(
                model,
                Mapping,
            )
            else {}
        )

        pred = snap.get(
            "prediction",
            {},
        )

        pred = (
            pred
            if isinstance(
                pred,
                Mapping,
            )
            else {}
        )

        starvation = snap.get(
            "starvation_stats",
            {},
        )

        starvation = (
            starvation
            if isinstance(
                starvation,
                Mapping,
            )
            else {}
        )

        tf = snap.get(
            "tf_alignment",
            {},
        )

        tf = (
            tf
            if isinstance(
                tf,
                Mapping,
            )
            else {}
        )

        session = snap.get(
            "session_context",
            {},
        )

        session = (
            session
            if isinstance(
                session,
                Mapping,
            )
            else {}
        )

        quote = self._quote(
            snap
        )

        spread_raw = market.get(
            "spread",
            {},
        )

        spread = (
            dict(
                spread_raw
            )
            if isinstance(
                spread_raw,
                Mapping,
            )
            else {}
        )

        spread.update(
            {
                "bid": quote[
                    "bid"
                ],

                "ask": quote[
                    "ask"
                ],

                "current": (
                    quote[
                        "spread_points"
                    ]
                ),
            }
        )

        positions = []

        for pos in (
            snap.get(
                "positions",
                [],
            )
            or []
        ):
            if not isinstance(
                pos,
                Mapping,
            ):
                continue

            positions.append(
                {
                    "ticket": pos.get(
                        "ticket"
                    ),

                    "symbol": pos.get(
                        "symbol"
                    ),

                    "action": pos.get(
                        "action"
                    ),

                    "volume": pos.get(
                        "volume"
                    ),

                    "entry_price": (
                        pos.get(
                            "entry_price",
                            pos.get(
                                "entry"
                            ),
                        )
                    ),

                    "sl": pos.get(
                        "sl"
                    ),

                    "tp": pos.get(
                        "tp"
                    ),

                    "pnl": pos.get(
                        "pnl"
                    ),

                    "age_seconds": (
                        pos.get(
                            "age_seconds"
                        )
                    ),

                    "entry_time_utc": (
                        pos.get(
                            "entry_time_utc"
                        )
                    ),
                }
            )

        routing = snap.get(
            "routing",
            {},
        )

        routing = (
            routing
            if isinstance(
                routing,
                Mapping,
            )
            else {}
        )

        suggestion = snap.get(
            "strategy_suggestion"
        )

        if (
            not isinstance(
                suggestion,
                Mapping,
            )
            or not suggestion
        ):
            candidate = (
                routing.get(
                    "suggestions"
                )
            )

            suggestion = (
                candidate
                if (
                    isinstance(
                        candidate,
                        Mapping,
                    )
                    and candidate
                )
                else None
            )

        suggestion = (
            dict(
                suggestion
            )
            if isinstance(
                suggestion,
                Mapping,
            )
            else None
        )

        rankings = [
            dict(
                row
            )
            for row
            in (
                snap.get(
                    "strategy_rankings",
                    [],
                )
                or []
            )
            if isinstance(
                row,
                Mapping,
            )
        ]

        paper = bool(
            risk.get(
                "paper_mode",
                self._settings().get(
                    "paper_mode",
                    True,
                ),
            )
        )

        allowed = diag.get(
            "allowed"
        )

        return {
            "connected": bool(
                snap.get(
                    "connected",
                    True,
                )
            ),

            "snapshot_version": (
                snap.get(
                    "snapshot_version"
                )
            ),

            "cycle_id": snap.get(
                "cycle_id"
            ),

            "cycle_number": snap.get(
                "cycle_number"
            ),

            "generated_at_utc": (
                snap.get(
                    "generated_at_utc"
                )
            ),

            "account": {
                "broker": account.get(
                    "broker"
                ),

                "server": (
                    "DEMO"
                    if paper
                    else "LIVE"
                ),

                "login": account.get(
                    "login"
                ),

                "balance": account.get(
                    "balance"
                ),

                "equity": account.get(
                    "equity"
                ),

                "profit": account.get(
                    "profit"
                ),

                "leverage": account.get(
                    "leverage"
                ),

                "margin_level": (
                    account.get(
                        "margin_level"
                    )
                ),

                "mode": (
                    "paper"
                    if paper
                    else "live"
                ),
            },

            "settings": self._settings(),

            "symbols": list(
                snap.get(
                    "symbols",
                    [],
                )
                or []
            ),

            "sentiment": (
                dict(
                    market.get(
                        "sentiment",
                        {},
                    )
                )
                if isinstance(
                    market.get(
                        "sentiment"
                    ),
                    Mapping,
                )
                else {}
            ),

            "volume": (
                dict(
                    market.get(
                        "volume",
                        {},
                    )
                )
                if isinstance(
                    market.get(
                        "volume"
                    ),
                    Mapping,
                )
                else {}
            ),

            "positions": positions,

            "history": self._history(),

            "market_regime": (
                market.get(
                    "regime",
                    market.get(
                        "market_regime",
                        "UNKNOWN",
                    ),
                )
            ),

            "training_status": (
                model.get(
                    "training_status",
                    "idle",
                )
            ),

            "latency_ms": (
                self._number(
                    market.get(
                        "latency_ms",
                        diag.get(
                            "latency_ms"
                        ),
                    )
                )
            ),

            "spread": spread,

            "prediction": dict(
                pred
            ),

            "skipped_stats": dict(
                starvation
            ),

            "active_sessions": list(
                snap.get(
                    "active_sessions",
                    [],
                )
                or []
            ),

            "tf_alignment": dict(
                tf
            ),

            "starvation_stats": dict(
                starvation
            ),

            "session_context": dict(
                session
            ),

            # No fabricated fallback.
            "strategy_suggestion": (
                suggestion
            ),

            "strategy_rankings": (
                rankings
            ),

            "diagnostics_status": (
                "HEALTHY"
                if allowed is True
                else (
                    "UNHEALTHY"
                    if allowed is False
                    else "UNKNOWN"
                )
            ),

            "model_status": dict(
                model
            ),

            "risk_status": dict(
                risk
            ),

            "is_new_candle_close": (
                False
            ),
        }

    # ================================================================
    # CHART
    # ================================================================

    def _chart(
        self,
        parsed,
    ) -> None:
        try:
            query = (
                urllib.parse
                .parse_qs(
                    parsed.query
                )
            )

            snap = self._snapshot()

            symbols = (
                list(
                    snap.get(
                        "symbols",
                        [],
                    )
                    or []
                )
                if snap
                else []
            )

            raw = (
                query.get(
                    "symbol",
                    [None],
                )[0]
                or (
                    symbols[0]
                    if symbols
                    else settings_manager.get(
                        "active_symbol",
                        "",
                    )
                )
            )

            symbol = (
                resolve_broker_symbol(
                    str(
                        raw
                        or ""
                    ),
                    self.engine,
                )
            )

            tf_name = str(
                query.get(
                    "timeframe",
                    ["M5"],
                )[0]
            ).upper()

            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }

            if (
                not symbol
                or tf_name
                not in tf_map
            ):
                raise ValueError(
                    (
                        "Invalid symbol "
                        "or timeframe"
                    )
                )

            rates = (
                mt5.copy_rates_from_pos(
                    symbol,
                    tf_map[
                        tf_name
                    ],
                    0,
                    350,
                )
            )

            if (
                rates is None
                or len(
                    rates
                )
                == 0
            ):
                self._json(
                    {
                        "symbol": symbol,
                        "timeframe": tf_name,
                        "candles": [],
                        "fvgs": [],
                        "sweeps": [],
                        "mss": [],
                        "levels": {},
                        "trades": [],
                        "error": (
                            "NO_MARKET_DATA"
                        ),
                    }
                )

                return

            import pandas as pd

            df = pd.DataFrame(
                rates
            )

            candles = [
                {
                    "time": int(
                        row[
                            "time"
                        ]
                    ),

                    "open": float(
                        row[
                            "open"
                        ]
                    ),

                    "high": float(
                        row[
                            "high"
                        ]
                    ),

                    "low": float(
                        row[
                            "low"
                        ]
                    ),

                    "close": float(
                        row[
                            "close"
                        ]
                    ),

                    "volume": (
                        float(
                            row[
                                "tick_volume"
                            ]
                        )
                        if (
                            "tick_volume"
                            in rates.dtype.names
                        )
                        else 0.0
                    ),
                }
                for row
                in rates
            ]

            df[
                "time_dt"
            ] = pd.to_datetime(
                df[
                    "time"
                ],
                unit="s",
                utc=True,
            )

            df.set_index(
                "time_dt",
                inplace=True,
            )

            df.rename(
                columns={
                    "tick_volume": (
                        "volume"
                    )
                },
                inplace=True,
            )

            # Display current candle but calculate
            # SMC only from closed candles.
            closed = (
                df.iloc[
                    :-1
                ]
                .tail(
                    300
                )
                .copy()
                if len(
                    df
                ) > 1
                else df.iloc[
                    0:0
                ].copy()
            )

            fvgs = []
            sweeps = []
            mss_events = []
            levels: Dict[str, Any] = {}

            if len(
                closed
            ) >= 20:
                from utils.smc_indicators import (
                    SMCIndicators,
                )

                smc = (
                    SMCIndicators
                    .compute_smc_features(
                        closed,
                        window=int(
                            settings_manager.get(
                                "smc_swing_window",
                                3,
                            )
                        ),
                    )
                )

                last = smc.iloc[
                    -1
                ]

                levels = {
                    key: (
                        self._number(
                            last.get(
                                key
                            )
                        )
                    )
                    for key
                    in (
                        "support",
                        "resistance",
                        "ob_top",
                        "ob_bottom",
                    )
                }

                levels[
                    "ob_direction"
                ] = (
                    str(
                        last.get(
                            "ob_direction"
                        )
                    )
                    if (
                        str(
                            last.get(
                                "ob_direction",
                                "none",
                            )
                        ).lower()
                        not in {
                            "none",
                            "nan",
                            "",
                        }
                    )
                    else None
                )

                for _, row in (
                    smc.iterrows()
                ):
                    ftype = int(
                        row.get(
                            "fvg_type",
                            0,
                        )
                        or 0
                    )

                    fclass = str(
                        row.get(
                            "fvg_class",
                            "",
                        )
                    ).lower()

                    top = self._number(
                        row.get(
                            "fvg_top"
                        )
                    )

                    bottom = (
                        self._number(
                            row.get(
                                "fvg_bottom"
                            )
                        )
                    )

                    if (
                        ftype
                        and top
                        is not None
                        and bottom
                        is not None
                        and fclass
                        in {
                            "bag",
                            "rfvg",
                        }
                    ):
                        fvgs.append(
                            {
                                "type": (
                                    "bullish"
                                    if ftype > 0
                                    else "bearish"
                                ),

                                "top": top,

                                "bottom": (
                                    bottom
                                ),

                                "class": (
                                    fclass
                                ),
                            }
                        )

                    sweep = int(
                        row.get(
                            "liq_sweep_type",
                            0,
                        )
                        or 0
                    )

                    if sweep:
                        sweeps.append(
                            {
                                "type": (
                                    "bullish"
                                    if sweep > 0
                                    else "bearish"
                                ),

                                "price": (
                                    self._number(
                                        row.get(
                                            "liq_sweep_level"
                                        )
                                    )
                                ),
                            }
                        )

                    mss = int(
                        row.get(
                            "mss_signal",
                            0,
                        )
                        or 0
                    )

                    if mss:
                        mss_events.append(
                            {
                                "type": (
                                    "bullish"
                                    if mss > 0
                                    else "bearish"
                                ),

                                "price": (
                                    self._number(
                                        row.get(
                                            "close"
                                        )
                                    )
                                ),
                            }
                        )

            # Quiet chart defaults.
            fvgs = fvgs[
                -8:
            ]

            sweeps = sweeps[
                -5:
            ]

            mss_events = (
                mss_events[
                    -5:
                ]
            )

            market = (
                snap.get(
                    "market",
                    {},
                )
                if (
                    snap
                    and isinstance(
                        snap.get(
                            "market"
                        ),
                        Mapping,
                    )
                )
                else {}
            )

            extra = (
                market.get(
                    "levels",
                    {},
                )
                if isinstance(
                    market,
                    Mapping,
                )
                else {}
            )

            if isinstance(
                extra,
                Mapping,
            ):
                for key in (
                    "pdh",
                    "pdl",
                    "pwh",
                    "pwl",
                    "entry_price",
                    "entry_action",
                    "sl_price",
                    "tp_price",
                ):
                    if key in extra:
                        levels[
                            key
                        ] = extra.get(
                            key
                        )

            trades = [
                {
                    "ticket": (
                        pos.get(
                            "ticket"
                        )
                    ),

                    "type": pos.get(
                        "action"
                    ),

                    "volume": (
                        pos.get(
                            "volume"
                        )
                    ),

                    "entry": (
                        pos.get(
                            "entry_price",
                            pos.get(
                                "entry"
                            ),
                        )
                    ),

                    "sl": pos.get(
                        "sl"
                    ),

                    "tp": pos.get(
                        "tp"
                    ),

                    "pnl": pos.get(
                        "pnl"
                    ),
                }

                for pos
                in (
                    snap.get(
                        "positions",
                        [],
                    )
                    if snap
                    else []
                )

                if (
                    isinstance(
                        pos,
                        Mapping,
                    )
                    and str(
                        pos.get(
                            "symbol",
                            "",
                        )
                    )
                    == symbol
                )
            ]

            self._json(
                {
                    "symbol": symbol,
                    "timeframe": tf_name,
                    "candles": candles,
                    "fvgs": fvgs,
                    "sweeps": sweeps,
                    "mss": mss_events,
                    "levels": levels,
                    "trades": trades,
                }
            )

        except Exception as exc:
            LOG.exception(
                (
                    "Chart endpoint "
                    "failed: %s"
                ),
                exc,
            )

            self._json(
                {
                    "error": (
                        "CHART_DATA_ERROR"
                    ),

                    "detail": str(
                        exc
                    ),
                },
                500,
            )

    # ================================================================
    # READ-ONLY SECONDARY DATA
    # ================================================================

    def _history(
        self,
    ):
        try:
            from core.trade_journal import (
                trade_journal,
            )

            rows = (
                trade_journal
                .get_all_trades()
                or []
            )

            return [
                {
                    "id": row.get(
                        "execution_id",
                        row.get(
                            "decision_id",
                            f"J-{i + 1}",
                        ),
                    ),

                    "symbol": row.get(
                        "symbol"
                    ),

                    "action": row.get(
                        "action"
                    ),

                    "volume": row.get(
                        "lot_size"
                    ),

                    "entry_price": (
                        row.get(
                            "entry_price"
                        )
                    ),

                    "close_price": (
                        row.get(
                            "close_price"
                        )
                    ),

                    "entry_time_utc": (
                        row.get(
                            "entry_time_utc"
                        )
                    ),

                    "close_time_utc": (
                        row.get(
                            "close_time_utc"
                        )
                    ),

                    "close_reason": (
                        row.get(
                            "close_reason"
                        )
                    ),

                    "pnl": row.get(
                        "pnl"
                    ),

                    "r_multiple": (
                        row.get(
                            "r_multiple",
                            row.get(
                                "net_r"
                            ),
                        )
                    ),

                    "strategy_name": (
                        row.get(
                            "strategy_name"
                        )
                    ),

                    "entry_pattern": (
                        row.get(
                            "entry_pattern"
                        )
                    ),
                }

                for i, row
                in enumerate(
                    rows[
                        -50:
                    ]
                )

                if isinstance(
                    row,
                    Mapping,
                )
            ]

        except Exception:
            return []

    def _journal(
        self,
    ):
        try:
            from core.trade_journal import (
                trade_journal,
            )

            rows = (
                trade_journal
                .get_all_trades()
                or []
            )

            self._json(
                {
                    "trades": (
                        rows[
                            -200:
                        ]
                    ),

                    "total": len(
                        rows
                    ),
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _daily(
        self,
    ):
        try:
            from core.trade_journal import (
                trade_journal,
            )

            analyzer = getattr(
                self.engine,
                "daily_analyzer",
                None,
            )

            report = (
                analyzer.get_latest_report()
                if (
                    analyzer
                    is not None
                    and hasattr(
                        analyzer,
                        "get_latest_report",
                    )
                )
                else None
            )

            self._json(
                {
                    "report": report,

                    "today_summary": (
                        trade_journal
                        .get_daily_summary()
                    ),
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _backtest_results(
        self,
    ):
        try:
            backtester = getattr(
                self.engine,
                "backtester",
                None,
            )

            self._json(
                (
                    backtester
                    .get_last_results()
                    if backtester
                    else {}
                )
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _audit(
        self,
    ):
        try:
            import sqlite3

            from core.database import (
                db_instance,
            )

            with db_instance._lock:
                conn = sqlite3.connect(
                    db_instance.db_path
                )

                conn.row_factory = (
                    sqlite3.Row
                )

                try:
                    rows = conn.execute(
                        (
                            "SELECT * FROM "
                            "audit_evaluations "
                            "ORDER BY id DESC "
                            "LIMIT 100"
                        )
                    ).fetchall()

                finally:
                    conn.close()

            self._json(
                {
                    "evaluations": [
                        dict(
                            row
                        )
                        for row
                        in rows
                    ]
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _logs(
        self,
    ):
        try:
            lines = []
            path = (
                "logs/engine.log"
            )

            if os.path.isfile(
                path
            ):
                with open(
                    path,
                    "rb",
                ) as handle:
                    handle.seek(
                        0,
                        os.SEEK_END,
                    )

                    size = (
                        handle.tell()
                    )

                    handle.seek(
                        max(
                            0,
                            size
                            - 64
                            * 1024,
                        )
                    )

                    lines = (
                        handle.read()
                        .decode(
                            "utf-8",
                            errors="replace",
                        )
                        .splitlines()[
                            -50:
                        ]
                    )

            self._json(
                {
                    "logs": lines
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    # ================================================================
    # CONTROL PLANE
    # ================================================================

    def _write_settings(
        self,
        data,
    ):
        try:
            validate_settings(
                data
            )

            prepared = dict(
                data
            )

            if "active_symbol" in prepared:
                prepared[
                    "active_symbol"
                ] = (
                    resolve_broker_symbol(
                        str(
                            prepared[
                                "active_symbol"
                            ]
                        ),
                        self.engine,
                    )
                )

            if hasattr(
                settings_manager,
                "set_many",
            ):
                settings_manager.set_many(
                    prepared,

                    source=(
                        "DASHBOARD_API"
                    ),

                    reason=(
                        "User updated "
                        "settings via dashboard"
                    ),
                )

            else:
                for key, value in (
                    prepared.items()
                ):
                    settings_manager.set(
                        key,
                        value,

                        source=(
                            "DASHBOARD_API"
                        ),

                        reason=(
                            "Dashboard update"
                        ),
                    )

            self._json(
                {
                    "status": (
                        "success"
                    ),

                    "settings": (
                        self._settings()
                    ),
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    def _reset_settings(
        self,
    ):
        try:
            settings_manager.reset_all(
                source=(
                    "DASHBOARD_API"
                )
            )

            self._json(
                {
                    "status": (
                        "success"
                    ),

                    "settings": (
                        self._settings()
                    ),
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    def _news_add(
        self,
        data,
    ):
        try:
            ok = (
                news_schedule
                .add_event(
                    str(
                        data.get(
                            "day",
                            "",
                        )
                    ).strip(),

                    str(
                        data.get(
                            "time_utc",
                            "",
                        )
                    ).strip(),

                    str(
                        data.get(
                            "name",
                            "",
                        )
                    ).strip(),

                    int(
                        data.get(
                            "duration_mins",
                            30,
                        )
                    ),

                    currency=str(
                        data.get(
                            "currency",
                            "USD",
                        )
                    ),

                    impact=str(
                        data.get(
                            "impact",
                            "HIGH",
                        )
                    ),
                )
            )

            if not ok:
                raise ValueError(
                    (
                        "Invalid or "
                        "duplicate manual event"
                    )
                )

            self._json(
                {
                    "status": (
                        "success"
                    )
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    def _news_remove(
        self,
        data,
    ):
        try:
            if not (
                news_schedule
                .remove_event(
                    int(
                        data.get(
                            "index",
                            -1,
                        )
                    )
                )
            ):
                raise ValueError(
                    "Invalid event index"
                )

            self._json(
                {
                    "status": (
                        "success"
                    )
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    def _news_update(
        self,
        data,
    ):
        try:
            kwargs = {
                key: data[
                    key
                ]
                for key
                in (
                    "day",
                    "time_utc",
                    "name",
                    "duration_mins",
                    "currency",
                    "impact",
                )
                if key
                in data
            }

            if (
                "duration_mins"
                in kwargs
            ):
                kwargs[
                    "duration_mins"
                ] = int(
                    kwargs[
                        "duration_mins"
                    ]
                )

            if not (
                news_schedule
                .update_event(
                    int(
                        data.get(
                            "index",
                            -1,
                        )
                    ),
                    **kwargs,
                )
            ):
                raise ValueError(
                    (
                        "Manual event "
                        "update rejected"
                    )
                )

            self._json(
                {
                    "status": (
                        "success"
                    )
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    def _manual_execute(
        self,
        data,
    ):
        """
        Legacy dashboard code invented entry,
        SL and TP.

        That bypass is prohibited.
        """

        if (
            self.engine is not None
            and hasattr(
                self.engine,
                (
                    "execute_validated_"
                    "dashboard_candidate"
                ),
            )
        ):
            try:
                result = (
                    self.engine
                    .execute_validated_dashboard_candidate(
                        data
                    )
                )

                self._json(
                    {
                        "status": (
                            "success"
                        ),

                        "result": (
                            result
                        ),
                    }
                )

                return

            except Exception as exc:
                self._json(
                    {
                        "error": str(
                            exc
                        )
                    },
                    400,
                )

                return

        self._json(
            {
                "error": (
                    "MANUAL_EXECUTION_"
                    "REQUIRES_VALIDATED_"
                    "CANDIDATE"
                ),

                "reason": (
                    "Dashboard cannot invent "
                    "entry/SL/TP or bypass "
                    "SafetyEngine, RiskEngine "
                    "and ExecutionValidator."
                ),
            },
            409,
        )

    def _add_symbol(
        self,
        data,
    ):
        try:
            raw = str(
                data.get(
                    "symbol",
                    "",
                )
            ).strip()

            resolved = (
                resolve_broker_symbol(
                    raw,
                    self.engine,
                )
            )

            if (
                not raw
                or mt5.symbol_info(
                    resolved
                )
                is None
            ):
                raise ValueError(
                    (
                        "Symbol not found "
                        "on broker"
                    )
                )

            settings_manager.set(
                "active_symbol",
                resolved,

                source=(
                    "DASHBOARD_API"
                ),

                reason=(
                    "User selected "
                    "broker symbol"
                ),
            )

            self._json(
                {
                    "status": (
                        "success"
                    ),

                    "symbol": (
                        resolved
                    ),
                }
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                400,
            )

    # ================================================================
    # BACKGROUND COMMANDS
    # ================================================================

    def _train(
        self,
    ):
        if getattr(
            self.engine,
            "training_in_progress",
            False,
        ):
            self._json(
                {
                    "status": (
                        "already_running"
                    )
                },
                409,
            )

            return

        threading.Thread(
            target=(
                self._training_worker
            ),
            daemon=True,
        ).start()

        self._json(
            {
                "status": (
                    "shadow_training_started"
                )
            },
            202,
        )

    def _training_worker(
        self,
    ):
        if (
            self.engine is None
            or getattr(
                self.engine,
                "training_in_progress",
                False,
            )
        ):
            return

        self.engine.training_in_progress = (
            True
        )

        try:
            trigger = getattr(
                self.engine,
                (
                    "trigger_historical_"
                    "training"
                ),
                None,
            )

            if trigger:
                trigger()

        except Exception as exc:
            LOG.error(
                (
                    "Shadow training "
                    "trigger failed: %s"
                ),
                exc,
            )

        finally:
            self.engine.training_in_progress = (
                False
            )

    def _close_all(
        self,
    ):
        try:
            trigger = getattr(
                self.engine,
                (
                    "trigger_emergency_"
                    "panic_close"
                ),
                None,
            )

            if trigger is None:
                raise RuntimeError(
                    (
                        "Emergency close "
                        "unavailable"
                    )
                )

            result = trigger()

            command_id = (
                result.get(
                    "command_id"
                )
                if isinstance(
                    result,
                    Mapping,
                )
                else None
            )

            self._json(
                {
                    "status": (
                        "ACCEPTED"
                    ),

                    "command_id": (
                        command_id
                    ),

                    "message": (
                        "Emergency close "
                        "command queued"
                    ),
                },
                202,
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _run_analysis(
        self,
    ):
        try:
            analyzer = getattr(
                self.engine,
                "daily_analyzer",
                None,
            )

            if analyzer is None:
                raise RuntimeError(
                    (
                        "Daily analyzer "
                        "unavailable"
                    )
                )

            def work():
                from datetime import date

                try:
                    analyzer.analyze_date(
                        date.today()
                    )

                except Exception as exc:
                    LOG.error(
                        (
                            "Daily analysis "
                            "failed: %s"
                        ),
                        exc,
                    )

            threading.Thread(
                target=work,
                daemon=True,
            ).start()

            self._json(
                {
                    "status": (
                        "analysis_started"
                    )
                },
                202,
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )

    def _run_backtest(
        self,
    ):
        try:
            backtester = getattr(
                self.engine,
                "backtester",
                None,
            )

            if backtester is None:
                raise RuntimeError(
                    "Backtester unavailable"
                )

            snap = self._snapshot()

            symbols = list(
                snap.get(
                    "symbols",
                    [],
                )
                or []
            )

            symbol = (
                symbols[0]
                if symbols
                else str(
                    settings_manager.get(
                        "active_symbol",
                        "",
                    )
                )
            )

            mode = str(
                settings_manager.get(
                    "trading_mode",
                    "scalping",
                )
            )

            def work():
                try:
                    backtester.self_optimize(
                        symbol,
                        trading_mode=mode,
                    )

                except Exception as exc:
                    LOG.error(
                        (
                            "Validation backtest "
                            "failed: %s"
                        ),
                        exc,
                    )

            threading.Thread(
                target=work,
                daemon=True,
            ).start()

            self._json(
                {
                    "status": (
                        "validation_backtest_"
                        "started"
                    ),

                    "symbol": symbol,

                    "mode": mode,

                    "production_mutation": (
                        False
                    ),
                },
                202,
            )

        except Exception as exc:
            self._json(
                {
                    "error": str(
                        exc
                    )
                },
                500,
            )


class WebDashboardServer:
    def __init__(
        self,
        engine,
        port=8000,
    ):
        self.engine = engine
        self.port = int(
            port
        )

        self.server = None
        self.thread = None
        self.logger = LOG

    def start(
        self,
    ):
        if self.server is not None:
            return

        factory = (
            lambda *args, **kwargs:
            DashboardRequestHandler(
                self.engine,
                *args,
                **kwargs,
            )
        )

        self.server = (
            ThreadingHTTPServer(
                (
                    "127.0.0.1",
                    self.port,
                ),
                factory,
            )
        )

        self.server.daemon_threads = (
            True
        )

        self.thread = (
            threading.Thread(
                target=self._run,
                daemon=True,
                name=(
                    "PulseViper-"
                    "WebDashboard"
                ),
            )
        )

        self.thread.start()

        self.logger.info(
            (
                "Web dashboard listening "
                "on http://127.0.0.1:%d"
            ),
            self.port,
        )

    def _run(
        self,
    ):
        try:
            if self.server is not None:
                self.server.serve_forever(
                    poll_interval=0.25
                )

        except Exception as exc:
            self.logger.error(
                (
                    "Web dashboard "
                    "server error: %s"
                ),
                exc,
            )

    def stop(
        self,
    ):
        server = self.server
        self.server = None

        if server is not None:
            try:
                server.shutdown()

            finally:
                server.server_close()

        thread = self.thread
        self.thread = None

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(
                timeout=1.0
            )