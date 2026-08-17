from __future__ import annotations

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


class NewsIntelligenceEngine:
    """
    Forex Factory economic calendar + display-only FXStreet sentiment.

    EXECUTION BLOCK POLICY
    ======================

    Live news may block execution ONLY when:

        currency == "USD"
        AND impact == "HIGH"

    No other currency or impact level may create a live execution lock.

    Feed failures:
        - never create synthetic CPI/NFP/FOMC/etc events
        - never reinterpret stale rows as current events
        - strict mode may fail closed with NEWS_CALENDAR_STALE
    """

    FOREX_FACTORY_URL = (
        "https://www.forexfactory.com/"
        "ffcal_week_this.xml"
    )

    FXSTREET_RSS_URL = (
        "https://www.fxstreet.com/rss/news"
    )

    SOURCE_FOREX_FACTORY = (
        "FOREX_FACTORY"
    )

    def __init__(self):
        self.logger = logging.getLogger(
            "PulseViper.NewsEngine"
        )

        self.events: List[
            Dict[str, Any]
        ] = []

        self.news_headlines: List[
            Dict[str, str]
        ] = []

        self.current_sentiment = 0.0

        self.lock = threading.RLock()

        self.running = False

        self.thread: Optional[
            threading.Thread
        ] = None

        self.last_live_attempt: Optional[
            datetime
        ] = None

        self.last_live_success: Optional[
            datetime
        ] = None

        self.last_live_error: Optional[
            str
        ] = None

        self.staleness_threshold = (
            timedelta(
                minutes=30
            )
        )

        self.bullish_keywords = [
            "growth",
            "above forecasts",
            "above expectations",
            "expansion",
            "rebound",
            "surges",
            "jumps",
            "rally",
            "positive",
            "optimism",
            "beats",
            "strong",
            "improves",
            "upgrades",
            "higher",
            "hawkish",
            "support",
            "gains",
            "steady",
            "upgraded",
        ]

        self.bearish_keywords = [
            "slowdown",
            "recession",
            "weakening",
            "contraction",
            "sink",
            "rout",
            "lower",
            "tensions",
            "escalating",
            "concerns",
            "misses",
            "below forecasts",
            "below expectations",
            "falls",
            "drops",
            "pessimism",
            "risk-off",
            "dovish",
            "deteriorated",
            "declines",
            "condemns",
            "stagflation",
        ]

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    def start(
        self,
    ) -> None:

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=(
                self._run_news_scraper
            ),
            daemon=True,
            name=(
                "PulseViper-NewsEngine"
            ),
        )

        self.thread.start()

        self.logger.info(
            (
                "News Intelligence "
                "Engine started."
            )
        )

    def stop(
        self,
    ) -> None:

        self.running = False

        thread = self.thread

        if (
            thread is not None
            and thread.is_alive()
        ):

            thread.join(
                timeout=1.0
            )

        self.thread = None

    def _run_news_scraper(
        self,
    ) -> None:

        while self.running:

            try:
                self.update_news_events()

            except Exception as exc:

                self.logger.error(
                    (
                        "Forex Factory "
                        "update failed: %s"
                    ),
                    exc,
                )

            try:
                self.update_news_sentiment()

            except Exception as exc:

                self.logger.error(
                    (
                        "News sentiment "
                        "update failed: %s"
                    ),
                    exc,
                )

            for _ in range(
                300
            ):

                if not self.running:
                    break

                time.sleep(
                    1
                )

    # =========================================================================
    # DISPLAY-ONLY SENTIMENT
    # =========================================================================

    def update_news_sentiment(
        self,
    ) -> None:
        """
        FXStreet headlines are advisory/display-only.

        They have ZERO execution-lock authority.
        """

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; PulseViper/1.0)"
            ),

            "Accept": (
                "application/rss+xml, "
                "application/xml, "
                "text/xml, */*"
            ),
        }

        try:
            response = requests.get(
                self.FXSTREET_RSS_URL,
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()

            root = ET.fromstring(
                response.content
            )

            headlines: List[
                Dict[str, str]
            ] = []

            for item in root.findall(
                ".//item"
            )[
                :20
            ]:

                title = item.find(
                    "title"
                )

                pub_date = item.find(
                    "pubDate"
                )

                title_text = (
                    (
                        title.text
                        or ""
                    ).strip()
                    if title
                    is not None
                    else ""
                )

                date_text = (
                    (
                        pub_date.text
                        or ""
                    ).strip()
                    if pub_date
                    is not None
                    else ""
                )

                if title_text:

                    headlines.append(
                        {
                            "title": (
                                title_text
                            ),

                            "date": (
                                date_text
                            ),
                        }
                    )

            with self.lock:

                self.news_headlines = (
                    headlines
                )

                self.current_sentiment = (
                    self.calculate_sentiment(
                        headlines
                    )
                )

        except Exception as exc:

            self.logger.warning(
                (
                    "FXStreet RSS "
                    "unavailable: %s"
                ),
                exc,
            )

    def calculate_sentiment(
        self,
        headlines: List[
            Dict
        ],
    ) -> float:

        score = 0.0
        analyzed_count = 0

        for item in headlines:

            title = str(
                item.get(
                    "title",
                    "",
                )
            ).lower()

            headline_score = (
                0.0
            )

            for word in (
                self.bullish_keywords
            ):

                if word in title:
                    headline_score += (
                        0.5
                    )

            for word in (
                self.bearish_keywords
            ):

                if word in title:
                    headline_score -= (
                        0.5
                    )

            if headline_score != 0.0:

                score += max(
                    -1.0,
                    min(
                        1.0,
                        headline_score,
                    ),
                )

                analyzed_count += 1

        if analyzed_count == 0:
            return 0.0

        return max(
            -1.0,
            min(
                1.0,
                (
                    score
                    / analyzed_count
                ),
            ),
        )

    def get_market_sentiment(
        self,
    ) -> float:

        with self.lock:

            return float(
                self.current_sentiment
            )

    # =========================================================================
    # NORMALIZATION
    # =========================================================================

    @staticmethod
    def _normalize_currency(
        value: Any,
    ) -> str:
        """
        Do NOT infer currency from event titles.

        Explicit US/USA country identifiers are normalized to USD because
        they represent the same United States event origin.
        """

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

        if raw in {
            "HOLIDAY",
            "BANK HOLIDAY",
        }:

            return "HOLIDAY"

        return raw

    @classmethod
    def _is_blocking_event(
        cls,
        event: Dict[
            str,
            Any,
        ],
    ) -> bool:
        """
        THE news-event blocker rule.

        Keep this deliberately boring and explicit.
        """

        currency = (
            cls._normalize_currency(
                event.get(
                    "currency",
                    event.get(
                        "country",
                        "",
                    ),
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

        return (
            currency == "USD"
            and impact == "HIGH"
        )

    # =========================================================================
    # FOREX FACTORY TIME PARSING
    # =========================================================================

    @staticmethod
    def _parse_date(
        date_text: str,
    ) -> Optional[
        datetime
    ]:

        value = str(
            date_text
            or ""
        ).strip()

        for fmt in (
            "%m-%d-%Y",
            "%m/%d/%Y",
            "%Y-%m-%d",
        ):

            try:

                return datetime.strptime(
                    value,
                    fmt,
                )

            except ValueError:
                continue

        return None

    @staticmethod
    def _parse_time(
        time_text: str,
    ) -> Optional[
        Tuple[
            int,
            int,
        ]
    ]:

        value = re.sub(
            r"\s+",
            "",
            str(
                time_text
                or ""
            )
            .strip()
            .lower(),
        )

        if not value:

            return None

        if value in {
            "allday",
            "tentative",
            "day1",
            "day2",
            "day3",
        }:

            return None

        for fmt in (
            "%I:%M%p",
            "%I%p",
            "%H:%M",
        ):

            try:

                parsed = datetime.strptime(
                    value,
                    fmt,
                )

                return (
                    parsed.hour,
                    parsed.minute,
                )

            except ValueError:
                continue

        return None

    @staticmethod
    def get_eastern_offset_hours(
        dt: datetime,
    ) -> int:
        """
        US Eastern offset for Forex Factory calendar timestamps.

        Returns:
            4 during EDT
            5 during EST
        """

        year = dt.year

        march_first = datetime(
            year,
            3,
            1,
        )

        second_sunday_march = (
            (
                6
                - march_first.weekday()
            )
            % 7
            + 8
        )

        dst_start = datetime(
            year,
            3,
            second_sunday_march,
            2,
        )

        november_first = datetime(
            year,
            11,
            1,
        )

        first_sunday_november = (
            (
                6
                - november_first.weekday()
            )
            % 7
            + 1
        )

        dst_end = datetime(
            year,
            11,
            first_sunday_november,
            2,
        )

        if (
            dst_start
            <= dt
            < dst_end
        ):

            return 4

        return 5

    def _event_datetime_utc(
        self,
        date_text: str,
        time_text: str,
    ) -> Optional[
        datetime
    ]:

        date_value = (
            self._parse_date(
                date_text
            )
        )

        time_value = (
            self._parse_time(
                time_text
            )
        )

        if (
            date_value
            is None
            or time_value
            is None
        ):

            return None

        hour, minute = (
            time_value
        )

        eastern_naive = datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            hour,
            minute,
        )

        offset_hours = (
            self.get_eastern_offset_hours(
                eastern_naive
            )
        )

        utc_naive = (
            eastern_naive
            + timedelta(
                hours=offset_hours
            )
        )

        return utc_naive.replace(
            tzinfo=timezone.utc
        )

    # =========================================================================
    # FOREX FACTORY PARSER
    # =========================================================================

    @staticmethod
    def _text(
        node: Optional[
            ET.Element
        ],
    ) -> str:

        if (
            node is None
            or node.text
            is None
        ):

            return ""

        return node.text.strip()

    def _parse_xml_feed_with_status(
        self,
        xml_content: bytes,
    ) -> Tuple[
        List[
            Dict[
                str,
                Any,
            ]
        ],
        bool,
    ]:

        try:

            root = ET.fromstring(
                xml_content
            )

        except ET.ParseError:

            return (
                [],
                False,
            )

        event_nodes = (
            root.findall(
                ".//event"
            )
        )

        if not event_nodes:

            return (
                [],
                False,
            )

        events: List[
            Dict[
                str,
                Any,
            ]
        ] = []

        for item in event_nodes:

            title_text = (
                self._text(
                    item.find(
                        "title"
                    )
                )
            )

            date_text = (
                self._text(
                    item.find(
                        "date"
                    )
                )
            )

            time_text = (
                self._text(
                    item.find(
                        "time"
                    )
                )
            )

            impact_text = (
                self._text(
                    item.find(
                        "impact"
                    )
                )
            )

            currency_text = (
                self._text(
                    item.find(
                        "currency"
                    )
                )
            )

            country_text = (
                self._text(
                    item.find(
                        "country"
                    )
                )
            )

            # Explicit feed field only.
            #
            # Never:
            #   infer USD because title contains "Fed"
            #   infer HIGH because title contains "CPI"
            explicit_currency = (
                currency_text
                or country_text
            )

            currency = (
                self._normalize_currency(
                    explicit_currency
                )
            )

            impact = (
                self._normalize_impact(
                    impact_text
                )
            )

            if (
                not title_text
                or not date_text
            ):

                continue

            event_time = (
                self._event_datetime_utc(
                    date_text,
                    time_text,
                )
            )

            event = {
                # Legacy/dashboard fields.
                "event": (
                    title_text
                ),

                "country": (
                    currency
                ),

                "impact": (
                    impact
                ),

                "date_iso": (
                    event_time
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                    if event_time
                    is not None
                    else None
                ),

                # Explicit policy fields.
                "currency": (
                    currency
                ),

                "source": (
                    self
                    .SOURCE_FOREX_FACTORY
                ),

                "scheduled": (
                    event_time
                    is not None
                ),

                "raw_date": (
                    date_text
                ),

                "raw_time": (
                    time_text
                ),
            }

            event[
                "execution_blocking_candidate"
            ] = (
                self._is_blocking_event(
                    event
                )
                and event_time
                is not None
            )

            events.append(
                event
            )

        # It is perfectly valid for a weekly feed to contain zero USD HIGH
        # events. Feed validity therefore depends on parseable event rows,
        # NOT on finding a blocking event.
        return (
            events,
            bool(
                events
            ),
        )

    def parse_xml_feed(
        self,
        xml_content: bytes,
    ) -> List[
        Dict
    ]:
        """
        Backward-compatible public parser.
        """

        (
            events,
            _,
        ) = (
            self._parse_xml_feed_with_status(
                xml_content
            )
        )

        return events

    # =========================================================================
    # LIVE UPDATE
    # =========================================================================

    def update_news_events(
        self,
    ) -> bool:
        """
        Fetch the real Forex Factory calendar.

        Failure never creates replacement events.
        """

        now = datetime.now(
            timezone.utc
        )

        with self.lock:

            self.last_live_attempt = (
                now
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; PulseViper/1.0)"
            ),

            "Accept": (
                "application/xml, "
                "text/xml, */*"
            ),

            "Cache-Control": (
                "no-cache"
            ),
        }

        try:

            response = requests.get(
                self.FOREX_FACTORY_URL,
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()

            (
                parsed_events,
                valid_feed,
            ) = (
                self._parse_xml_feed_with_status(
                    response.content
                )
            )

            if not valid_feed:

                raise ValueError(
                    (
                        "FOREX_FACTORY_"
                        "FEED_INVALID_OR_EMPTY"
                    )
                )

            success_time = (
                datetime.now(
                    timezone.utc
                )
            )

            with self.lock:

                self.events = (
                    parsed_events
                )

                self.last_live_success = (
                    success_time
                )

                self.last_live_error = (
                    None
                )

            blocking_count = sum(
                1
                for event
                in parsed_events
                if (
                    self._is_blocking_event(
                        event
                    )
                    and event.get(
                        "scheduled",
                        False,
                    )
                )
            )

            self.logger.info(
                (
                    "Forex Factory "
                    "calendar updated: "
                    "%d events, "
                    "%d USD HIGH."
                ),
                len(
                    parsed_events
                ),
                blocking_count,
            )

            return True

        except Exception as exc:

            with self.lock:

                self.last_live_error = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

            self.logger.warning(
                (
                    "Forex Factory "
                    "calendar unavailable; "
                    "NO synthetic fallback "
                    "events created: %s"
                ),
                exc,
            )

            return False

    # =========================================================================
    # EXECUTION LOCK HELPERS
    # =========================================================================

    @staticmethod
    def _normalize_utc(
        value: datetime,
    ) -> datetime:

        if value.tzinfo is None:

            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    @staticmethod
    def _parse_iso_utc(
        value: Any,
    ) -> Optional[
        datetime
    ]:

        if not value:

            return None

        text = str(
            value
        ).strip()

        try:

            if text.endswith(
                "Z"
            ):

                text = (
                    text[
                        :-1
                    ]
                    + "+00:00"
                )

            parsed = datetime.fromisoformat(
                text
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except ValueError:

            return None

    @staticmethod
    def _is_usd_sensitive_symbol(
        symbol: Optional[
            str
        ],
    ) -> bool:
        """
        Symbol filtering can only REMOVE a news lock.

        It can never make a non-USD event block trading.
        """

        if symbol is None:
            return True

        sym = re.sub(
            r"[^A-Z0-9]",
            "",
            str(
                symbol
            ).upper(),
        )

        if not sym:
            return True

        if (
            "XAU"
            in sym
            or "GOLD"
            in sym
        ):

            return True

        if "USD" in sym:

            return True

        crypto_bases = {
            "BTC",
            "ETH",
            "LTC",
            "XRP",
            "SOL",
            "DOGE",
            "ADA",
            "DOT",
            "AVAX",
            "MATIC",
            "BNB",
            "LINK",
        }

        if any(
            sym.startswith(
                base
            )
            for base
            in crypto_bases
        ):

            return False

        # Non-USD FX crosses do not need a USD calendar lock.
        return False

    def _calendar_is_stale(
        self,
        now_utc: datetime,
    ) -> bool:

        with self.lock:

            last_success = (
                self.last_live_success
            )

        if last_success is None:

            return True

        return (
            now_utc
            - last_success
        ) > self.staleness_threshold

    # =========================================================================
    # EXECUTION LOCK
    # =========================================================================

    def is_execution_locked(
        self,
        current_time_utc: datetime,
        lockout_mins: int = 30,
        cooldown_mins: int = 15,
        symbol: Optional[str] = None,
    ) -> Tuple[
        bool,
        Optional[str],
    ]:
        """
        News execution gate.

        LIVE LOCK CONDITION:

            event.currency == "USD"
            AND event.impact == "HIGH"
            AND current_time is inside pre/post window

        Manual schedule is checked only when explicitly enabled.
        """

        from utils.settings_manager import (
            settings_manager,
        )

        now_utc = (
            self._normalize_utc(
                current_time_utc
            )
        )

        if not bool(
            settings_manager.get(
                "news_filter_enabled",
                True,
            )
        ):

            return (
                False,
                None,
            )

        pre_minutes = max(
            0,
            int(
                lockout_mins
            ),
        )

        post_minutes = max(
            0,
            int(
                cooldown_mins
            ),
        )

        usd_sensitive = (
            self._is_usd_sensitive_symbol(
                symbol
            )
        )

        # -----------------------------------------------------------------
        # 1. MANUAL SCHEDULE
        #
        # Only if explicitly enabled.
        # -----------------------------------------------------------------

        if bool(
            settings_manager.get(
                "use_manual_news_schedule",
                False,
            )
        ):

            try:

                from core.news_schedule import (
                    news_schedule,
                )

                (
                    blocked,
                    reason,
                ) = (
                    news_schedule.is_blocked(
                        current_utc=(
                            now_utc
                        ),
                        pre_mins=(
                            pre_minutes
                        ),
                        post_mins=(
                            post_minutes
                        ),
                    )
                )

                if (
                    blocked
                    and usd_sensitive
                ):

                    return (
                        True,
                        reason,
                    )

            except Exception as exc:

                self.logger.error(
                    (
                        "Manual news "
                        "schedule error: %s"
                    ),
                    exc,
                )

                if bool(
                    settings_manager.get(
                        "strict_mode",
                        False,
                    )
                ):

                    return (
                        True,
                        (
                            "NEWS_MANUAL_"
                            "SCHEDULE_ERROR"
                        ),
                    )

        # -----------------------------------------------------------------
        # 2. LIVE FOREX FACTORY
        #
        # Only if explicitly enabled.
        # -----------------------------------------------------------------

        if not bool(
            settings_manager.get(
                "use_live_news_feed",
                False,
            )
        ):

            return (
                False,
                None,
            )

        # -----------------------------------------------------------------
        # 3. STALE FEED
        #
        # Do NOT use stale events.
        # Do NOT fabricate replacements.
        # -----------------------------------------------------------------

        if self._calendar_is_stale(
            now_utc
        ):

            if bool(
                settings_manager.get(
                    "strict_mode",
                    False,
                )
            ):

                return (
                    True,
                    "NEWS_CALENDAR_STALE",
                )

            return (
                False,
                None,
            )

        if not usd_sensitive:

            return (
                False,
                None,
            )

        with self.lock:

            events_snapshot = [
                dict(
                    event
                )
                for event
                in self.events
            ]

        # -----------------------------------------------------------------
        # 4. EXACT USD + HIGH RULE
        # -----------------------------------------------------------------

        for event in events_snapshot:

            if not self._is_blocking_event(
                event
            ):

                continue

            event_time = (
                self._parse_iso_utc(
                    event.get(
                        "date_iso"
                    )
                )
            )

            if event_time is None:

                continue

            block_start = (
                event_time
                - timedelta(
                    minutes=(
                        pre_minutes
                    )
                )
            )

            block_end = (
                event_time
                + timedelta(
                    minutes=(
                        post_minutes
                    )
                )
            )

            if (
                block_start
                <= now_utc
                <= block_end
            ):

                event_name = str(
                    event.get(
                        "event",
                        "USD HIGH Event",
                    )
                )

                return (
                    True,
                    (
                        "FOREX_FACTORY_USD_HIGH: "
                        f"{event_name} @ "
                        f"{event_time.isoformat().replace('+00:00', 'Z')}"
                    ),
                )

        return (
            False,
            None,
        )

    # =========================================================================
    # READ-ONLY STATUS
    # =========================================================================

    def get_events(
        self,
    ) -> List[
        Dict[
            str,
            Any,
        ]
    ]:

        with self.lock:

            return [
                dict(
                    event
                )
                for event
                in self.events
            ]

    def get_calendar_status(
        self,
    ) -> Dict[
        str,
        Any,
    ]:

        now = datetime.now(
            timezone.utc
        )

        with self.lock:

            events = [
                dict(
                    event
                )
                for event
                in self.events
            ]

            last_attempt = (
                self.last_live_attempt
            )

            last_success = (
                self.last_live_success
            )

            last_error = (
                self.last_live_error
            )

        return {
            "source": (
                self.SOURCE_FOREX_FACTORY
            ),

            "last_attempt_utc": (
                last_attempt.isoformat()
                if last_attempt
                is not None
                else None
            ),

            "last_success_utc": (
                last_success.isoformat()
                if last_success
                is not None
                else None
            ),

            "stale": (
                self._calendar_is_stale(
                    now
                )
            ),

            "last_error": (
                last_error
            ),

            "event_count": len(
                events
            ),

            "usd_high_event_count": sum(
                1
                for event
                in events
                if self._is_blocking_event(
                    event
                )
            ),

            "blocking_policy": (
                "USD_HIGH_ONLY"
            ),

            "synthetic_fallbacks": (
                False
            ),
        }

    # =========================================================================
    # LEGACY FALLBACK API
    # =========================================================================

    def _load_fallback_events(
        self,
    ) -> None:
        """
        Kept only so an old caller does not crash.

        Synthetic macro events are prohibited.
        """

        self.logger.warning(
            (
                "Synthetic news "
                "fallback requested "
                "but disabled."
            )
        )