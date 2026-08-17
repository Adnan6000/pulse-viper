from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Optional, Sequence


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


def _configure_stdio() -> None:
    for stream in (
        sys.stdout,
        sys.stderr,
    ):
        if hasattr(
            stream,
            "reconfigure",
        ):
            try:
                stream.reconfigure(
                    encoding="utf-8",
                    errors="backslashreplace",
                )
            except Exception:
                pass


def _ensure_runtime_dirs() -> None:
    for name in (
        "logs",
        "data",
        "configs",
        "models",
    ):
        (
            ROOT
            / name
        ).mkdir(
            parents=True,
            exist_ok=True,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PulseViper Trading Engine"
        )
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help=(
            "Broker symbols. "
            "If omitted, active_symbol "
            "from settings is used."
        ),
    )

    parser.add_argument(
        "--mode",
        choices=(
            "scalping",
            "intraday",
            "swing",
        ),
        default=None,
        help=(
            "Trading mode. "
            "Explicit value is written "
            "to settings before startup."
        ),
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help=(
            "Analysis interval in seconds."
        ),
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help=(
            "Disable web dashboard."
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help=(
            "Dashboard localhost port."
        ),
    )

    parser.add_argument(
        "--allow-live-orders",
        action="store_true",
        help=(
            "Required when BOTH "
            "paper_mode=false and "
            "auto_trade_enabled=true."
        ),
    )

    return parser


def _validate_cli(
    args: argparse.Namespace,
) -> None:
    if not (
        1024
        <= int(args.port)
        <= 65535
    ):
        raise ValueError(
            (
                "port must be between "
                "1024 and 65535"
            )
        )

    if not (
        0.1
        <= float(args.interval)
        <= 3600.0
    ):
        raise ValueError(
            (
                "interval must be between "
                "0.1 and 3600 seconds"
            )
        )

    if args.symbols:
        args.symbols = [
            str(
                symbol
            ).strip()
            for symbol
            in args.symbols
        ]

        if any(
            not symbol
            for symbol
            in args.symbols
        ):
            raise ValueError(
                (
                    "symbols cannot "
                    "contain empty values"
                )
            )


def main(
    argv: Optional[
        Sequence[str]
    ] = None,
) -> int:
    _configure_stdio()
    _ensure_runtime_dirs()

    parser = _build_parser()

    args = parser.parse_args(
        argv
    )

    try:
        _validate_cli(
            args
        )

        from utils.settings_manager import (
            settings_manager,
        )

        # ---------------------------------------------------------
        # CLI MODE MUST MATCH RUNTIME MODE
        # ---------------------------------------------------------

        if args.mode is not None:
            settings_manager.set(
                "trading_mode",
                args.mode,
                source="CLI",
                reason=(
                    "Explicit startup --mode"
                ),
            )

        runtime_mode = str(
            settings_manager.get(
                "trading_mode",
                "scalping",
            )
        ).lower()

        if runtime_mode not in {
            "scalping",
            "intraday",
            "swing",
        }:
            raise RuntimeError(
                (
                    "INVALID_RUNTIME_"
                    "TRADING_MODE:"
                    f"{runtime_mode}"
                )
            )

        # ---------------------------------------------------------
        # EXECUTION-SAFETY STARTUP CHECK
        # ---------------------------------------------------------

        paper_mode = bool(
            settings_manager.get(
                "paper_mode",
                True,
            )
        )

        auto_trade = bool(
            settings_manager.get(
                "auto_trade_enabled",
                False,
            )
        )

        allow_untokenized = bool(
            settings_manager.get(
                "allow_untokenized_orders",
                False,
            )
        )

        if allow_untokenized:
            raise RuntimeError(
                (
                    "UNSAFE_SETTING:"
                    "allow_untokenized_orders "
                    "must be false"
                )
            )

        # Prevent accidental live startup.
        #
        # Monitoring with:
        #   paper_mode = false
        #   auto_trade = false
        #
        # is allowed.
        #
        # Live AUTO execution requires
        # an explicit startup acknowledgement.
        if (
            not paper_mode
            and auto_trade
            and not args.allow_live_orders
        ):
            raise RuntimeError(
                (
                    "LIVE_AUTO_TRADE_"
                    "STARTUP_BLOCKED: "
                    "paper_mode=false and "
                    "auto_trade_enabled=true. "
                    "Use --allow-live-orders "
                    "only after intentional "
                    "live-trading review."
                )
            )

        # ---------------------------------------------------------
        # SYMBOLS
        # ---------------------------------------------------------

        symbols = args.symbols

        if not symbols:
            active_symbol = str(
                settings_manager.get(
                    "active_symbol",
                    "",
                )
                or ""
            ).strip()

            symbols = (
                [
                    active_symbol
                ]
                if active_symbol
                else None
            )

        # Import engine only after
        # settings/startup validation.
        from core.engine import (
            AdvancedTradingEngine,
        )

        print(
            "🐍 PULSE VIPER"
        )

        print(
            "="
            * 56
        )

        print(
            f"Mode       : "
            f"{runtime_mode}"
        )

        print(
            f"Paper mode : "
            f"{paper_mode}"
        )

        print(
            f"Auto trade : "
            f"{auto_trade}"
        )

        print(
            f"Symbols    : "
            f"{symbols or 'AUTO-DETECT'}"
        )

        print(
            (
                "Dashboard  : "
                + (
                    (
                        "http://127.0.0.1:"
                        f"{args.port}"
                    )
                    if not args.no_dashboard
                    else "DISABLED"
                )
            )
        )

        print(
            "="
            * 56
        )

        engine = (
            AdvancedTradingEngine(
                symbols=symbols,

                strategy_mode=(
                    runtime_mode
                ),

                enable_dashboard=(
                    not args.no_dashboard
                ),

                port=int(
                    args.port
                ),
            )
        )

        engine.run_engine(
            sleep_seconds=float(
                args.interval
            )
        )

        return 0

    except KeyboardInterrupt:
        print(
            "\nPulseViper stopped by user."
        )

        return 130

    except Exception as exc:
        print(
            (
                "PulseViper startup/"
                f"runtime error: {exc}"
            )
        )

        traceback.print_exc()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )