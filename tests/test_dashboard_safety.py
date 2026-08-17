# tests/test_dashboard_safety.py
import unittest
import json
import secrets
import time
import threading
from unittest.mock import MagicMock, patch
from http.cookies import SimpleCookie

import urllib.parse
from dashboard.web_dashboard import (
    DashboardRequestHandler,
    sessions,
    settings_manager,
    validate_settings
)

class MockServer:
    def __init__(self, port=8000):
        self.server_port = port

class MockRequest:
    def __init__(self, command, path, headers, rfile_data=b""):
        self.command = command
        self.path = path
        self.headers = headers
        self.rfile = MagicMock()
        self.rfile.read.return_value = rfile_data
        self.wfile = MagicMock()

class TestDashboardSafety(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.engine.symbols = ["EURUSDm"]
        self.engine.market_state = {"latency_ms": 1.2}
        self.engine.get_dashboard_snapshot.return_value = {
            "connected": True,
            "cycle_number": 42,
            "account": {
                "balance": 10000.0,
                "equity": 10050.0,
                "profit": 50.0,
                "leverage": 500,
                "margin_level": 999.9,
                "broker": "MOCK"
            },
            "risk_status": {"paper_mode": True},
            "positions": [],
            "tf_alignment": {},
            "market": {"regime": "RANGE"},
            "routing": {"suggestions": {}}
        }
        
        # Save settings state
        self.original_settings = dict(settings_manager.settings)
        settings_manager.set("control_token", "super_secret_token")

    def tearDown(self):
        # Restore settings
        settings_manager.settings = self.original_settings
        sessions.clear()

    def _make_handler(self, command, path, headers_dict, rfile_data=b""):
        headers = MagicMock()
        headers.get = lambda k, default=None: headers_dict.get(k, default)
        headers.__contains__ = lambda k: k in headers_dict
        
        # Implement SimpleCookie behavior mock
        cookie_val = headers_dict.get("Cookie")
        headers.get_all = lambda k, default=None: [cookie_val] if (k == "Cookie" and cookie_val) else []
        
        req = MockRequest(command, path, headers, rfile_data)
        server = MockServer()
        
        # Instantiate without running base constructor by mocking it or mocking handler logic
        with patch('http.server.BaseHTTPRequestHandler.__init__', lambda *a, **kw: None):
            handler = DashboardRequestHandler(self.engine, req, ('127.0.0.1', 12345), server)
            handler.request = req
            handler.wfile = req.wfile
            handler.rfile = req.rfile
            handler.headers = headers
            handler.command = command
            handler.path = path
            handler.server = server
            
            # Mock send_response and headers
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.send_error = MagicMock()
            
            return handler

    def test_host_header_validation(self):
        # 1. Valid host local port
        headers = {"Host": "127.0.0.1:8000"}
        handler = self._make_handler("GET", "/api/status", headers)
        self.assertTrue(handler._validate_host_and_origin())
        
        # 2. Invalid host dns rebinding
        headers = {"Host": "evil-attacker.com"}
        handler = self._make_handler("GET", "/api/status", headers)
        self.assertFalse(handler._validate_host_and_origin())
        handler.send_error.assert_called_with(400, "Invalid Host header")

    def test_origin_header_validation_on_mutations(self):
        # POST mutation request
        # 1. Valid origin local port
        headers = {
            "Host": "localhost:8000",
            "Origin": "http://localhost:8000"
        }
        handler = self._make_handler("POST", "/api/settings", headers)
        self.assertTrue(handler._validate_host_and_origin())
        
        # 2. Invalid Origin (CORS attempt)
        headers = {
            "Host": "localhost:8000",
            "Origin": "http://malicious-site.com"
        }
        handler = self._make_handler("POST", "/api/settings", headers)
        self.assertFalse(handler._validate_host_and_origin())
        handler.send_error.assert_called_with(403, "Invalid Origin or Referer header")

    def test_auth_token_bypass_origin_validation(self):
        # Automation scripts using control token header bypass CORS origin check
        headers = {
            "Host": "localhost:8000",
            "X-PulseViper-Control-Token": "super_secret_token"
        }
        handler = self._make_handler("POST", "/api/settings", headers)
        self.assertTrue(handler._validate_host_and_origin())

    def test_direct_request_without_login(self):
        # Direct GET / should succeed with 200 without requiring login
        headers = {"Host": "localhost:8000"}
        handler = self._make_handler("GET", "/", headers)
        handler.do_GET()
        handler.send_response.assert_called_with(200)

    def test_api_status_without_auth(self):
        # GET /api/status should return 200 without requiring auth
        headers = {"Host": "localhost:8000"}
        handler = self._make_handler("GET", "/api/status", headers)
        handler.do_GET()
        handler.send_response.assert_called_with(200)

    def test_authenticated_token_header(self):
        # Request with control token header
        headers = {
            "Host": "localhost:8000",
            "X-PulseViper-Control-Token": "super_secret_token"
        }
        handler = self._make_handler("GET", "/api/status", headers)
        handler.do_GET()
        handler.send_response.assert_called_with(200)

    def test_login_route_redirects_to_root(self):
        # GET /login should redirect to /
        headers = {"Host": "localhost:8000"}
        handler = self._make_handler("GET", "/login", headers)
        handler.do_GET()
        handler.send_response.assert_called_with(302)
        handler.send_header.assert_any_call("Location", "/")

    def test_settings_validation_schema(self):
        # 1. Invalid setting type
        invalid_data = {"paper_mode": "NOT_A_BOOLEAN"}
        with self.assertRaises(ValueError):
            validate_settings(invalid_data)
            
        # 2. Invalid range setting
        invalid_range = {"risk_percent": 0.5}
        with self.assertRaises(ValueError):
            validate_settings(invalid_range)
            
        # 3. Valid settings
        valid_data = {"paper_mode": True, "risk_percent": 0.02}
        self.assertTrue(validate_settings(valid_data))

    def test_async_panic_emergency_response(self):
        # Trigger close all
        self.engine.trigger_emergency_panic_close.return_value = {
            "command_id": "CMD-PANIC-123",
            "completion_event": threading.Event(),
            "result_holder": {}
        }
        
        headers = {
            "Host": "localhost:8000",
            "X-PulseViper-Control-Token": "super_secret_token"
        }
        handler = self._make_handler("POST", "/api/close_all", headers)
        handler.do_POST()
        
        # Since wait event is not set, it returns 202 Accepted
        handler.send_response.assert_called_with(202)
        write_call = handler.wfile.write.call_args[0][0]
        resp_data = json.loads(write_call.decode('utf-8'))
        self.assertEqual(resp_data["status"], "ACCEPTED")
        self.assertEqual(resp_data["command_id"], "CMD-PANIC-123")

    def test_broadcast_mode_route(self):
        headers = {
            "Host": "localhost:8000"
        }
        handler = self._make_handler("GET", "/broadcast", headers)
        handler.client_address = ("127.0.0.1", 12345)
        handler.do_GET()
        handler.send_response.assert_called_with(200)

if __name__ == '__main__':
    unittest.main()
