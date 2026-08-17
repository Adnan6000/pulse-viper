from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = (
    Path(
        __file__
    )
    .resolve()
    .parents[
        1
    ]
)


PRODUCTION_PATHS = (
    ROOT
    / "core",

    ROOT
    / "utils",

    ROOT
    / "strategies",

    ROOT
    / "dashboard",

    ROOT
    / "configs",
)


ALLOWED_RAW_MT5 = {
    "utils/mt5_gateway.py",

    "core/execution_service.py",

    (
        "core/"
        "emergency_exit_controller.py"
    ),
}


class TestMT5Imports(
    unittest.TestCase
):
    def test_raw_metatrader5_imports_are_restricted(
        self,
    ):
        violations = []

        files = []

        for directory in (
            PRODUCTION_PATHS
        ):
            if directory.exists():
                files.extend(
                    directory.rglob(
                        "*.py"
                    )
                )

        files.extend(
            path
            for path in (
                ROOT
                / "run.py",

                ROOT
                / "launcher.py",
            )
            if path.exists()
        )

        for path in files:
            relative = (
                path
                .relative_to(
                    ROOT
                )
                .as_posix()
            )

            if (
                relative
                in ALLOWED_RAW_MT5
            ):
                continue

            try:
                tree = ast.parse(
                    path.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    ),

                    filename=(
                        relative
                    ),
                )

            except SyntaxError as exc:
                self.fail(
                    (
                        "Cannot parse "
                        f"{relative}: "
                        f"{exc}"
                    )
                )

            for node in ast.walk(
                tree
            ):
                if isinstance(
                    node,
                    ast.Import,
                ):
                    for alias in (
                        node.names
                    ):
                        if (
                            alias.name
                            == "MetaTrader5"
                        ):
                            violations.append(
                                (
                                    f"{relative}:"
                                    f"{node.lineno}"
                                )
                            )

                elif isinstance(
                    node,
                    ast.ImportFrom,
                ):
                    if (
                        node.module
                        == "MetaTrader5"
                    ):
                        violations.append(
                            (
                                f"{relative}:"
                                f"{node.lineno}"
                            )
                        )

        self.assertEqual(
            violations,
            [],
            (
                "Raw MetaTrader5 "
                "imports found outside "
                "approved choke-point "
                "files:\n"
                + "\n".join(
                    violations
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()