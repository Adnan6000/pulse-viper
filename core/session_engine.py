# core/session_engine.py
"""
PulseViper Session Intelligence Engine.
Identifies active Forex trading sessions (UTC) and assigns quality scores for XAUUSD trading.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

class SessionEngine:
    def __init__(self):
        self.logger = logging.getLogger("PulseViper.SessionEngine")
        # Define session time ranges (start_hour_utc, end_hour_utc, name for gold, name for others)
        self.session_ranges = [
            # (start_hour, end_hour, gold_name, other_name, is_overlap_ny_open)
            (0, 8, "GOLD_ASIAN", "ASIAN", False),
            (8, 10, "GOLD_LDN_OPEN", "LONDON", False),
            (10, 13, "GOLD_LONDON", "LONDON", False),
            (13, 15, "GOLD_OVERLAP_NY_OPEN", "OVERLAP", True),
            (15, 17, "GOLD_OVERLAP", "OVERLAP", True),
            (17, 21, "GOLD_NEW_YORK", "NEW_YORK", False),
        ]

    def get_session_context(self, current_time_utc: Optional[datetime] = None, symbol: Optional[str] = None) -> Dict:
        """
        Determine session status and quality score for a given UTC datetime and symbol.
        Defaults to current UTC time.
        """
        if current_time_utc is None:
            current_time_utc = datetime.now(timezone.utc)

        hour = current_time_utc.hour
        minute = current_time_utc.minute
        time_fraction = hour + minute / 60.0
        current_total_minutes = hour * 60 + minute

        is_gold = symbol is not None and ("XAU" in symbol.upper() or "GOLD" in symbol.upper())
        
        # Detect crypto symbols — they trade 24/7 with no weekend closure
        is_crypto = False
        if symbol is not None:
            sym_up = symbol.upper()
            crypto_bases = ["BTC", "ETH", "LTC", "XRP", "SOL", "DOGE", "ADA", "DOT", "AVAX", "MATIC", "BNB", "LINK"]
            is_crypto = any(c in sym_up for c in crypto_bases)

        session_name = "GOLD_OFF" if is_gold else "OFF"
        score = 0.0
        remaining_minutes = 0
        start_hour = 0
        end_hour = 0

        # Crypto: always active with a base score — no weekend closure
        if is_crypto:
            session_name = "CRYPTO_24H"
            # Give higher score during high-volume hours (13:00-21:00 UTC = US session)
            if 13 <= hour < 21:
                score = 12.0
                session_name = "CRYPTO_US_SESSION"
            elif 8 <= hour < 13:
                score = 10.0
                session_name = "CRYPTO_EU_SESSION"
            else:
                score = 8.0
                session_name = "CRYPTO_ASIA_SESSION"
            remaining_minutes = 60 - minute  # Next hour boundary
            return {
                "session_name": session_name,
                "session_score": score,
                "hour_utc": hour,
                "minute_utc": minute,
                "weekday": current_time_utc.weekday(),
                "remaining_minutes": remaining_minutes,
                "start_hour_utc": 0,
                "end_hour_utc": 24
            }

        # Check weekend (only for non-crypto)
        if current_time_utc.weekday() in (5, 6):
            session_name = "WEEKEND"
            score = 0.0
            # Calculate remaining time until Monday 00:00 UTC
            days_until_monday = (7 - current_time_utc.weekday()) % 7
            end_datetime = current_time_utc + timedelta(days=days_until_monday)
            end_datetime = end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            delta = end_datetime - current_time_utc
            remaining_minutes = int(delta.total_seconds() / 60)
        else:
            # Find active session
            for (start_h, end_h, gold_name, other_name, _) in self.session_ranges:
                if start_h <= time_fraction < end_h:
                    session_name = gold_name if is_gold else other_name
                    start_hour = start_h
                    end_hour = end_h
                    # Calculate score based on session type
                    if "OVERLAP" in session_name:
                        score = 15.0
                    elif "LDN_OPEN" in session_name:
                        score = 14.0
                    elif "LONDON" in session_name:
                        score = 10.0
                    elif "NEW_YORK" in session_name:
                        score = 8.0
                    elif "ASIAN" in session_name:
                        score = 2.0
                    # Calculate remaining minutes
                    end_total_minutes = end_h * 60
                    remaining_minutes = end_total_minutes - current_total_minutes
                    break
            else:
                # No active session, find next session start
                next_start_h = 0
                for (start_h, _, _, _, _) in self.session_ranges:
                    if start_h > time_fraction:
                        next_start_h = start_h
                        break
                else:
                    next_start_h = 0  # Next day first session
                next_start_total = next_start_h * 60
                if next_start_total > current_total_minutes:
                    remaining_minutes = next_start_total - current_total_minutes
                else:
                    remaining_minutes = (24*60 - current_total_minutes) + next_start_total

        return {
            "session_name": session_name,
            "session_score": score,
            "hour_utc": hour,
            "minute_utc": minute,
            "weekday": current_time_utc.weekday(),
            "remaining_minutes": remaining_minutes,
            "start_hour_utc": start_hour,
            "end_hour_utc": end_hour
        }

    def get_session_score(self, current_time_utc: Optional[datetime] = None, symbol: Optional[str] = None) -> float:
        """Helper to get just the quality score."""
        return self.get_session_context(current_time_utc, symbol)["session_score"]

    def get_session_name(self, current_time_utc: Optional[datetime] = None, symbol: Optional[str] = None) -> str:
        """Helper to get just the session name."""
        return self.get_session_context(current_time_utc, symbol)["session_name"]
