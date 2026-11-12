"""Display text for rainfall (decisions D-026, D-027): shown amount, IMD category label, message, timing within the day.

IMD categories (mm per 24 h; SOP 2021 Table 1.5 / FAQ Q93): very light trace-2.4, light 2.5-15.5, moderate 15.6-64.4,
heavy 64.5-115.5, very heavy 115.6-204.4, extremely heavy >= 204.5. The label is taken from the ROUNDED number shown
(1 decimal, halves up), so word and number always agree. True zero shows "0 mm"; tiny amounts show "< 0.1 mm".
"""

import pytest

from pipeline.messages import AREA_NOTE, CATEGORY_SOURCE, category, describe_day, format_mm, part_of_day

# ---------------------------------------------------------------- shown amount


@pytest.mark.parametrize("mm, shown", [
    (0.0, "0 mm"),             # true zero
    (0.03, "< 0.1 mm"),        # tiny, would round to 0.0
    (0.0499, "< 0.1 mm"),
    (0.05, "0.1 mm"),          # halves go up
    (0.06103515625, "0.1 mm"),
    (2.44, "2.4 mm"),
    (2.45, "2.5 mm"),
    (18.0, "18.0 mm"),
    (11.962890625, "12.0 mm"),
    (204.45, "204.5 mm"),
])
def test_format_mm(mm, shown):
    assert format_mm(mm) == shown


def test_format_mm_missing_and_negative():
    assert format_mm(None) is None
    with pytest.raises(ValueError):
        format_mm(-0.1)        # shown values are never negative (D-008 adjusts them to 0 before this point)


# ---------------------------------------------------------------- IMD category from the shown number

@pytest.mark.parametrize("mm, key, label", [
    (0.0, "no_rain", "No rain"),
    (0.03, "very_light", "Very light"),          # "< 0.1 mm" is a trace: IMD very light = Trace - 2.4
    (0.05, "very_light", "Very light"),
    (2.4, "very_light", "Very light"),
    (2.44, "very_light", "Very light"),          # shown 2.4
    (2.45, "light", "Light"),                    # shown 2.5
    (2.5, "light", "Light"),
    (15.5, "light", "Light"),
    (15.54, "light", "Light"),                   # shown 15.5
    (15.55, "moderate", "Moderate"),             # shown 15.6
    (64.4, "moderate", "Moderate"),
    (64.45, "heavy", "Heavy"),                   # shown 64.5
    (115.5, "heavy", "Heavy"),
    (115.55, "very_heavy", "Very heavy"),        # shown 115.6
    (204.4, "very_heavy", "Very heavy"),
    (204.44, "very_heavy", "Very heavy"),        # shown 204.4
    (204.45, "extremely_heavy", "Extremely heavy"),   # shown 204.5
    (204.5, "extremely_heavy", "Extremely heavy"),    # SOP: "greater than or equal to 204.5 mm"
    (500.0, "extremely_heavy", "Extremely heavy"),
])
def test_category_from_shown_number(mm, key, label):
    assert category(mm) == (key, label)


def test_no_exceptionally_heavy_category():
    assert category(1000.0)[0] == "extremely_heavy"


# ---------------------------------------------------------------- part of the day (IST)

@pytest.mark.parametrize("start, part", [
    ("2026-11-11T23:30+05:30", "night"), ("2026-11-12T02:30+05:30", "night"),
    ("2026-11-12T05:30+05:30", "morning"), ("2026-11-12T08:30+05:30", "morning"),
    ("2026-11-12T11:30+05:30", "afternoon"), ("2026-11-12T14:30+05:30", "afternoon"),
    ("2026-11-12T17:30+05:30", "evening"), ("2026-11-12T20:30+05:30", "evening"),
])
def test_part_of_day(start, part):
    assert part_of_day(start) == part


def test_part_of_day_rejects_other_start_times():
    with pytest.raises(ValueError):
        part_of_day("2026-11-12T06:00+05:30")


# ---------------------------------------------------------------- whole day

FULL_STARTS = ["2026-11-11T23:30", "2026-11-12T02:30", "2026-11-12T05:30", "2026-11-12T08:30",
               "2026-11-12T11:30", "2026-11-12T14:30", "2026-11-12T17:30", "2026-11-12T20:30"]


def iv(start, mm, hours=3, status="ok"):
    from datetime import datetime, timedelta
    end = (datetime.fromisoformat(start) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
    return {"start": start + "+05:30", "end": end + "+05:30", "hours": hours, "mm": mm,
            "raw_mm": mm, "status": status}


def day(mm, status="ok", start="2026-11-11T23:30", end="2026-11-12T23:30", hours=24, partial=False):
    return {"date": end[:10], "start": start + "+05:30", "end": end + "+05:30", "hours": hours, "partial": partial,
            "mm": mm, "raw_mm": mm, "status": status}


def full_day(values):
    return day(sum(values)), [iv(s, v) for s, v in zip(FULL_STARTS, values)]


def test_dry_day():
    d, ivs = full_day([0.0] * 8)
    assert describe_day(d, ivs) == {"shown": "0 mm", "category": "no_rain", "label": "No rain",
                                    "message": "No rain expected."}


def test_rain_in_afternoon_and_evening():
    d, ivs = full_day([0, 0, 0, 0, 1.0, 2.0, 3.0, 0.5])           # 6.5 mm
    assert describe_day(d, ivs) == {"shown": "6.5 mm", "category": "light", "label": "Light",
                                    "message": "Light rain expected, in the afternoon and evening."}


def test_rain_in_one_part():
    d, ivs = full_day([10.0, 10.0, 0, 0, 0, 0, 0, 0])
    assert describe_day(d, ivs)["message"] == "Moderate rain expected, at night."


def test_rain_through_the_day():
    d, ivs = full_day([1.0] * 8)
    assert describe_day(d, ivs)["message"] == "Light rain expected, through the day."


def test_part_needs_at_least_shown_0_1_mm():
    # morning 0.04 mm (shown "< 0.1 mm") does not count as a rainy part; evening 0.05 (shown 0.1) does
    d, ivs = full_day([0, 0, 0.02, 0.02, 0, 0, 0.05, 0])
    r = describe_day(d, ivs)
    assert (r["shown"], r["label"], r["message"]) == ("0.1 mm", "Very light", "Very light rain expected, in the evening.")


def test_tiny_day_has_no_timing():
    d, ivs = full_day([0, 0, 0.01, 0, 0, 0.02, 0, 0])
    assert describe_day(d, ivs) == {"shown": "< 0.1 mm", "category": "very_light", "label": "Very light",
                                    "message": "Very light rain expected (less than 0.1 mm)."}


def test_six_hour_intervals():
    starts = ["2026-11-19T23:30", "2026-11-20T05:30", "2026-11-20T11:30", "2026-11-20T17:30"]
    d = day(20.0, start="2026-11-19T23:30", end="2026-11-20T23:30")
    ivs = [iv(s, v, hours=6) for s, v in zip(starts, [0, 15.0, 5.0, 0])]
    assert describe_day(d, ivs)["message"] == "Moderate rain expected, in the morning and afternoon."


def test_partial_first_day_gets_label():
    starts = FULL_STARTS[2:]                                     # 05:30 -> 23:30, 18 h
    d = day(3.0, start="2026-11-12T05:30", hours=18, partial=True)
    ivs = [iv(s, v) for s, v in zip(starts, [0, 0, 0, 0, 1.0, 2.0])]
    assert describe_day(d, ivs) == {"shown": "3.0 mm", "category": "light", "label": "Light",
                                    "message": "Light rain expected, in the evening."}


def test_adjusted_day_is_no_rain():
    d, ivs = full_day([0.0] * 8)
    d.update(status="adjusted", mm=0.0, raw_mm=-0.12)
    assert describe_day(d, ivs)["label"] == "No rain"


def test_unavailable_day():
    d, ivs = full_day([0.0] * 8)
    d.update(status="unavailable", mm=None, raw_mm=None, reason="missing step 18")
    assert describe_day(d, ivs) == {"shown": None, "category": "unavailable", "label": "No forecast",
                                    "message": "No forecast available for this day."}


def test_day_with_unavailable_interval_says_timing_unknown():
    d, ivs = full_day([0, 0, 0, 0, 1.0, 2.0, 3.0, 0.5])
    ivs[1].update(status="unavailable", mm=None, raw_mm=None)
    assert describe_day(d, ivs)["message"] == "Light rain expected. Timing within the day is not available."


def test_intervals_from_other_days_are_ignored():
    d, ivs = full_day([0, 0, 0, 0, 0, 0, 0, 3.0])               # 3.0 mm = IMD light (first draft said 2.0: very light)
    neighbour = iv("2026-11-12T23:30", 50.0)                    # next day's first interval
    assert describe_day(d, ivs + [neighbour])["message"] == "Light rain expected, in the evening."


def test_notes_are_cited():
    assert "27 km" in AREA_NOTE and "exact" in AREA_NOTE
    assert "IMD" in CATEGORY_SOURCE
