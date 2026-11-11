"""Rainfall arithmetic for one location, from cumulative tp readings.

Inputs are plain dicts {step_hours: cumulative_rain} so every rule can be tested with small,
hand-checkable numbers. Verified facts this relies on (docs/DECISIONS.md D-004, D-007):
  * tp is in metres and accumulated from forecast start (startStep = 0) at every step;
  * steps are 0..144 every 3 h, then 150.. every 6 h.

Not implemented here (awaiting owner approval): deriving the negative-value threshold from
GRIB packing metadata. Functions below take the threshold as an argument.
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


def build_intervals(cum: dict, steps: list[int], threshold_mm=None) -> list[dict]:
    """One entry per consecutive pair of expected steps."""
    if any(b <= a for a, b in zip(steps, steps[1:])):
        raise ValueError(f"steps must be strictly increasing: {steps}")
    out = []
    for a, b in zip(steps, steps[1:]):
        raw = interval_rain(cum, a, b)
        mm, status = classify(raw, threshold_mm)
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


def build_days(cum: dict, periods: list[dict], threshold_mm=None) -> list[dict]:
    """Daily total = cumulative at period end - cumulative at period start (only the two boundaries)."""
    out = []
    for p in periods:
        raw = interval_rain(cum, p["start_step"], p["end_step"])
        mm, status = classify(raw, threshold_mm)
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
