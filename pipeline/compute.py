"""Rainfall arithmetic for one location, from cumulative tp readings.

Inputs are plain dicts {step_hours: cumulative_rain} so every rule can be tested with small,
hand-checkable numbers. Verified facts this relies on (docs/DECISIONS.md D-004, D-007):
  * tp is in metres and accumulated from forecast start (startStep = 0) at every step;
  * steps are 0..144 every 3 h, then 150.. every 6 h.

Negative-value threshold (D-015): for a difference between two readings with packing increments
q1 and q2, the threshold is (q1 + q2) / 2, the largest error two round-to-nearest readings can add up to.
Increments come from each message's own GRIB metadata (packing_increment_mm).
"""

import datetime as dt

MM_PER_M = 1000.0
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
DAY_BOUNDARY_UTC_HOUR = 18  # 18:00 UTC = 23:30 IST (decision D-006)


def m_to_mm(metres):
    """Convert metres of water to millimetres. Negative values are passed through unchanged."""
    return metres * MM_PER_M


def expected_steps(horizon_hours: int) -> list[int]:
    """HRES open-data steps up to the horizon: every 3 h to 144 h, then every 6 h."""
    return list(range(0, min(horizon_hours, 144) + 1, 3)) + list(range(150, horizon_hours + 1, 6))


def packing_increment_mm(binary_scale_factor: int, decimal_scale_factor: int, bits_per_value: int) -> float:
    """Spacing between representable values of one GRIB message, in mm.

    Decoded value = (R + k * 2^E) / 10^D metres, so neighbouring values differ by 2^E / 10^D metres.
    A constant field (bitsPerValue = 0) stores no rounded values at all, so its increment is 0.
    """
    for name, v in (("binary_scale_factor", binary_scale_factor), ("decimal_scale_factor", decimal_scale_factor),
                    ("bits_per_value", bits_per_value)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{name} must be an integer, got {v!r}")
    if bits_per_value < 0:
        raise ValueError(f"bits_per_value must be >= 0, got {bits_per_value}")
    if bits_per_value == 0:
        return 0.0
    return MM_PER_M * 2.0 ** binary_scale_factor / 10.0 ** decimal_scale_factor


def negative_threshold_mm(q1_mm: float, q2_mm: float) -> float:
    """Largest negative difference attributable to rounding of two readings: (q1 + q2) / 2 (D-015)."""
    if q1_mm < 0 or q2_mm < 0:
        raise ValueError(f"increments must be >= 0, got {q1_mm}, {q2_mm}")
    return (q1_mm + q2_mm) / 2


def _pair_threshold(increments, a: int, b: int):
    if increments is None:
        return None
    missing = [s for s in (a, b) if s not in increments]
    if missing:
        raise ValueError(f"no packing increment for step(s) {missing}")
    return negative_threshold_mm(increments[a], increments[b])


def interval_rain(cum: dict, start_step: int, end_step: int):
    """Rain between two readings = later cumulative - earlier cumulative. None if either is missing."""
    if start_step not in cum or end_step not in cum:
        return None
    return cum[end_step] - cum[start_step]


def classify(raw_mm, threshold_mm):
    """Apply decision D-008. Returns (display_mm, status).

    raw >= 0                  -> (raw, "ok")
    -threshold <= raw < 0     -> (0.0, "adjusted")   raw value is kept separately by the caller
    raw < -threshold          -> (None, "invalid")   blocks publication
    raw is None               -> (None, "unavailable")
    """
    if raw_mm is None:
        return None, "unavailable"
    if raw_mm >= 0:
        return raw_mm, "ok"
    if threshold_mm is None:
        raise ValueError(f"negative value {raw_mm} but no threshold was provided")
    if raw_mm >= -threshold_mm:
        return 0.0, "adjusted"
    return None, "invalid"


def rate_mm_per_h(mm, hours: int):
    """Average rate over the interval's actual duration. None if the amount is unavailable."""
    if mm is None:
        return None
    return mm / hours


def _missing_reason(cum: dict, *steps: int) -> str:
    return "missing step " + ", ".join(f"{s} h" for s in steps if s not in cum)


def build_intervals(cum: dict, steps: list[int], increments: dict | None = None) -> list[dict]:
    """One entry per consecutive pair of expected steps.

    increments: {step: packing increment in mm}. Required as soon as any difference is negative.
    """
    if any(b <= a for a, b in zip(steps, steps[1:])):
        raise ValueError(f"steps must be strictly increasing: {steps}")
    out = []
    for a, b in zip(steps, steps[1:]):
        raw = interval_rain(cum, a, b)
        threshold = _pair_threshold(increments, a, b) if raw is not None and raw < 0 else None
        mm, status = classify(raw, threshold)
        entry = {"start_step": a, "end_step": b, "hours": b - a, "raw_mm": raw, "mm": mm,
                 "mm_per_h": rate_mm_per_h(mm, b - a), "status": status}
        if status == "unavailable":
            entry["reason"] = _missing_reason(cum, a, b)
        out.append(entry)
    return out


def daily_periods(init_utc: dt.datetime, horizon_hours: int) -> list[dict]:
    """Daily periods ending at 23:30 IST (18 UTC). The first runs from forecast start and may be partial.

    Only periods that end within the horizon are returned.
    """
    if init_utc.tzinfo is None:
        raise ValueError("init_utc must be timezone-aware")
    first_end = (DAY_BOUNDARY_UTC_HOUR - init_utc.astimezone(dt.timezone.utc).hour) % 24 or 24
    bounds = [0] + list(range(first_end, horizon_hours + 1, 24))
    periods = []
    for a, b in zip(bounds, bounds[1:]):
        start_ist = (init_utc + dt.timedelta(hours=a)).astimezone(IST)
        end_ist = (init_utc + dt.timedelta(hours=b)).astimezone(IST)
        periods.append({"start_step": a, "end_step": b, "hours": b - a, "partial": (b - a) != 24,
                        "date": end_ist.date(), "start_ist": start_ist, "end_ist": end_ist})
    return periods


def build_days(cum: dict, periods: list[dict], increments: dict | None = None) -> list[dict]:
    """Daily total = cumulative at period end - cumulative at period start (only the two boundaries)."""
    out = []
    for p in periods:
        raw = interval_rain(cum, p["start_step"], p["end_step"])
        threshold = (_pair_threshold(increments, p["start_step"], p["end_step"])
                     if raw is not None and raw < 0 else None)
        mm, status = classify(raw, threshold)
        entry = {**p, "raw_mm": raw, "mm": mm, "status": status}
        if status == "unavailable":
            entry["reason"] = _missing_reason(cum, p["start_step"], p["end_step"])
        out.append(entry)
    return out


def days_not_matching_intervals(days: list[dict], intervals: list[dict]) -> list:
    """Dates whose raw total differs from the sum of their intervals' raw values (exact comparison).

    Days with any unavailable interval, or that are themselves unavailable, are skipped.
    Exact comparison is valid because GRIB values are exact binary multiples (D-007 telescoping check).
    """
    bad = []
    for d in days:
        if d["raw_mm"] is None:
            continue
        parts = [i for i in intervals if d["start_step"] <= i["start_step"] and i["end_step"] <= d["end_step"]]
        if any(i["raw_mm"] is None for i in parts):
            continue
        if sum(i["raw_mm"] for i in parts) != d["raw_mm"]:
            bad.append(d["date"])
    return bad


def assert_publishable(statuses) -> None:
    """Raise if any value is invalid (D-008: such a forecast must not be published)."""
    n = sum(1 for s in statuses if s == "invalid")
    if n:
        raise ValueError(f"{n} invalid value(s): negative difference beyond threshold; not publishable")
