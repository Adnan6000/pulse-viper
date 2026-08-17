from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


SCHEDULE_FILE = (
    "configs/news_schedule.json"
)

# No invented weekly macro timetable.
DEFAULT_SCHEDULE: List[
    Dict[
        str,
        Any,
    ]
] = []

DAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

DAYS_MAP = {
    day: index
    for index, day
    in enumerate(
        DAYS
    )
}


class NewsScheduleManager:
    """
    Explicit operator-maintained manual news schedule.

    Manual schedule can contain/display any events.

    But execution blocking still requires:

        currency == USD
        impact == HIGH

    NewsIntelligenceEngine checks this schedule only when:

        use_manual_news_schedule == True
    """

    def __init__(
        self,
        schedule_file: str = (
            SCHEDULE_FILE
        ),
    ):
        self.schedule_file = (
            schedule_file
        )

        self.logger = logging.getLogger(
            "PulseViper.NewsSchedule"
        )

        self.schedule: List[
            Dict[
                str,
                Any,
            ]
        ] = []

        self._lock = (
            threading.RLock()
        )

        self._load()

    # =========================================================================
    # NORMALIZATION
    # =========================================================================

    @staticmethod
    def _normalize_currency(
        value: Any,
    ) -> str:

        raw = re.sub(
            r"[^A-Z]",
            "",
            str(
                value
                or ""
            ).upper(),
        )

        if raw in {
            "USD",
            "US",
            "USA",
            "UNITEDSTATES",
        }:

            return "USD"

        if len(
            raw
        ) == 3:

            return raw

        return raw

    @staticmethod
    def _normalize_impact(
        value: Any,
    ) -> str:

        raw = re.sub(
            r"\s+",
            " ",
            str(
                value
                or ""
            )
            .strip()
            .upper(),
        )

        if raw in {
            "HIGH",
            "HIGH IMPACT",
        }:

            return "HIGH"

        if raw in {
            "MEDIUM",
            "MED",
            "MEDIUM IMPACT",
        }:

            return "MEDIUM"

        if raw in {
            "LOW",
            "LOW IMPACT",
        }:

            return "LOW"

        return raw

    @staticmethod
    def _valid_time(
        value: str,
    ) -> bool:

        try:

            hour, minute = map(
                int,
                str(
                    value
                ).split(
                    ":"
                ),
            )

            return (
                0
                <= hour
                <= 23
                and 0
                <= minute
                <= 59
            )

        except Exception:

            return False

    @classmethod
    def _normalize_event(
        cls,
        event: Dict[
            str,
            Any,
        ],
    ) -> Optional[
        Dict[
            str,
            Any,
        ]
    ]:

        if not isinstance(
            event,
            dict,
        ):

            return None

        day = str(
            event.get(
                "day",
                "",
            )
        ).strip()

        time_utc = str(
            event.get(
                "time_utc",
                "",
            )
        ).strip()

        name = str(
            event.get(
                "name",
                "",
            )
        ).strip()

        if (
            day not in DAYS_MAP
            and day != "Daily"
        ):

            return None

        if not cls._valid_time(
            time_utc
        ):

            return None

        if not name:

            return None

        # Important:
        #
        # Existing old rows missing currency/impact DO NOT inherit USD/HIGH
        # because of their event name.
        currency = (
            cls._normalize_currency(
                event.get(
                    "currency",
                    "",
                )
            )
        )

        impact = (
            cls._normalize_impact(
                event.get(
                    "impact",
                    "",
                )
            )
        )

        try:

            duration = max(
                0,
                min(
                    1440,
                    int(
                        event.get(
                            "duration_mins",
                            30,
                        )
                    ),
                ),
            )

        except Exception:

            duration = 30

        return {
            "day": (
                day
            ),

            "time_utc": (
                time_utc
            ),

            "name": (
                name
            ),

            # Kept for dashboard compatibility.
            "duration_mins": (
                duration
            ),

            "currency": (
                currency
            ),

            "impact": (
                impact
            ),

            "source": (
                "MANUAL"
            ),
        }

    @classmethod
    def _is_blocking_event(
        cls,
        event: Dict[
            str,
            Any,
        ],
    ) -> bool:

        return (
            cls._normalize_currency(
                event.get(
                    "currency",
                    "",
                )
            )
            == "USD"
            and
            cls._normalize_impact(
                event.get(
                    "impact",
                    "",
                )
            )
            == "HIGH"
        )

    # =========================================================================
    # LOAD / SAVE
    # =========================================================================

    def _load(
        self,
    ) -> None:

        with self._lock:

            if not os.path.exists(
                self.schedule_file
            ):

                self.schedule = []

                self._save_locked()

                self.logger.info(
                    (
                        "No manual news "
                        "schedule found; "
                        "created empty schedule."
                    )
                )

                return

            try:

                with open(
                    self.schedule_file,
                    "r",
                    encoding="utf-8",
                ) as handle:

                    data = json.load(
                        handle
                    )

                if not isinstance(
                    data,
                    list,
                ):

                    raise ValueError(
                        (
                            "News schedule "
                            "root must be list."
                        )
                    )

                normalized: List[
                    Dict[
                        str,
                        Any,
                    ]
                ] = []

                for row in data:

                    parsed = (
                        self._normalize_event(
                            row
                        )
                    )

                    if parsed is not None:

                        normalized.append(
                            parsed
                        )

                self.schedule = (
                    normalized
                )

                self.logger.info(
                    (
                        "Manual schedule "
                        "loaded: %d rows; "
                        "%d blocking-eligible."
                    ),
                    len(
                        self.schedule
                    ),
                    sum(
                        1
                        for row
                        in self.schedule
                        if self._is_blocking_event(
                            row
                        )
                    ),
                )

            except Exception as exc:

                # Fail empty.
                # Never fall back to invented recurring events.
                self.schedule = []

                self.logger.error(
                    (
                        "Manual schedule "
                        "load failed; "
                        "using empty schedule: %s"
                    ),
                    exc,
                )

    def _save_locked(
        self,
    ) -> None:

        directory = os.path.dirname(
            self.schedule_file
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True,
            )

        temp_path = (
            self.schedule_file
            + ".tmp"
        )

        with open(
            temp_path,
            "w",
            encoding="utf-8",
        ) as handle:

            json.dump(
                self.schedule,
                handle,
                indent=2,
                allow_nan=False,
            )

            handle.flush()

            try:

                os.fsync(
                    handle.fileno()
                )

            except OSError:

                pass

        os.replace(
            temp_path,
            self.schedule_file,
        )

    def _save(
        self,
    ) -> None:

        with self._lock:

            try:

                self._save_locked()

            except Exception as exc:

                self.logger.error(
                    (
                        "Failed saving "
                        "manual schedule: %s"
                    ),
                    exc,
                )

    # =========================================================================
    # MUTATION
    # =========================================================================

    def add_event(
        self,
        day: str,
        time_utc: str,
        name: str,
        duration_mins: int = 30,
        currency: str = "USD",
        impact: str = "HIGH",
    ) -> bool:
        """
        Backward compatible with old four-argument dashboard calls.

        Newly-added manual rows default to explicit USD/HIGH because this is
        specifically the USD high-impact manual blackout schedule.
        """

        candidate = (
            self._normalize_event(
                {
                    "day": (
                        day
                    ),

                    "time_utc": (
                        time_utc
                    ),

                    "name": (
                        name
                    ),

                    "duration_mins": (
                        duration_mins
                    ),

                    "currency": (
                        currency
                    ),

                    "impact": (
                        impact
                    ),
                }
            )
        )

        if candidate is None:

            return False

        with self._lock:

            for existing in (
                self.schedule
            ):

                if (
                    existing.get(
                        "day"
                    )
                    == candidate[
                        "day"
                    ]
                    and existing.get(
                        "time_utc"
                    )
                    == candidate[
                        "time_utc"
                    ]
                    and existing.get(
                        "name"
                    )
                    == candidate[
                        "name"
                    ]
                    and existing.get(
                        "currency"
                    )
                    == candidate[
                        "currency"
                    ]
                    and existing.get(
                        "impact"
                    )
                    == candidate[
                        "impact"
                    ]
                ):

                    return False

            self.schedule.append(
                candidate
            )

            try:

                self._save_locked()

            except Exception as exc:

                self.schedule.pop()

                self.logger.error(
                    (
                        "Failed persisting "
                        "added event: %s"
                    ),
                    exc,
                )

                return False

        return True

    def remove_event(
        self,
        index: int,
    ) -> bool:

        index = int(
            index
        )

        with self._lock:

            if not (
                0
                <= index
                < len(
                    self.schedule
                )
            ):

                return False

            removed = (
                self.schedule.pop(
                    index
                )
            )

            try:

                self._save_locked()

            except Exception as exc:

                self.schedule.insert(
                    index,
                    removed,
                )

                self.logger.error(
                    (
                        "Failed persisting "
                        "removed event: %s"
                    ),
                    exc,
                )

                return False

        return True

    def update_event(
        self,
        index: int,
        day: Optional[
            str
        ] = None,
        time_utc: Optional[
            str
        ] = None,
        name: Optional[
            str
        ] = None,
        duration_mins: Optional[
            int
        ] = None,
        currency: Optional[
            str
        ] = None,
        impact: Optional[
            str
        ] = None,
    ) -> bool:

        index = int(
            index
        )

        with self._lock:

            if not (
                0
                <= index
                < len(
                    self.schedule
                )
            ):

                return False

            old = copy.deepcopy(
                self.schedule[
                    index
                ]
            )

            candidate = copy.deepcopy(
                old
            )

            if day is not None:

                candidate[
                    "day"
                ] = day

            if time_utc is not None:

                candidate[
                    "time_utc"
                ] = time_utc

            if name is not None:

                candidate[
                    "name"
                ] = name

            if duration_mins is not None:

                candidate[
                    "duration_mins"
                ] = duration_mins

            if currency is not None:

                candidate[
                    "currency"
                ] = currency

            if impact is not None:

                candidate[
                    "impact"
                ] = impact

            normalized = (
                self._normalize_event(
                    candidate
                )
            )

            if normalized is None:

                return False

            self.schedule[
                index
            ] = normalized

            try:

                self._save_locked()

            except Exception as exc:

                self.schedule[
                    index
                ] = old

                self.logger.error(
                    (
                        "Failed persisting "
                        "updated event: %s"
                    ),
                    exc,
                )

                return False

        return True

    # =========================================================================
    # READ API
    # =========================================================================

    def get_all_events(
        self,
    ) -> List[
        Dict
    ]:

        with self._lock:

            return [
                {
                    **copy.deepcopy(
                        event
                    ),

                    "blocking_eligible": (
                        self._is_blocking_event(
                            event
                        )
                    ),
                }
                for event
                in self.schedule
            ]

    @staticmethod
    def _normalize_utc(
        value: Optional[
            datetime
        ],
    ) -> datetime:

        if value is None:

            return datetime.now(
                timezone.utc
            )

        if value.tzinfo is None:

            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    # =========================================================================
    # MANUAL BLOCK CHECK
    # =========================================================================

    def is_blocked(
        self,
        current_utc: Optional[
            datetime
        ] = None,
        pre_mins: int = 30,
        post_mins: int = 15,
    ) -> Tuple[
        bool,
        Optional[str],
    ]:
        """
        Manual schedule uses the same global pre/post window.

        Legacy duration_mins is kept for UI compatibility but does not
        silently override the global lockout/cooldown settings.
        """

        now = (
            self._normalize_utc(
                current_utc
            )
        )

        pre_minutes = max(
            0,
            int(
                pre_mins
            ),
        )

        post_minutes = max(
            0,
            int(
                post_mins
            ),
        )

        with self._lock:

            rows = [
                copy.deepcopy(
                    event
                )
                for event
                in self.schedule
            ]

        current_day = (
            DAYS[
                now.weekday()
            ]
        )

        for event in rows:

            # Exact USD + HIGH condition.
            if not self._is_blocking_event(
                event
            ):

                continue

            event_day = str(
                event.get(
                    "day",
                    "",
                )
            )

            if event_day not in {
                current_day,
                "Daily",
            }:

                continue

            try:

                hour, minute = map(
                    int,
                    str(
                        event[
                            "time_utc"
                        ]
                    ).split(
                        ":"
                    ),
                )

            except Exception:

                continue

            event_dt = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            block_start = (
                event_dt
                - timedelta(
                    minutes=(
                        pre_minutes
                    )
                )
            )

            block_end = (
                event_dt
                + timedelta(
                    minutes=(
                        post_minutes
                    )
                )
            )

            if (
                block_start
                <= now
                <= block_end
            ):

                return (
                    True,
                    (
                        "MANUAL_USD_HIGH: "
                        f"{event['name']} @ "
                        f"{event_dt.isoformat().replace('+00:00', 'Z')}"
                    ),
                )

        return (
            False,
            None,
        )

    # =========================================================================
    # UPCOMING EVENTS
    # =========================================================================

    def get_upcoming_events(
        self,
        hours_ahead: int = 24,
    ) -> List[
        Dict
    ]:

        now = datetime.now(
            timezone.utc
        )

        horizon = (
            now
            + timedelta(
                hours=max(
                    0,
                    int(
                        hours_ahead
                    ),
                )
            )
        )

        with self._lock:

            rows = [
                copy.deepcopy(
                    event
                )
                for event
                in self.schedule
            ]

        upcoming: List[
            Dict[
                str,
                Any,
            ]
        ] = []

        days_to_scan = max(
            1,
            int(
                (
                    horizon
                    - now
                ).total_seconds()
                // 86400
            )
            + 2,
        )

        for day_offset in range(
            days_to_scan
        ):

            reference = (
                now
                + timedelta(
                    days=day_offset
                )
            )

            day_name = (
                DAYS[
                    reference.weekday()
                ]
            )

            for event in rows:

                if event.get(
                    "day"
                ) not in {
                    day_name,
                    "Daily",
                }:

                    continue

                try:

                    hour, minute = map(
                        int,
                        str(
                            event[
                                "time_utc"
                            ]
                        ).split(
                            ":"
                        ),
                    )

                except Exception:

                    continue

                event_dt = (
                    reference.replace(
                        hour=hour,
                        minute=minute,
                        second=0,
                        microsecond=0,
                    )
                )

                if not (
                    now
                    <= event_dt
                    <= horizon
                ):

                    continue

                upcoming.append(
                    {
                        "name": (
                            event[
                                "name"
                            ]
                        ),

                        "day": (
                            event[
                                "day"
                            ]
                        ),

                        "time_utc": (
                            event[
                                "time_utc"
                            ]
                        ),

                        "duration_mins": (
                            event.get(
                                "duration_mins",
                                30,
                            )
                        ),

                        "currency": (
                            event.get(
                                "currency",
                                "",
                            )
                        ),

                        "impact": (
                            event.get(
                                "impact",
                                "",
                            )
                        ),

                        "blocking_eligible": (
                            self._is_blocking_event(
                                event
                            )
                        ),

                        "minutes_until": int(
                            (
                                event_dt
                                - now
                            ).total_seconds()
                            / 60
                        ),

                        "event_dt_utc": (
                            event_dt
                            .isoformat()
                            .replace(
                                "+00:00",
                                "Z",
                            )
                        ),
                    }
                )

        upcoming.sort(
            key=lambda row: (
                row[
                    "event_dt_utc"
                ]
            )
        )

        return upcoming


news_schedule = (
    NewsScheduleManager()
)