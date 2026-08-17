from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Sequence


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


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


def _ensure_dirs() -> None:
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


def _venv_python() -> Path:
    if os.name == "nt":
        return (
            ROOT
            / "venv"
            / "Scripts"
            / "python.exe"
        )

    return (
        ROOT
        / "venv"
        / "bin"
        / "python"
    )


def resolve_python() -> str:
    candidates = []

    project_python = (
        _venv_python()
    )

    if project_python.is_file():
        candidates.append(
            str(
                project_python
            )
        )

    current_python = str(
        Path(
            sys.executable
        ).resolve()
    )

    if (
        current_python
        not in candidates
    ):
        candidates.append(
            current_python
        )

    for candidate in candidates:
        try:
            result = (
                subprocess.run(
                    [
                        candidate,
                        "--version",
                    ],

                    capture_output=True,

                    text=True,

                    encoding="utf-8",

                    errors="replace",

                    timeout=10,

                    check=False,
                )
            )

            if (
                result.returncode
                == 0
            ):
                return candidate

        except Exception:
            continue

    raise RuntimeError(
        (
            "No working Python "
            "interpreter found. "
            "Create the project venv "
            "and install requirements."
        )
    )


def port_in_use(
    port: int,
) -> bool:
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:
        sock.settimeout(
            0.35
        )

        return (
            sock.connect_ex(
                (
                    "127.0.0.1",
                    int(
                        port
                    ),
                )
            )
            == 0
        )


def run_preflight(
    python_exe: str,
    skip_mt5: bool,
) -> bool:
    """
    Read-only startup check.

    No settings changes.
    No orders.
    """

    checker = r'''
import os

required = [
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("sklearn", "scikit-learn"),
    ("scipy", "scipy"),
    ("torch", "torch"),
]

missing = []

for import_name, package_name in required:
    try:
        __import__(import_name)
    except Exception as exc:
        missing.append(
            f"{package_name}:"
            f"{type(exc).__name__}:"
            f"{exc}"
        )

if missing:
    print(
        "DEPENDENCY_ERROR|"
        + "||".join(missing)
    )
    raise SystemExit(10)

if os.environ.get(
    "PV_SKIP_MT5",
    "0",
) == "1":
    print("OK|MT5_SKIPPED")
    raise SystemExit(0)

try:
    import MetaTrader5 as mt5
except Exception as exc:
    print(
        "MT5_IMPORT_ERROR|"
        f"{type(exc).__name__}|"
        f"{exc}"
    )
    raise SystemExit(11)

if not mt5.initialize(
    timeout=5000
):
    print(
        "MT5_INIT_ERROR"
    )
    raise SystemExit(12)

try:
    account = (
        mt5.account_info()
    )

    if account is None:
        print(
            "MT5_ACCOUNT_ERROR"
        )
        raise SystemExit(13)

    # Do not print login/account ID.
    print(
        "OK|"
        + str(
            getattr(
                account,
                "company",
                "",
            )
            or "BROKER"
        )
    )

finally:
    mt5.shutdown()
'''

    env = os.environ.copy()

    env[
        "PYTHONIOENCODING"
    ] = "utf-8"

    env[
        "PYTHONUTF8"
    ] = "1"

    env[
        "PV_SKIP_MT5"
    ] = (
        "1"
        if skip_mt5
        else "0"
    )

    try:
        result = (
            subprocess.run(
                [
                    python_exe,
                    "-c",
                    checker,
                ],

                capture_output=True,

                text=True,

                encoding="utf-8",

                errors="replace",

                env=env,

                timeout=60,

                check=False,
            )
        )

    except subprocess.TimeoutExpired:
        print(
            (
                "[ERROR] "
                "Preflight timed out."
            )
        )

        return False

    output = (
        (
            result.stdout
            or ""
        )
        + "\n"
        + (
            result.stderr
            or ""
        )
    ).strip()

    if result.returncode != 0:
        print(
            (
                "[ERROR] "
                "Preflight failed:"
            )
        )

        print(
            output
            or (
                "Unknown preflight "
                f"failure ({result.returncode})"
            )
        )

        return False

    print(
        (
            "[OK] Preflight passed: "
            + (
                output
                or "OK"
            )
        )
    )

    return True


def wait_for_dashboard(
    process: subprocess.Popen,
    port: int,
    timeout_seconds: float = 20.0,
) -> bool:
    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    while (
        time.monotonic()
        < deadline
    ):
        if (
            process.poll()
            is not None
        ):
            return False

        if port_in_use(
            port
        ):
            return True

        time.sleep(
            0.25
        )

    return port_in_use(
        port
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PulseViper Safe Launcher"
        )
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
    )

    parser.add_argument(
        "--skip-preflight",
        action="store_true",
    )

    parser.add_argument(
        "--skip-mt5",
        action="store_true",
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
    )

    parser.add_argument(
        "--mode",
        choices=(
            "scalping",
            "intraday",
            "swing",
        ),
        default=None,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--allow-live-orders",
        action="store_true",
    )

    return parser


def main(
    argv: Optional[
        Sequence[str]
    ] = None,
) -> int:
    _configure_stdio()
    _ensure_dirs()

    parser = (
        _build_parser()
    )

    args, extra = (
        parser.parse_known_args(
            argv
        )
    )

    if not (
        1024
        <= int(
            args.port
        )
        <= 65535
    ):
        parser.error(
            (
                "port must be between "
                "1024 and 65535"
            )
        )

    python_exe = (
        resolve_python()
    )

    if (
        not args.skip_preflight
        and not run_preflight(
            python_exe,
            args.skip_mt5,
        )
    ):
        return 1

    # ---------------------------------------------------------
    # DO NOT KILL RANDOM PROCESSES USING THE PORT
    # ---------------------------------------------------------

    if (
        not args.no_dashboard
        and port_in_use(
            args.port
        )
    ):
        print(
            (
                f"[ERROR] Port {args.port} "
                "is already in use.\n"
                "PulseViper will not kill "
                "another process automatically."
            )
        )

        return 2

    run_py = (
        ROOT
        / "run.py"
    )

    if not run_py.is_file():
        print(
            (
                "[ERROR] "
                "run.py is missing."
            )
        )

        return 2

    command = [
        python_exe,
        str(
            run_py
        ),
        "--port",
        str(
            args.port
        ),
    ]

    if args.no_dashboard:
        command.append(
            "--no-dashboard"
        )

    if args.symbols:
        command.extend(
            [
                "--symbols",
                *[
                    str(
                        symbol
                    )
                    for symbol
                    in args.symbols
                ],
            ]
        )

    if args.mode:
        command.extend(
            [
                "--mode",
                args.mode,
            ]
        )

    if (
        args.interval
        is not None
    ):
        command.extend(
            [
                "--interval",
                str(
                    args.interval
                ),
            ]
        )

    if args.allow_live_orders:
        command.append(
            "--allow-live-orders"
        )

    # Preserve future run.py CLI
    # arguments without shell=True.
    command.extend(
        extra
    )

    env = os.environ.copy()

    env[
        "PYTHONIOENCODING"
    ] = "utf-8"

    env[
        "PYTHONUTF8"
    ] = "1"

    print(
        "[INFO] Starting PulseViper..."
    )

    print(
        (
            "[INFO] Python: "
            + python_exe
        )
    )

    process = (
        subprocess.Popen(
            command,

            cwd=str(
                ROOT
            ),

            env=env,
        )
    )

    if not args.no_dashboard:
        ready = (
            wait_for_dashboard(
                process,
                args.port,
            )
        )

        url = (
            "http://127.0.0.1:"
            f"{args.port}"
        )

        if ready:
            print(
                (
                    "[OK] Dashboard: "
                    + url
                )
            )

            if not args.no_browser:
                try:
                    webbrowser.open(
                        url,

                        new=2,

                        autoraise=False,
                    )

                except Exception:
                    pass

        elif (
            process.poll()
            is None
        ):
            print(
                (
                    "[WARN] Engine is "
                    "running but dashboard "
                    "is not ready."
                )
            )

    try:
        return int(
            process.wait()
        )

    except KeyboardInterrupt:
        print(
            (
                "\n[INFO] "
                "Stopping PulseViper..."
            )
        )

        if (
            process.poll()
            is None
        ):
            process.terminate()

            try:
                return int(
                    process.wait(
                        timeout=10
                    )
                )

            except subprocess.TimeoutExpired:
                process.kill()

                return int(
                    process.wait()
                )

        return 130


if __name__ == "__main__":
    raise SystemExit(
        main()
    )