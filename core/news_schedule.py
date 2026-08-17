# core/news_schedule.py
"""
Manual Weekly News Schedule System
===================================
Allows the user to define a fixed weekly timetable of high-impact news events.
Only USD high-impact events block trading.
This runs ALONGSIDE the ForexFactory live calendar as a fallback and override.

Schedule is stored in: configs/news_schedule.json
Format:
  [
    { "day": "Monday",   "time_utc": "14:30", "name": "USD ISM Manufacturing PMI",  "duration_mins": 30 },
    { "day": "Tuesday",  "time_utc": "14:30", "name": "USD JOLTS Job Openings",      "duration_mins": 30 },
    ...
  ]

day: Monday-Friday (or "Daily" for every day)
time_utc: HH:MM in UTC
duration_mins: How many minutes to block BEFORE AND AFTER the event (default 30 pre, 15 post)
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional


# ── Default high-impact USD weekly schedule ──────────────────────────────────
# These are the most impactful USD events that reliably move Gold/Forex
DEFAULT_SCHEDULE: List[Dict] = [
    # Monday
    {"day": "Monday",    "time_utc": "14:00", "name": "USD ISM Manufacturing PMI",        "duration_mins": 5},

    # Tuesday
    {"day": "Tuesday",   "time_utc": "14:30", "name": "USD JOLTS Job Openings",            "duration_mins": 5},
    {"day": "Tuesday",   "time_utc": "19:00", "name": "FOMC Member Speech",                "duration_mins": 5},

    # Wednesday
    {"day": "Wednesday", "time_utc": "14:15", "name": "USD ADP Non-Farm Employment",       "duration_mins": 5},
    {"day": "Wednesday", "time_utc": "14:30", "name": "USD Trade Balance",                 "duration_mins": 5},
    {"day": "Wednesday", "time_utc": "15:00", "name": "USD ISM Non-Manufacturing PMI",     "duration_mins": 5},
    {"day": "Wednesday", "time_utc": "18:00", "name": "FOMC Rate Decision",                "duration_mins": 5},
    {"day": "Wednesday", "time_utc": "18:30", "name": "FOMC Press Conference",             "duration_mins": 5},

    # Thursday
    {"day": "Thursday",  "time_utc": "14:30", "name": "USD Initial Jobless Claims",        "duration_mins": 5},
    {"day": "Thursday",  "time_utc": "14:30", "name": "USD PPI MoM",                       "duration_mins": 5},

    # Friday
    {"day": "Friday",    "time_utc": "14:30", "name": "USD Non-Farm Payrolls (NFP)",       "duration_mins": 5},
    {"day": "Friday",    "time_utc": "14:30", "name": "USD Average Hourly Earnings MoM",   "duration_mins": 5},
    {"day": "Friday",    "time_utc": "14:30", "name": "USD Unemployment Rate",             "duration_mins": 5},
    {"day": "Friday",    "time_utc": "16:00", "name": "USD Michigan Consumer Sentiment",   "duration_mins": 5},
]

SCHEDULE_FILE = "configs/news_schedule.json"
DAYS_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
}


class NewsScheduleManager:
    """
    Manages a user-defined weekly news blackout timetable.
    Blocks trading X minutes before and Y minutes after each event.
    """
    def __init__(self, schedule_file: str = SCHEDULE_FILE):
        self.schedule_file = schedule_file
        self.logger = logging.getLogger("PulseViper.NewsSchedule")
        self.schedule: List[Dict] = []
        self._load()

    def _load(self):
        """Load schedule from file, or create default."""
        if os.path.exists(self.schedule_file):
            try:
                with open(self.schedule_file, "r") as f:
                    self.schedule = json.load(f)
                
                # Auto-migrate: convert any old 20/30/60 min default durations to 5 mins
                migrated = False
                for ev in self.schedule:
                    if ev.get("duration_mins", 30) in [30, 20, 60]:
                        ev["duration_mins"] = 5
                        migrated = True
                if migrated:
                    self._save()
                    self.logger.info("Migrated old weekly schedule events to 5-minute durations")
                
                self.logger.info(f"News schedule loaded: {len(self.schedule)} events")
            except Exception as e:
                self.logger.error(f"Failed to load news schedule: {e}. Using defaults.")
                self.schedule = list(DEFAULT_SCHEDULE)
                self._save()
        else:
            self.logger.info("No news schedule found. Creating default USD high-impact schedule.")
            self.schedule = list(DEFAULT_SCHEDULE)
            self._save()

    def _save(self):
        """Persist schedule to disk."""
        try:
            os.makedirs(os.path.dirname(self.schedule_file), exist_ok=True)
            with open(self.schedule_file, "w") as f:
                json.dump(self.schedule, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save news schedule: {e}")

    def add_event(self, day: str, time_utc: str, name: str, duration_mins: int = 30) -> bool:
        """Add a new event to the schedule."""
        if day not in DAYS_MAP and day != "Daily":
            return False
        try:
            h, m = map(int, time_utc.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return False
        except Exception:
            return False

        # Avoid exact duplicates
        for ev in self.schedule:
            if ev["day"] == day and ev["time_utc"] == time_utc and ev["name"] == name:
                return False

        self.schedule.append({
            "day": day,
            "time_utc": time_utc,
            "name": name,
            "duration_mins": duration_mins
        })
        self._save()
        self.logger.info(f"News schedule: added '{name}' on {day} at {time_utc} UTC ({duration_mins}m block)")
        return True

    def remove_event(self, index: int) -> bool:
        """Remove event by index."""
        if 0 <= index < len(self.schedule):
            removed = self.schedule.pop(index)
            self._save()
            self.logger.info(f"News schedule: removed '{removed['name']}' on {removed['day']}")
            return True
        return False

    def update_event(self, index: int, day: Optional[str] = None, time_utc: Optional[str] = None,
                     name: Optional[str] = None, duration_mins: Optional[int] = None) -> bool:
        """Update an existing event by index."""
        if 0 <= index < len(self.schedule):
            ev = self.schedule[index]
            if day is not None:
                ev["day"] = day
            if time_utc is not None:
                ev["time_utc"] = time_utc
            if name is not None:
                ev["name"] = name
            if duration_mins is not None:
                ev["duration_mins"] = duration_mins
            self._save()
            return True
        return False

    def get_all_events(self) -> List[Dict]:
        """Return full schedule for dashboard display."""
        return list(self.schedule)

    def is_blocked(self, current_utc: Optional[datetime] = None,
                   pre_mins: int = 30, post_mins: int = 15) -> Tuple[bool, Optional[str]]:
        """
        Check if trading should be blocked right now due to a scheduled news event.

        Args:
            current_utc: Current UTC datetime (defaults to now)
            pre_mins: Minutes to block BEFORE event (default 30, can be overridden by event's duration_mins)
            post_mins: Minutes to block AFTER event (default 15)

        Returns:
            (is_blocked: bool, reason: Optional[str])
        """
        if not self.schedule:
            return False, None

        if current_utc is None:
            current_utc = datetime.now(timezone.utc)

        # Get current weekday (0=Monday)
        current_weekday = current_utc.weekday()
        current_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                             "Friday", "Saturday", "Sunday"][current_weekday]

        for event in self.schedule:
            event_day = event.get("day", "")
            if event_day != current_day_name and event_day != "Daily":
                continue

            time_str = event.get("time_utc", "00:00")
            dur = int(event.get("duration_mins", pre_mins))
            name = event.get("name", "Unknown Event")

            try:
                h, m = map(int, time_str.split(":"))
                # Build event datetime for today
                event_dt = current_utc.replace(
                    hour=h, minute=m, second=0, microsecond=0
                )

                # Block window: pre_mins before → post_mins after
                block_start = event_dt - timedelta(minutes=dur)
                block_end = event_dt + timedelta(minutes=post_mins)

                if block_start <= current_utc <= block_end:
                    mins_to_event = int((event_dt - current_utc).total_seconds() / 60)
                    if mins_to_event >= 0:
                        reason = f"📅 NEWS BLOCK: '{name}' in {mins_to_event}m (UTC {time_str})"
                    else:
                        mins_after = int((current_utc - event_dt).total_seconds() / 60)
                        reason = f"📅 NEWS COOLDOWN: '{name}' ended {mins_after}m ago (UTC {time_str})"
                    return True, reason
            except Exception:
                continue

        return False, None

    def get_upcoming_events(self, hours_ahead: int = 24) -> List[Dict]:
        """Return events in the next N hours with time-to-event."""
        now = datetime.now(timezone.utc)
        current_weekday = now.weekday()
        upcoming = []

        for day_offset in range(7):  # Check next 7 days
            check_weekday = (current_weekday + day_offset) % 7
            check_day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                               "Friday", "Saturday", "Sunday"][check_weekday]

            for event in self.schedule:
                if event.get("day") != check_day_name and event.get("day") != "Daily":
                    continue
                try:
                    h, m = map(int, event["time_utc"].split(":"))
                    event_dt = (now + timedelta(days=day_offset)).replace(
                        hour=h, minute=m, second=0, microsecond=0
                    )
                    diff_hours = (event_dt - now).total_seconds() / 3600
                    if 0 <= diff_hours <= hours_ahead:
                        upcoming.append({
                            "name": event["name"],
                            "day": event["day"],
                            "time_utc": event["time_utc"],
                            "duration_mins": event.get("duration_mins", 30),
                            "minutes_until": int((event_dt - now).total_seconds() / 60),
                            "event_dt_utc": event_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        })
                except Exception:
                    continue

        upcoming.sort(key=lambda x: x["minutes_until"])
        return upcoming


# Singleton instance
news_schedule = NewsScheduleManager()
