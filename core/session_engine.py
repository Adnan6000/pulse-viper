# core/session_engine.py
"""
PulseViper Session Intelligence Engine.
Identifies active Forex trading sessions (UTC) and assigns quality scores for XAUUSD trading.
"""
import logging
from datetime import datetime, time, timezone
from typing import Dict, Tuple

class SessionEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SessionEngine")

    def get_session_context(self, current_time_utc: datetime = None) -> Dict:
        """
        Determine session status and quality score for a given UTC datetime.
        Defaults to current UTC time.
        """
        if current_time_utc is None:
            current_time_utc = datetime.now(timezone.utc)

        hour = current_time_utc.hour
        minute = current_time_utc.minute
        time_fraction = hour + minute / 60.0

        # Define sessions in UTC (standard winter hours used as reference)
        # Asian: 00:00 - 08:00 UTC
        # London: 08:00 - 16:00 UTC
        # New York: 13:00 - 21:00 UTC
        # Overlap (London + NY): 13:00 - 16:00 UTC

        session_name = "OFF"
        score = 0.0

        # Overlap check (highest priority)
        if 13.0 <= time_fraction < 16.0:
            session_name = "OVERLAP"
            score = 15.0
        # London check
        elif 8.0 <= time_fraction < 16.0:
            session_name = "LONDON"
            score = 12.0
        # New York check
        elif 13.0 <= time_fraction < 21.0:
            session_name = "NEW_YORK"
            score = 10.0
        # Asian check
        elif 0.0 <= time_fraction < 8.0:
            session_name = "ASIAN"
            score = 2.0
        else:
            session_name = "OFF"
            score = 0.0

        # Check for weekend (Saturday & Sunday UTC)
        # weekday: 0=Monday, 5=Saturday, 6=Sunday
        if current_time_utc.weekday() in (5, 6):
            session_name = "WEEKEND"
            score = 0.0

        return {
            "session_name": session_name,
            "session_score": score,
            "hour_utc": hour,
            "minute_utc": minute,
            "weekday": current_time_utc.weekday()
        }

    def get_session_score(self, current_time_utc: datetime = None) -> float:
        """Helper to get just the quality score."""
        return self.get_session_context(current_time_utc)["session_score"]

    def get_session_name(self, current_time_utc: datetime = None) -> str:
        """Helper to get just the session name."""
        return self.get_session_context(current_time_utc)["session_name"]
