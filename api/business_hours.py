import calendar
from datetime import datetime, time, timedelta
from typing import Any

WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

DEFAULT_BUSINESS_START = time(9, 0)
DEFAULT_BUSINESS_END = time(18, 0)

# Default schedule: Monday (0) through Friday (4) from 09:00 to 18:00
DEFAULT_WEEKLY_SCHEDULE: dict[int, tuple[time, time] | None] = {
    0: (DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END),
    1: (DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END),
    2: (DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END),
    3: (DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END),
    4: (DEFAULT_BUSINESS_START, DEFAULT_BUSINESS_END),
    5: None,  # Saturday: Closed
    6: None,  # Sunday: Closed
}


def is_within_business_hours(
    dt: datetime,
    schedule: dict[int, tuple[time, time] | None] | None = None,
) -> bool:
    """Check if a timestamp falls within operating business hours."""
    sched = schedule if schedule is not None else DEFAULT_WEEKLY_SCHEDULE
    window = sched.get(dt.weekday())
    if window is None:
        return False
    start_t, end_t = window
    current_t = dt.time()
    return start_t <= current_t < end_t


def get_next_business_window_start(
    dt: datetime,
    schedule: dict[int, tuple[time, time] | None] | None = None,
) -> datetime:
    """Return dt if within business hours, or jump forward to the start of the next open window."""
    sched = schedule if schedule is not None else DEFAULT_WEEKLY_SCHEDULE
    if is_within_business_hours(dt, sched):
        return dt

    current = dt.replace(microsecond=0)
    for _ in range(14):  # scan up to two weeks ahead
        window = sched.get(current.weekday())
        if window is not None:
            start_t, end_t = window
            day_open = current.replace(
                hour=start_t.hour,
                minute=start_t.minute,
                second=start_t.second,
                microsecond=0,
            )
            day_close = current.replace(
                hour=end_t.hour,
                minute=end_t.minute,
                second=end_t.second,
                microsecond=0,
            )
            if current < day_open:
                return day_open
            if current < day_close:
                return current

        # Advance to next day at 00:00
        current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return dt


def add_business_minutes(
    start_dt: datetime,
    minutes: int,
    schedule: dict[int, tuple[time, time] | None] | None = None,
) -> datetime:
    """Add a number of business minutes to start_dt, respecting weekends and closed hours."""
    if minutes <= 0:
        return start_dt

    sched = schedule if schedule is not None else DEFAULT_WEEKLY_SCHEDULE
    curr = get_next_business_window_start(start_dt, sched)
    remaining_minutes = minutes

    max_steps = 1000  # safety bounded iteration
    step = 0

    while remaining_minutes > 0 and step < max_steps:
        step += 1
        window = sched.get(curr.weekday())
        if window is None:
            curr = get_next_business_window_start(curr, sched)
            continue

        start_t, end_t = window
        day_close = curr.replace(
            hour=end_t.hour,
            minute=end_t.minute,
            second=end_t.second,
            microsecond=0,
        )

        minutes_until_close = int((day_close - curr).total_seconds() // 60)
        if minutes_until_close <= 0:
            curr = get_next_business_window_start(curr + timedelta(minutes=1), sched)
            continue

        if remaining_minutes <= minutes_until_close:
            curr = curr + timedelta(minutes=remaining_minutes)
            remaining_minutes = 0
            break

        remaining_minutes -= minutes_until_close
        # Advance past close to find next window start
        curr = get_next_business_window_start(day_close + timedelta(minutes=1), sched)

    return curr


def calculate_business_minutes_between(
    start_dt: datetime,
    end_dt: datetime,
    schedule: dict[int, tuple[time, time] | None] | None = None,
) -> int:
    """Calculate the total business minutes elapsed between start_dt and end_dt."""
    if end_dt <= start_dt:
        return 0

    sched = schedule if schedule is not None else DEFAULT_WEEKLY_SCHEDULE
    curr = get_next_business_window_start(start_dt, sched)
    total_minutes = 0
    max_steps = 1000
    step = 0

    while curr < end_dt and step < max_steps:
        step += 1
        window = sched.get(curr.weekday())
        if window is None:
            curr = get_next_business_window_start(curr, sched)
            continue

        _, end_t = window
        day_close = curr.replace(
            hour=end_t.hour,
            minute=end_t.minute,
            second=end_t.second,
            microsecond=0,
        )

        slice_end = min(end_dt, day_close)
        if slice_end > curr:
            mins = int((slice_end - curr).total_seconds() // 60)
            total_minutes += max(0, mins)

        if slice_end >= day_close:
            curr = get_next_business_window_start(day_close + timedelta(minutes=1), sched)
        else:
            break

    return total_minutes


def get_business_hours_status(
    current_time: datetime | None = None,
    schedule: dict[int, tuple[time, time] | None] | None = None,
) -> dict[str, Any]:
    """Return current operating state, open/closed flag, next open time, and weekly schedule."""
    dt = current_time if current_time is not None else datetime.utcnow()
    sched = schedule if schedule is not None else DEFAULT_WEEKLY_SCHEDULE
    is_open = is_within_business_hours(dt, sched)

    next_open_dt: datetime | None = None
    if not is_open:
        next_open_dt = get_next_business_window_start(dt, sched)

    schedule_summary: dict[str, str] = {}
    for day_idx, day_name in enumerate(WEEKDAY_NAMES):
        w = sched.get(day_idx)
        if w is None:
            schedule_summary[day_name] = "Closed"
        else:
            s_str = f"{w[0].hour:02d}:{w[0].minute:02d}"
            e_str = f"{w[1].hour:02d}:{w[1].minute:02d}"
            schedule_summary[day_name] = f"{s_str} - {e_str}"

    return {
        "is_open": is_open,
        "current_time": dt.isoformat(),
        "next_open_at": next_open_dt.isoformat() if next_open_dt else None,
        "timezone": "UTC",
        "schedule": schedule_summary,
        "day_name": calendar.day_name[dt.weekday()],
    }
