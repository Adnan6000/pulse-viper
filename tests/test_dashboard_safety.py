from __future__ import annotations

import inspect
import unittest

from dashboard.html_template import HTML_TEMPLATE
from dashboard.web_dashboard import (
    DashboardRequestHandler,
    json_safe,
    redact,
    validate_settings,
)


class TestDashboardSafety(unittest.TestCase):
    def test_local_url_policy(self):
        handler = object.__new__(
            DashboardRequestHandler
        )

        self.assertTrue(
            handler._local_url(
                "http://127.0.0.1:8000"
            )
        )

        self.assertTrue(
            handler._local_url(
                "http://localhost:8000/status"
            )
        )

        self.assertFalse(
            handler._local_url(
                "https://example.com"
            )
        )

        self.assertFalse(
            handler._local_url(
                None
            )
        )

    def test_control_token_cannot_be_persisted(self):
        with self.assertRaises(
            ValueError
        ):
            validate_settings(
                {
                    "control_token":
                    "should-not-be-stored"
                }
            )

    def test_normal_setting_validation(self):
        validate_settings(
            {
                "paper_mode": True
            }
        )

        validate_settings(
            {
                "auto_trade_enabled":
                False
            }
        )

    def test_recursive_redaction(self):
        value = {
            "paper_mode": True,

            "control_token":
            "SECRET",

            "nested": {
                "api_key":
                "SECRET",

                "safe":
                123,
            },
        }

        result = redact(
            value
        )

        self.assertNotIn(
            "control_token",
            result,
        )

        self.assertNotIn(
            "api_key",
            result[
                "nested"
            ],
        )

        self.assertEqual(
            result[
                "nested"
            ][
                "safe"
            ],
            123,
        )

    def test_json_safe_rejects_non_finite_numbers(self):
        self.assertIsNone(
            json_safe(
                float(
                    "nan"
                )
            )
        )

        self.assertIsNone(
            json_safe(
                float(
                    "inf"
                )
            )
        )

        self.assertEqual(
            json_safe(
                1.25
            ),
            1.25,
        )

    def test_no_wildcard_cors(self):
        source = inspect.getsource(
            DashboardRequestHandler
            ._headers
        )

        self.assertNotIn(
            (
                'Access-Control-Allow-'
                'Origin", "*"'
            ),
            source,
        )

    def test_no_legacy_manual_trade_ui(self):
        self.assertNotIn(
            "executeCopilotTrade",
            HTML_TEMPLATE,
        )

        self.assertNotIn(
            (
                "EXECUTE CO-PILOT "
                "TRADE"
            ),
            HTML_TEMPLATE,
        )

        self.assertNotIn(
            "/api/execute_trade",
            HTML_TEMPLATE,
        )

    def test_runtime_data_not_rendered_with_innerhtml(self):
        self.assertNotIn(
            ".innerHTML",
            HTML_TEMPLATE,
        )


if __name__ == "__main__":
    unittest.main()