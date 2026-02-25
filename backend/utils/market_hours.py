"""
Market Hours Utility
====================
Point 5: Strict US/Eastern market hours enforcement.

- Market open:  Mon-Fri, 9:30 AM – 4:00 PM ET
- Pre-market bookend:  9:25 AM ET (capture gap-ups/downs)
- Post-market bookend: 4:05 PM ET (official mark-to-market close)
- Override:  Set FORCE_MARKET_OPEN=1 env var for dev/testing
"""

import os
import logging
from datetime import datetime, time, timedelta

import pytz
import holidays

logger = logging.getLogger(__name__)

# US/Eastern timezone — handles EST/EDT transitions automatically
EASTERN = pytz.timezone('US/Eastern')

# Market hours (standard equity options)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Bookend snapshot times
PRE_MARKET_BOOKEND = time(9, 25)
POST_MARKET_BOOKEND = time(16, 5)

# NYSE holiday calendar — computes algorithmically, no maintenance needed
NYSE_HOLIDAYS = holidays.NYSE()


def now_eastern() -> datetime:
    """Get current time in US/Eastern timezone."""
    return datetime.now(EASTERN)


def is_market_open() -> bool:
    """Check if the market is currently open.

    Returns True if:
      - FORCE_MARKET_OPEN env var is set (dev/testing override), OR
      - It is Mon-Fri, 9:30 AM – 4:00 PM ET, and NOT a holiday

    Returns:
        bool: True if market is open or forced open.
    """
    # Dev/testing override
    if os.getenv('FORCE_MARKET_OPEN'):
        return True

    now = now_eastern()

    # Weekend check (Mon=0, Sun=6)
    if now.weekday() > 4:
        return False

    # Holiday check (NYSE observed holidays)
    if now.date() in NYSE_HOLIDAYS:
        return False

    # Time window check
    current_time = now.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def is_market_holiday() -> bool:
    """Check if today is a US market holiday (NYSE calendar)."""
    return now_eastern().date() in NYSE_HOLIDAYS


def is_weekday() -> bool:
    """Check if today is a weekday (Mon-Fri) in US/Eastern."""
    return now_eastern().weekday() <= 4


def get_market_status() -> dict:
    """Get detailed market status for logging and UI display.

    Returns:
        dict with keys: is_open, current_time_et, day, forced, holiday
    """
    now = now_eastern()
    forced = bool(os.getenv('FORCE_MARKET_OPEN'))
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    return {
        'is_open': is_market_open(),
        'current_time_et': now.strftime('%H:%M:%S'),
        'day': days[now.weekday()],
        'forced': forced,
        'holiday': is_market_holiday(),
    }


def seconds_until_market_open() -> float:
    """Calculate seconds until next market open.

    Useful for scheduling the first cron job of the day.

    Returns:
        Seconds until next 9:30 AM ET.  Returns 0 if market is currently open.
    """
    if is_market_open():
        return 0.0

    now = now_eastern()
    today_open = now.replace(
        hour=MARKET_OPEN.hour,
        minute=MARKET_OPEN.minute,
        second=0,
        microsecond=0,
    )

    if now < today_open and now.weekday() <= 4:
        # Today is a weekday and we're before open
        return (today_open - now).total_seconds()
    else:
        # Advance to next weekday
        days_ahead = 1
        next_day = now + timedelta(days=days_ahead)
        while next_day.weekday() > 4:
            days_ahead += 1
            next_day = now + timedelta(days=days_ahead)

        next_open = next_day.replace(
            hour=MARKET_OPEN.hour,
            minute=MARKET_OPEN.minute,
            second=0,
            microsecond=0,
        )
        return (next_open - now).total_seconds()


def get_todays_market_close_utc() -> datetime:
    """Get today's market close (4:00 PM ET) as a UTC datetime.

    Used by the smart after-hours guard to check if a post-close
    snapshot has already been taken today.
    """
    now_et = now_eastern()
    close_et = now_et.replace(
        hour=MARKET_CLOSE.hour,
        minute=MARKET_CLOSE.minute,
        second=0,
        microsecond=0,
    )
    return close_et.astimezone(pytz.utc).replace(tzinfo=None)
