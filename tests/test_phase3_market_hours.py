"""
Phase 3 Regression Tests: Market Hours Utility
===============================================
Tests T-MH-01 through T-MH-08

Pure unit tests — no database required.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, time
from unittest.mock import patch

passed = 0
failed = 0
total = 0


def test(test_id, description, func):
    global passed, failed, total
    total += 1
    try:
        func()
        print(f"  PASS {test_id}: {description}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {test_id}: {description}")
        print(f"     Error: {e}")
        failed += 1


print("\n" + "=" * 60)
print("Phase 3 Tests: Market Hours Utility")
print("=" * 60 + "\n")


# =========================================================================
# T-MH-01: Module imports successfully
# =========================================================================
def t_mh_01():
    from backend.utils.market_hours import (
        is_market_open, now_eastern, get_market_status,
        is_weekday, seconds_until_market_open,
        MARKET_OPEN, MARKET_CLOSE, PRE_MARKET_BOOKEND, POST_MARKET_BOOKEND,
    )
    assert callable(is_market_open)
    assert callable(now_eastern)
    assert callable(get_market_status)

test("T-MH-01", "market_hours module imports all symbols", t_mh_01)


# =========================================================================
# T-MH-02: Constants are correct times (9:30, 16:00, 9:25, 16:05)
# =========================================================================
def t_mh_02():
    from backend.utils.market_hours import (
        MARKET_OPEN, MARKET_CLOSE, PRE_MARKET_BOOKEND, POST_MARKET_BOOKEND,
    )
    assert MARKET_OPEN == time(9, 30), f"Expected 09:30, got {MARKET_OPEN}"
    assert MARKET_CLOSE == time(16, 0), f"Expected 16:00, got {MARKET_CLOSE}"
    assert PRE_MARKET_BOOKEND == time(9, 25), f"Expected 09:25, got {PRE_MARKET_BOOKEND}"
    assert POST_MARKET_BOOKEND == time(16, 5), f"Expected 16:05, got {POST_MARKET_BOOKEND}"

test("T-MH-02", "Constants: 9:30 open, 16:00 close, 9:25/16:05 bookends", t_mh_02)


# =========================================================================
# T-MH-03: is_market_open() returns True during market hours (Wed 11:00 ET)
# =========================================================================
def t_mh_03():
    import pytz
    from backend.utils.market_hours import is_market_open

    eastern = pytz.timezone('US/Eastern')
    # Wednesday Feb 18, 2026 at 11:00 AM ET (market should be open)
    mock_now = eastern.localize(datetime(2026, 2, 18, 11, 0, 0))

    with patch('backend.utils.market_hours.now_eastern', return_value=mock_now):
        result = is_market_open()
    assert result is True, f"Expected True (Wed 11:00 ET), got {result}"

test("T-MH-03", "is_market_open() = True during Wed 11:00 ET", t_mh_03)


# =========================================================================
# T-MH-04: is_market_open() returns False before 9:30 AM ET
# =========================================================================
def t_mh_04():
    import pytz
    from backend.utils.market_hours import is_market_open

    eastern = pytz.timezone('US/Eastern')
    # Wednesday at 8:00 AM ET (before market open)
    mock_now = eastern.localize(datetime(2026, 2, 18, 8, 0, 0))

    with patch('backend.utils.market_hours.now_eastern', return_value=mock_now):
        result = is_market_open()
    assert result is False, f"Expected False (8:00 AM pre-market), got {result}"

test("T-MH-04", "is_market_open() = False before 9:30 AM ET", t_mh_04)


# =========================================================================
# T-MH-05: is_market_open() returns False after 4:00 PM ET
# =========================================================================
def t_mh_05():
    import pytz
    from backend.utils.market_hours import is_market_open

    eastern = pytz.timezone('US/Eastern')
    # Wednesday at 4:30 PM ET (after market close)
    mock_now = eastern.localize(datetime(2026, 2, 18, 16, 30, 0))

    with patch('backend.utils.market_hours.now_eastern', return_value=mock_now):
        result = is_market_open()
    assert result is False, f"Expected False (4:30 PM post-market), got {result}"

test("T-MH-05", "is_market_open() = False after 4:00 PM ET", t_mh_05)


# =========================================================================
# T-MH-06: is_market_open() returns False on Saturday
# =========================================================================
def t_mh_06():
    import pytz
    from backend.utils.market_hours import is_market_open

    eastern = pytz.timezone('US/Eastern')
    # Saturday Feb 21, 2026 at 11:00 AM ET (weekend)
    mock_now = eastern.localize(datetime(2026, 2, 21, 11, 0, 0))

    with patch('backend.utils.market_hours.now_eastern', return_value=mock_now):
        result = is_market_open()
    assert result is False, f"Expected False (Saturday), got {result}"

test("T-MH-06", "is_market_open() = False on Saturday", t_mh_06)


# =========================================================================
# T-MH-07: FORCE_MARKET_OPEN env var overrides to True
# =========================================================================
def t_mh_07():
    import pytz
    from backend.utils.market_hours import is_market_open

    eastern = pytz.timezone('US/Eastern')
    # Saturday at 2:00 AM ET — would normally be False
    mock_now = eastern.localize(datetime(2026, 2, 21, 2, 0, 0))

    with patch('backend.utils.market_hours.now_eastern', return_value=mock_now):
        with patch.dict(os.environ, {'FORCE_MARKET_OPEN': '1'}):
            result = is_market_open()
    assert result is True, f"Expected True (FORCE_MARKET_OPEN=1), got {result}"

test("T-MH-07", "FORCE_MARKET_OPEN=1 overrides to True on Saturday", t_mh_07)


# =========================================================================
# T-MH-08: get_market_status() returns expected keys
# =========================================================================
def t_mh_08():
    from backend.utils.market_hours import get_market_status

    status = get_market_status()
    assert isinstance(status, dict), f"Expected dict, got {type(status)}"

    expected_keys = {'is_open', 'current_time_et', 'day'}
    actual_keys = set(status.keys())
    missing = expected_keys - actual_keys
    assert not missing, f"Missing keys: {missing}. Got: {actual_keys}"

    assert isinstance(status['is_open'], bool), f"is_open should be bool"
    assert isinstance(status['current_time_et'], str), f"current_time_et should be str"

test("T-MH-08", "get_market_status() returns dict with is_open, label, time_et", t_mh_08)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*60}")
print(f"Market Hours Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
