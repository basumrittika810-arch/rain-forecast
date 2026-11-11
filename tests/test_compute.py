"""Tests for the rainfall arithmetic (pipeline/compute.py), using small artificial datasets.

All expected values are worked out by hand in the comments, independently of the code.
Rain amounts are chosen as exact binary fractions of a metre (e.g. 0.0078125 m = 7.8125 mm), so the
computer stores them exactly and results can be compared with ==, like the real GRIB values
(which are exact multiples of 2^E m).
"""

import datetime as dt

import pytest

from pipeline.compute import (
    assert_publishable,
    build_days,
    build_intervals,
    classify,
    days_not_matching_intervals,
    daily_periods,
    expected_steps,
    interval_rain,
    m_to_mm,
    negative_threshold_mm,
    packing_increment_mm,
    rate_mm_per_h,
)

INIT = dt.datetime(2026, 11, 11, 0, 0, tzinfo=dt.timezone.utc)  # a 00 UTC run = 05:30 IST
STEPS = expected_steps(258)


def dataset_a():
    """Cumulative rain (metres) since forecast start, for one location.

    Rain falls only in four slots: 21->24 h: 0.0078125 m, 42->45 h: 0.015625 m,
    144->150 h: 0.03125 m, 252->258 h: 0.0625 m.  So the running total is:
      steps 0..21   : 0
      steps 24..42  : 0.0078125
      steps 45..144 : 0.0234375
      steps 150..252: 0.0546875
      step  258     : 0.1171875
    """
    def total(step):
        t = 0.0
        if step >= 24:
            t += 0.0078125
        if step >= 45:
            t += 0.015625
        if step >= 150:
            t += 0.03125
        if step >= 258:
            t += 0.0625
        return t
    return {s: m_to_mm(total(s)) for s in STEPS}  # in mm from here on


# ---------------------------------------------------------------- 0. step schedule

def test_expected_steps_match_verified_server_schedule():
    # Verified on the server (D-007): 0..144 every 3 h (49 steps) + 150..258 every 6 h (19 steps) = 68.
    assert len(STEPS) == 68
    assert STEPS[:3] == [0, 3, 6]
    assert STEPS[47:51] == [141, 144, 150, 156]
    assert STEPS[-3:] == [246, 252, 258]
    assert 147 not in STEPS


# ---------------------------------------------------------------- 1. rain between two readings

def test_rain_between_two_readings_is_later_minus_earlier():
    # Real values from run 2026-11-11 00z, Bay of Bengal 12.5N 83.25E (D-004 / demo output):
    # 0-144 h = 0.60498046875 m, 0-150 h = 0.64404296875 m  ->  0.0390625 m fell in 144->150 h.
    cum = {144: 0.60498046875, 150: 0.64404296875}
    assert interval_rain(cum, 144, 150) == 0.0390625


def test_rain_between_readings_unavailable_if_a_reading_is_missing():
    # Never fill a gap: if either reading is missing, the answer is None (not 0).
    assert interval_rain({144: 0.6}, 144, 150) is None
    assert interval_rain({150: 0.6}, 144, 150) is None


# ---------------------------------------------------------------- 2. metres -> millimetres

@pytest.mark.parametrize("metres, mm", [
    (0.0, 0.0),
    (0.0390625, 39.0625),            # exact binary fraction -> exact result
    (0.00006103515625, 0.06103515625),  # one packing increment (2^-14 m)
    (-0.00006103515625, -0.06103515625),  # negatives are NOT changed by conversion
])
def test_metres_to_mm_exact(metres, mm):
    assert m_to_mm(metres) == mm


def test_metres_to_mm_decimal_value():
    # 0.025 m is not an exact binary fraction, so compare with a tiny tolerance.
    assert m_to_mm(0.025) == pytest.approx(25.0, abs=1e-12)


# ---------------------------------------------------------------- 3. 3-hour and 6-hour intervals

def test_intervals_count_durations_and_values():
    iv = build_intervals(dataset_a(), STEPS)
    assert len(iv) == 67                                    # 68 readings -> 67 gaps
    assert [i["hours"] for i in iv].count(3) == 48          # 0->3 ... 141->144
    assert [i["hours"] for i in iv].count(6) == 19          # 144->150 ... 252->258
    nonzero = {(i["start_step"], i["end_step"]): i["raw_mm"] for i in iv if i["raw_mm"] != 0}
    assert nonzero == {(21, 24): 7.8125, (42, 45): 15.625, (144, 150): 31.25, (252, 258): 62.5}


def test_first_six_hour_interval_is_144_to_150():
    iv = build_intervals(dataset_a(), STEPS)
    i = next(x for x in iv if x["start_step"] == 144)
    assert (i["end_step"], i["hours"]) == (150, 6)


def test_rate_uses_actual_interval_duration():
    # 31.25 mm over 6 h = 5.208333 mm/h; the same amount over 3 h would be 10.416667 mm/h.
    assert rate_mm_per_h(31.25, 6) == pytest.approx(31.25 / 6)
    assert rate_mm_per_h(31.25, 3) == pytest.approx(31.25 / 3)
    assert rate_mm_per_h(None, 6) is None


def test_intervals_reject_unordered_steps():
    with pytest.raises(ValueError):
        build_intervals({0: 0.0, 6: 0.0, 3: 0.0}, [0, 6, 3])


# ---------------------------------------------------------------- 4. daily totals, 23:30 IST

def test_daily_periods_for_00z_run():
    p = daily_periods(INIT, horizon_hours=258)
    assert len(p) == 11
    # Day 1: forecast start 05:30 IST -> 23:30 IST, 18 h, partial.
    assert (p[0]["start_step"], p[0]["end_step"], p[0]["hours"], p[0]["partial"]) == (0, 18, 18, True)
    assert p[0]["date"] == dt.date(2026, 11, 11)
    assert p[0]["start_ist"].isoformat() == "2026-11-11T05:30:00+05:30"
    assert p[0]["end_ist"].isoformat() == "2026-11-11T23:30:00+05:30"
    # Day 2: 11 Nov 23:30 -> 12 Nov 23:30 IST = steps 18 -> 42, labelled 12 Nov.
    assert (p[1]["start_step"], p[1]["end_step"], p[1]["partial"]) == (18, 42, False)
    assert p[1]["date"] == dt.date(2026, 11, 12)
    # Last day: steps 234 -> 258 = 20 Nov 23:30 -> 21 Nov 23:30 IST, labelled 21 Nov.
    assert (p[-1]["start_step"], p[-1]["end_step"]) == (234, 258)
    assert p[-1]["date"] == dt.date(2026, 11, 21)
    assert p[-1]["end_ist"].isoformat() == "2026-11-21T23:30:00+05:30"
    # Only the first period is partial; the others are 24 h.
    assert [d["hours"] for d in p[1:]] == [24] * 10


def test_daily_totals_dataset_a():
    days = build_days(dataset_a(), daily_periods(INIT, 258))
    got = {d["date"].isoformat(): d["raw_mm"] for d in days}
    assert got == {
        "2026-11-11": 0.0,       # 05:30-23:30 IST, no rain
        "2026-11-12": 7.8125,    # 21->24 h = 12 Nov 02:30-05:30 IST, inside 18->42 h (11 Nov 23:30 -> 12 Nov 23:30)
        "2026-11-13": 15.625,    # 42->45 h = 12 Nov 23:30 -> 13 Nov 02:30 IST -> belongs to 13 Nov
        "2026-11-14": 0.0, "2026-11-15": 0.0, "2026-11-16": 0.0,
        "2026-11-17": 31.25,     # 144->150 h lies inside 138->162 h (16 Nov 23:30 -> 17 Nov 23:30 IST)
        "2026-11-18": 0.0, "2026-11-19": 0.0, "2026-11-20": 0.0,
        "2026-11-21": 62.5,      # 252->258 h lies inside 234->258 h
    }
    assert sum(got.values()) == 117.1875   # total of all four slots


def test_rain_just_after_2330_counts_for_next_date():
    # 42->45 h starts exactly at the 23:30 IST boundary of 12 Nov, so it must count for 13 Nov, not 12 Nov.
    days = {d["date"].isoformat(): d["raw_mm"] for d in build_days(dataset_a(), daily_periods(INIT, 258))}
    assert days["2026-11-12"] == 7.8125 and days["2026-11-13"] == 15.625


# ---------------------------------------------------------------- 5a. missing data

def test_missing_boundary_step_makes_both_adjacent_days_unavailable():
    cum = dataset_a()
    del cum[42]                               # boundary between 12 Nov and 13 Nov
    days = {d["date"].isoformat(): d for d in build_days(cum, daily_periods(INIT, 258))}
    for date in ("2026-11-12", "2026-11-13"):
        assert days[date]["raw_mm"] is None   # never 0
        assert days[date]["status"] == "unavailable"
        assert "42" in days[date]["reason"]
    # all other days are unaffected
    assert days["2026-11-17"]["raw_mm"] == 31.25 and days["2026-11-17"]["status"] == "ok"
    assert sum(1 for d in days.values() if d["status"] == "unavailable") == 2


def test_missing_intermediate_step_affects_only_its_two_intervals():
    cum = dataset_a()
    del cum[30]                               # not a day boundary
    days = build_days(cum, daily_periods(INIT, 258))
    assert all(d["status"] == "ok" for d in days)
    assert next(d for d in days if d["date"] == dt.date(2026, 11, 12))["raw_mm"] == 7.8125
    iv = build_intervals(cum, STEPS)
    bad = [(i["start_step"], i["end_step"]) for i in iv if i["status"] == "unavailable"]
    assert bad == [(27, 30), (30, 33)]
    assert all(i["raw_mm"] is None for i in iv if i["status"] == "unavailable")


# ---------------------------------------------------------------- 5b. negative differences
# The threshold is passed in. HOW it is derived from GRIB metadata is not implemented yet
# (awaiting owner approval). One packing increment at E = -14 is 2^-14 m = 0.06103515625 mm.

ONE_INC = 0.06103515625


def test_positive_and_zero_are_ok_unchanged():
    assert classify(7.8125, ONE_INC) == (7.8125, "ok")
    assert classify(0.0, ONE_INC) == (0.0, "ok")


def test_small_negative_within_threshold_is_shown_as_zero_and_flagged():
    assert classify(-ONE_INC, ONE_INC) == (0.0, "adjusted")          # exactly one step: allowed
    assert classify(-ONE_INC / 2, ONE_INC) == (0.0, "adjusted")


def test_negative_beyond_threshold_is_invalid():
    assert classify(-2 * ONE_INC, ONE_INC) == (None, "invalid")      # two steps: not allowed
    assert classify(-0.25, 0.1220703125) == (None, "invalid")


def test_missing_value_is_unavailable_not_zero():
    assert classify(None, ONE_INC) == (None, "unavailable")


# Increments as in the real run (D-014): E=-14 for steps 3-6, -13 for 9-129, -12 for 132-258.
FINE, MID, COARSE = 0.06103515625, 0.1220703125, 0.244140625
# Step 0 is a constant field (bitsPerValue = 0): its values are exact, so its increment is 0.
REAL_INCREMENTS = {s: (0.0 if s == 0 else FINE if s <= 6 else MID if s <= 129 else COARSE) for s in STEPS}


def test_raw_negative_is_kept_while_display_is_zero():
    # Dataset B: reading drops by one fine increment between 6 h and 9 h (seen in real data, D-007).
    cum = {s: 0.0 for s in STEPS}
    cum[6] = FINE
    iv = {(i["start_step"], i["end_step"]): i for i in build_intervals(cum, STEPS, increments=REAL_INCREMENTS)}
    i = iv[(6, 9)]
    assert (i["raw_mm"], i["mm"], i["status"], i["mm_per_h"]) == (-FINE, 0.0, "adjusted", 0.0)


def test_invalid_value_blocks_publication():
    cum = {s: 0.0 for s in STEPS}
    cum[6] = 3 * FINE                         # drops by three fine steps at 6 -> 9 h
    iv = build_intervals(cum, STEPS, increments=REAL_INCREMENTS)
    assert [i["status"] for i in iv].count("invalid") == 1
    with pytest.raises(ValueError, match="invalid"):
        assert_publishable([i["status"] for i in iv])


# ---------------------------------------------------------------- 5c. threshold from GRIB precision (D-015)

@pytest.mark.parametrize("E, D, bits, expected_mm", [
    (-14, 0, 12, 0.06103515625),   # 2^-14 m = 0.06103515625 mm
    (-13, 0, 12, 0.1220703125),    # 2^-13 m
    (-12, 0, 12, 0.244140625),     # 2^-12 m
    (0, 1, 12, 100.0),             # 2^0 m / 10^1 = 0.1 m = 100 mm (decimal scaling)
    (0, 0, 0, 0.0),                # constant field (real step 0): exact values, no rounding
])
def test_packing_increment_from_metadata(E, D, bits, expected_mm):
    assert packing_increment_mm(E, D, bits) == expected_mm


@pytest.mark.parametrize("q1, q2, expected", [
    (FINE, FINE, FINE),                # same increment -> that increment
    (FINE, MID, 0.091552734375),       # (0.06103515625 + 0.1220703125) / 2, worked by hand
    (MID, COARSE, 0.18310546875),      # (0.1220703125 + 0.244140625) / 2
    (COARSE, COARSE, COARSE),
])
def test_threshold_is_mean_of_the_two_increments(q1, q2, expected):
    assert negative_threshold_mm(q1, q2) == expected
    assert negative_threshold_mm(q2, q1) == expected   # order does not matter


def test_threshold_with_an_exact_constant_field():
    # 0 -> 3 h: step 0 exact (0), step 3 rounded to FINE -> max error FINE/2.
    assert negative_threshold_mm(0.0, FINE) == 0.030517578125
    assert negative_threshold_mm(0.0, 0.0) == 0.0     # two exact fields: no negative is acceptable


def test_threshold_rejects_negative_increments():
    with pytest.raises(ValueError):
        negative_threshold_mm(-FINE, FINE)


def test_constant_first_field_does_not_allow_large_dips():
    cum = {s: 0.0 for s in STEPS}
    cum[0] = 1.0                        # impossible: 1 mm at the start, then 0 at 3 h (dip of 1 mm)
    iv = {(i["start_step"], i["end_step"]): i for i in build_intervals(cum, STEPS, increments=REAL_INCREMENTS)}
    assert iv[(0, 3)]["status"] == "invalid"


def test_transition_pair_one_fine_step_allowed_two_blocked():
    # 6 -> 9 h: increments FINE -> MID, threshold 0.0915527...
    cum = {s: 0.0 for s in STEPS}
    cum[6] = FINE                       # dip of 1 fine step (0.061) -> allowed
    iv = {(i["start_step"], i["end_step"]): i for i in build_intervals(cum, STEPS, increments=REAL_INCREMENTS)}
    assert iv[(6, 9)]["status"] == "adjusted"
    cum[6] = 2 * FINE                   # dip of 0.122 > 0.0915 -> blocked
    iv = {(i["start_step"], i["end_step"]): i for i in build_intervals(cum, STEPS, increments=REAL_INCREMENTS)}
    assert iv[(6, 9)]["status"] == "invalid"


def test_same_increment_pair_exactly_one_step_allowed():
    # 246 -> 252 h: both COARSE, threshold = 0.244140625 (inclusive); real data had dips of exactly this size.
    cum = {s: 0.0 for s in STEPS}
    for s in STEPS:
        if s <= 246:
            cum[s] = COARSE if s >= 132 else 0.0
    iv = {(i["start_step"], i["end_step"]): i for i in build_intervals(cum, STEPS, increments=REAL_INCREMENTS)}
    assert (iv[(246, 252)]["raw_mm"], iv[(246, 252)]["status"]) == (-COARSE, "adjusted")


def test_real_daily_dip_is_adjusted():
    # Real example (D-014): 13.50N 79.75E, day 114 -> 138 h (16 Nov):
    # 3.2958984375 mm (27 x MID) -> 3.173828125 mm (13 x COARSE): dip 0.1220703125 <= threshold 0.18310546875.
    cum = {s: 0.0 for s in STEPS}
    for s in STEPS:
        if 114 <= s < 138:
            cum[s] = 3.2958984375
        elif s >= 138:
            cum[s] = 3.173828125
    days = {d["date"].isoformat(): d for d in build_days(cum, daily_periods(INIT, 258), increments=REAL_INCREMENTS)}
    d = days["2026-11-16"]
    assert (d["raw_mm"], d["mm"], d["status"]) == (-0.1220703125, 0.0, "adjusted")


def test_negative_without_increments_is_an_error_not_a_guess():
    cum = {s: 0.0 for s in STEPS}
    cum[6] = FINE
    with pytest.raises(ValueError):
        build_intervals(cum, STEPS)          # no increments given -> must not silently pick a threshold


def test_ok_adjusted_and_unavailable_do_not_block_publication():
    assert_publishable(["ok", "adjusted", "unavailable", "ok"])   # must not raise


# ---------------------------------------------------------------- 6. days agree with their intervals

def test_every_day_equals_the_sum_of_its_intervals():
    cum = dataset_a()
    days = build_days(cum, daily_periods(INIT, 258))
    iv = build_intervals(cum, STEPS)
    assert days_not_matching_intervals(days, iv) == []


def test_tampered_interval_is_detected():
    cum = dataset_a()
    days = build_days(cum, daily_periods(INIT, 258))
    iv = build_intervals(cum, STEPS)
    for i in iv:
        if (i["start_step"], i["end_step"]) == (144, 150):
            i["raw_mm"] += 0.5                # simulate a calculation error
    assert days_not_matching_intervals(days, iv) == [dt.date(2026, 11, 17)]


def test_days_with_unavailable_intervals_are_not_compared():
    cum = dataset_a()
    del cum[30]                               # intervals 27->30, 30->33 unavailable; day 12 Nov still known
    days = build_days(cum, daily_periods(INIT, 258))
    iv = build_intervals(cum, STEPS)
    assert days_not_matching_intervals(days, iv) == []   # 12 Nov is skipped, not reported as a mismatch
