from datetime import datetime, time

from api import business_hours


def test_is_within_business_hours_standard_weekday():
    # Wednesday 10:00 AM UTC (Open)
    wed_open = datetime(2026, 10, 14, 10, 0, 0)
    assert business_hours.is_within_business_hours(wed_open) is True

    # Wednesday 08:59 AM UTC (Closed, before open)
    wed_early = datetime(2026, 10, 14, 8, 59, 0)
    assert business_hours.is_within_business_hours(wed_early) is False

    # Wednesday 18:00 PM UTC (Closed, at boundary)
    wed_closed = datetime(2026, 10, 14, 18, 0, 0)
    assert business_hours.is_within_business_hours(wed_closed) is False

    # Wednesday 20:00 PM UTC (Closed, after hours)
    wed_night = datetime(2026, 10, 14, 20, 0, 0)
    assert business_hours.is_within_business_hours(wed_night) is False


def test_is_within_business_hours_weekend():
    # Saturday (Closed all day)
    sat = datetime(2026, 10, 17, 12, 0, 0)
    assert business_hours.is_within_business_hours(sat) is False

    # Sunday (Closed all day)
    sun = datetime(2026, 10, 18, 12, 0, 0)
    assert business_hours.is_within_business_hours(sun) is False


def test_get_next_business_window_start():
    # Already open -> returns self
    wed_open = datetime(2026, 10, 14, 10, 30, 0)
    assert business_hours.get_next_business_window_start(wed_open) == wed_open

    # Early morning on weekday -> jumps to 09:00 same day
    wed_early = datetime(2026, 10, 14, 6, 15, 0)
    expected_open = datetime(2026, 10, 14, 9, 0, 0)
    assert business_hours.get_next_business_window_start(wed_early) == expected_open

    # Evening on Thursday -> jumps to Friday 09:00
    thu_late = datetime(2026, 10, 15, 19, 45, 0)
    expected_fri = datetime(2026, 10, 16, 9, 0, 0)
    assert business_hours.get_next_business_window_start(thu_late) == expected_fri

    # Friday night -> jumps over weekend to Monday 09:00
    fri_late = datetime(2026, 10, 16, 21, 0, 0)
    expected_mon = datetime(2026, 10, 19, 9, 0, 0)
    assert business_hours.get_next_business_window_start(fri_late) == expected_mon

    # Saturday afternoon -> jumps to Monday 09:00
    sat_afternoon = datetime(2026, 10, 17, 14, 0, 0)
    assert business_hours.get_next_business_window_start(sat_afternoon) == expected_mon


def test_add_business_minutes_same_day():
    start = datetime(2026, 10, 14, 10, 0, 0)
    # Add 45 minutes
    res = business_hours.add_business_minutes(start, 45)
    assert res == datetime(2026, 10, 14, 10, 45, 0)

    # 0 or negative minutes returns start
    assert business_hours.add_business_minutes(start, 0) == start
    assert business_hours.add_business_minutes(start, -10) == start


def test_add_business_minutes_crosses_evening_and_weekend():
    # Thursday 17:00 (1 hour / 60m left before 18:00 close)
    thu_start = datetime(2026, 10, 15, 17, 0, 0)
    # Add 120 minutes: 60m used Thursday until 18:00, remaining 60m resumes Friday at 09:00 -> 10:00
    res_fri = business_hours.add_business_minutes(thu_start, 120)
    assert res_fri == datetime(2026, 10, 16, 10, 0, 0)

    # Friday 17:30 (30m left before 18:00 close)
    fri_start = datetime(2026, 10, 16, 17, 30, 0)
    # Add 90 minutes: 30m used Friday until 18:00, remaining 60m resumes Monday at 09:00 -> 10:00
    res_mon = business_hours.add_business_minutes(fri_start, 90)
    assert res_mon == datetime(2026, 10, 19, 10, 0, 0)

    # Start on Saturday (Closed) with 60m target
    sat_start = datetime(2026, 10, 17, 11, 0, 0)
    res_sat = business_hours.add_business_minutes(sat_start, 60)
    # Starts Monday 09:00 + 60m -> Monday 10:00
    assert res_sat == datetime(2026, 10, 19, 10, 0, 0)


def test_calculate_business_minutes_between():
    # Same day within window: 10:00 to 12:30 = 150 minutes
    t1 = datetime(2026, 10, 14, 10, 0, 0)
    t2 = datetime(2026, 10, 14, 12, 30, 0)
    expected_same_day = 150
    assert business_hours.calculate_business_minutes_between(t1, t2) == expected_same_day

    # End <= Start returns 0
    assert business_hours.calculate_business_minutes_between(t2, t1) == 0

    # Across night: Thursday 16:00 to Friday 11:00
    # Thursday: 16:00 to 18:00 = 120m
    # Friday: 09:00 to 11:00 = 120m
    # Total = 240m
    t_thu = datetime(2026, 10, 15, 16, 0, 0)
    t_fri = datetime(2026, 10, 16, 11, 0, 0)
    expected_across_night = 240
    assert business_hours.calculate_business_minutes_between(t_thu, t_fri) == expected_across_night

    # Across weekend: Friday 17:00 to Monday 10:00
    # Friday: 17:00 to 18:00 = 60m
    # Saturday & Sunday: 0m
    # Monday: 09:00 to 10:00 = 60m
    # Total = 120m
    t_fri_eve = datetime(2026, 10, 16, 17, 0, 0)
    t_mon_morn = datetime(2026, 10, 19, 10, 0, 0)
    expected_across_weekend = 120
    assert business_hours.calculate_business_minutes_between(t_fri_eve, t_mon_morn) == (
        expected_across_weekend
    )


def test_get_business_hours_status():
    # Inside business hours
    dt_open = datetime(2026, 10, 14, 14, 0, 0)
    status_open = business_hours.get_business_hours_status(dt_open)
    assert status_open["is_open"] is True
    assert status_open["next_open_at"] is None
    assert status_open["schedule"]["monday"] == "09:00 - 18:00"
    assert status_open["schedule"]["saturday"] == "Closed"

    # Outside business hours (Sunday)
    dt_closed = datetime(2026, 10, 18, 14, 0, 0)
    status_closed = business_hours.get_business_hours_status(dt_closed)
    assert status_closed["is_open"] is False
    assert status_closed["next_open_at"] == "2026-10-19T09:00:00"


def test_custom_schedule_support():
    # Custom schedule: Monday to Saturday 08:00 - 20:00
    custom_sched: dict[int, tuple[time, time] | None] = {
        0: (time(8, 0), time(20, 0)),
        1: (time(8, 0), time(20, 0)),
        2: (time(8, 0), time(20, 0)),
        3: (time(8, 0), time(20, 0)),
        4: (time(8, 0), time(20, 0)),
        5: (time(8, 0), time(20, 0)),
        6: None,
    }

    # Saturday 15:00 is open in custom schedule
    sat_time = datetime(2026, 10, 17, 15, 0, 0)
    assert business_hours.is_within_business_hours(sat_time, custom_sched) is True
