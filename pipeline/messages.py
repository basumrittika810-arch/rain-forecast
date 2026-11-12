"""Display text for rainfall: shown amount, IMD category, message (decisions D-026, D-027). Standard library only.

Nothing here changes a stored value; it only describes the published `mm` (already 0 for adjusted values, D-008).
  * Shown amount: 1 decimal, halves rounded up; true zero "0 mm"; amounts that round to 0.0 "< 0.1 mm".
  * IMD category (SOP 2021 Table 1.5 / FAQ Q93) is taken from the ROUNDED number shown, so word and number agree.
    "Exceptionally heavy" is not used (needs station records). The partial first day gets a label too.
  * Timing: the parts of the day (IST) whose rain, rounded, is at least 0.1 mm. The forecast blocks start at 23:30,
    02:30, ... (3 h) or 23:30, 05:30, ... (6 h), so every block lies inside exactly one part. No time inside a block is implied.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

CATEGORY_SOURCE = ("Rain categories: India Meteorological Department (IMD), SOP Weather Forecasting and Warning "
                   "Services 2021, Table 1.5 (24-hour rainfall). Applied to the forecast amount shown.")
AREA_NOTE = ("Amounts are averages for an area about 27 km across around this place (ECMWF grid box), not for one "
             "exact spot. Rain at your exact location may be more or less.")

# (upper bound of the shown amount in mm, key, label); IMD Table 1.5, bands written to 1 decimal
_BANDS = [
    (Decimal("2.4"), "very_light", "Very light"),
    (Decimal("15.5"), "light", "Light"),
    (Decimal("64.4"), "moderate", "Moderate"),
    (Decimal("115.5"), "heavy", "Heavy"),
    (Decimal("204.4"), "very_heavy", "Very heavy"),
]
_PARTS = {"23:30": "night", "02:30": "night", "05:30": "morning", "08:30": "morning",
          "11:30": "afternoon", "14:30": "afternoon", "17:30": "evening", "20:30": "evening"}
_PART_ORDER = ["night", "morning", "afternoon", "evening"]


def _rounded(mm: float) -> Decimal:
    if mm < 0:
        raise ValueError(f"shown rainfall cannot be negative: {mm}")
    return Decimal(repr(mm)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def format_mm(mm: float | None) -> str | None:
    if mm is None:
        return None
    if mm == 0:
        return "0 mm"
    r = _rounded(mm)
    return "< 0.1 mm" if r == 0 else f"{r} mm"


def category(mm: float) -> tuple[str, str]:
    if mm == 0:
        return "no_rain", "No rain"
    r = _rounded(mm)   # a tiny amount rounds to 0.0: a trace, which IMD counts as very light
    for upper, key, label in _BANDS:
        if r <= upper:
            return key, label
    return "extremely_heavy", "Extremely heavy"   # >= 204.5 mm (SOP: "greater than or equal to 204.5 mm")


def part_of_day(start_iso: str) -> str:
    hhmm = dt.datetime.fromisoformat(start_iso).strftime("%H:%M")
    if hhmm not in _PARTS:
        raise ValueError(f"interval start {start_iso} is not on the 23:30 IST block grid")
    return _PARTS[hhmm]


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _join(parts: list[str]) -> str:
    """['afternoon', 'evening'] -> 'in the afternoon and evening'; ['night', 'evening'] -> 'at night and in the evening'."""
    day_parts = [p for p in parts if p != "night"]
    pieces = (["at night"] if "night" in parts else []) + (["in the " + _and(day_parts)] if day_parts else [])
    return " and ".join(pieces)


def describe_day(day: dict, intervals: list[dict]) -> dict:
    if day["status"] == "unavailable":
        return {"shown": None, "category": "unavailable", "label": "No forecast",
                "message": "No forecast available for this day."}
    mm = day["mm"]
    key, label = category(mm)
    shown = format_mm(mm)
    if key == "no_rain":
        return {"shown": shown, "category": key, "label": label, "message": "No rain expected."}
    sentence = f"{label} rain expected"
    if shown == "< 0.1 mm":
        return {"shown": shown, "category": key, "label": label, "message": sentence + " (less than 0.1 mm)."}
    start, end = dt.datetime.fromisoformat(day["start"]), dt.datetime.fromisoformat(day["end"])
    inside = [i for i in intervals
              if start <= dt.datetime.fromisoformat(i["start"]) and dt.datetime.fromisoformat(i["end"]) <= end]
    if any(i["status"] == "unavailable" for i in inside):
        return {"shown": shown, "category": key, "label": label,
                "message": sentence + ". Timing within the day is not available."}
    totals: dict[str, float] = {}
    for i in inside:
        part = part_of_day(i["start"])
        totals[part] = totals.get(part, 0.0) + i["mm"]
    rainy = [p for p in _PART_ORDER if p in totals and totals[p] > 0 and _rounded(totals[p]) >= Decimal("0.1")]
    all_parts = [p for p in _PART_ORDER if p in totals]
    if not rainy:
        when = ""
    elif rainy == all_parts and len(all_parts) == 4:
        when = ", through the day"
    else:
        when = ", " + _join(rainy)
    return {"shown": shown, "category": key, "label": label, "message": sentence + when + "."}
