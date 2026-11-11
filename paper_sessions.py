"""Published cash-equity closures used to identify the paper entry session."""

from datetime import timedelta

import pandas as pd


# MM-DD, full closures only. Early closes are still sessions. Do not infer a
# closure from a missing price bar. Keep these dated lists current.
_MARKETS = {
    # https://www.nyse.com/trade/hours-calendars and Nasdaq US holiday schedule.
    # 2025 includes the Jan 9 national day of mourning announced by both venues.
    "": ("America/New_York", {
        2025: "01-01 01-09 01-20 02-17 04-18 05-26 06-19 07-04 09-01 11-27 12-25",
        2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
        2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
        2028: "01-17 02-21 04-14 05-29 06-19 07-04 09-04 11-23 12-25",
    }),
    # https://www.londonstockexchange.com/en/resources/markets-products/business-days
    ".L": ("Europe/London", {
        2026: "01-01 04-03 04-06 05-04 05-25 08-31 12-25 12-28",
        2027: "01-01 03-26 03-29 05-03 05-31 08-30 12-27 12-28",
        2028: "01-03 04-14 04-17 05-01 05-29 08-28 12-25 12-26",
    }),
    # https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours
    ".DE": ("Europe/Berlin", {
        2026: "01-01 04-03 04-06 05-01 12-24 12-25 12-31",
        2027: "01-01 03-26 03-29 12-24 12-31",
        2028: "04-14 04-17 05-01 12-25 12-26",
    }),
    # GPW resolutions 753/2025 and 754/2025.
    # https://www.gpw.pl/pub/GPW/uchwaly/2025/753_2025.pdf
    # https://www.gpw.pl/pub/GPW/uchwaly/2025/754_2025.pdf
    ".WA": ("Europe/Warsaw", {
        2026: "01-01 01-06 04-03 04-06 05-01 06-04 11-11 12-24 12-25 12-31",
        2027: "01-01 01-06 03-26 03-29 05-03 05-27 11-01 11-11 12-24 12-31",
    }),
    # https://www.tase.co.il/en/content/knowledge_center/trading_vacation_schedule
    # The 2026 schedule starts Monday Jan 5; Jan 1 was still a Thursday session.
    ".TA": ("Asia/Jerusalem", {
        2026: "03-03 04-01 04-02 04-07 04-08 04-21 04-22 05-21 05-22 07-23 09-11 09-18 09-21 09-25 10-02 10-27",
        2027: "03-23 04-21 04-22 04-27 04-28 05-11 05-12 06-10 06-11 08-12 10-01 10-08 10-11 10-15 10-22",
        2028: "03-10 04-10 04-11 04-17 05-01 05-02 05-30 05-31 08-01 09-20 09-21 09-22 09-29 10-04 10-05 10-11 10-12",
    }),
}


def next_paper_session(ticker, selected_at, now):
    """Expected next regular session and local as-of day, independent of bars."""
    symbol = ticker.upper()
    suffix = "." + symbol.rsplit(".", 1)[-1] if "." in symbol else ""
    if suffix not in _MARKETS:
        return None, None
    zone, closures = _MARKETS[suffix]
    selected = pd.Timestamp(selected_at)
    if selected.tzinfo is None:
        selected = selected.tz_localize("UTC")
    day = selected.tz_convert(zone).date()
    local_today = now.tz_convert(zone).date()
    for _ in range(10):
        day += timedelta(days=1)
        if day.year not in closures:
            break
        if day.weekday() >= 5 or day.isoformat()[5:] in closures[day.year].split():
            continue
        if suffix == ".TA" and day.isoformat() == "2026-01-02":
            continue  # Last Friday before the switch to Mon–Fri trading.
        return day, local_today
    return None, local_today
