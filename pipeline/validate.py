"""Validate a downloaded tp GRIB run against the verified data rules (D-004, D-007, D-014).

All problems are collected and reported together; any problem rejects the run.
"""

import datetime as dt
import math
from collections import Counter
from pathlib import Path

import eccodes
import numpy as np

from pipeline.compute import packing_increment_mm

# Real HRES 0.25 deg open-data grid, as observed in every verified message.
REAL_GRID = {
    "gridType": "regular_ll",
    "Ni": 1440, "Nj": 721,
    "latitudeOfFirstGridPointInDegrees": 90.0, "longitudeOfFirstGridPointInDegrees": 180.0,
    "latitudeOfLastGridPointInDegrees": -90.0, "longitudeOfLastGridPointInDegrees": 179.75,
    "iDirectionIncrementInDegrees": 0.25, "jDirectionIncrementInDegrees": 0.25,
}
# Packing types whose decoding is value = (R + k * 2^E) / 10^D, the basis of the negative threshold.
ALLOWED_PACKING = {"grid_ccsds", "grid_simple"}


class ValidationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("run rejected:\n  " + "\n  ".join(problems))


def _dt(date: int, time: int) -> dt.datetime:
    return dt.datetime.strptime(f"{date}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=dt.timezone.utc)


def _check_message(gid, run_init, grid, problems, seen, increments, stats):
    def get(key):
        try:
            return eccodes.codes_get(gid, key)
        except eccodes.KeyValueNotFoundError:
            problems.append(f"message {len(seen) + 1}: key {key} missing")
            return None

    step = get("endStep")
    if step is None:
        return
    step = int(step)
    seen.append(step)
    p = f"step {step}:"

    if (get("shortName"), get("paramId")) != ("tp", 228):
        problems.append(f"{p} shortName/paramId {get('shortName')}/{get('paramId')}, expected tp/228")
    if get("units") != "m":
        problems.append(f"{p} units {get('units')!r}, expected 'm'")
    if (get("stepType"), get("productDefinitionTemplateNumber"), get("typeOfStatisticalProcessing")) != ("accum", 8, 1):
        problems.append(f"{p} not an accumulation (stepType/template/processing = {get('stepType')}/"
                        f"{get('productDefinitionTemplateNumber')}/{get('typeOfStatisticalProcessing')})")
    if get("stepUnits") != 1:
        problems.append(f"{p} stepUnits {get('stepUnits')}, expected 1 (hours)")
    if get("startStep") != 0:
        problems.append(f"{p} startStep {get('startStep')}, expected 0 (accumulation from forecast start)")

    init = _dt(get("dataDate"), get("dataTime"))
    if init != run_init:
        problems.append(f"{p} initialisation {init:%Y-%m-%d %H:%M}, expected {run_init:%Y-%m-%d %H:%M} UTC")
    valid = _dt(get("validityDate"), get("validityTime"))
    if valid != run_init + dt.timedelta(hours=step):
        problems.append(f"{p} validity {valid:%Y-%m-%d %H:%M}, expected init + {step} h")

    bad_grid = {k: get(k) for k, v in grid.items() if get(k) != v}
    if bad_grid:
        problems.append(f"{p} grid differs from expected: {bad_grid}")

    packing = get("packingType")
    if packing not in ALLOWED_PACKING:
        problems.append(f"{p} packing {packing!r} not in {sorted(ALLOWED_PACKING)}")
    if get("bitmapPresent") != 0 or get("numberOfMissing") != 0:
        problems.append(f"{p} missing values present (bitmapPresent={get('bitmapPresent')}, "
                        f"numberOfMissing={get('numberOfMissing')})")

    values = eccodes.codes_get_values(gid)
    if not np.all(np.isfinite(values)):
        problems.append(f"{p} non-finite values")
    elif values.min() < 0:
        problems.append(f"{p} negative stored value(s): min {values.min()} m")
    else:
        stats["min"] = min(stats["min"], float(values.min()))
        stats["max"] = max(stats["max"], float(values.max()))
    increments[step] = packing_increment_mm(get("binaryScaleFactor"), get("decimalScaleFactor"),
                                            get("bitsPerValue"))


def _scan(path, run_init, grid, problems, seen, increments, stats) -> int:
    """Read every message. Always returns normally, so the file handle is released before the caller raises.

    (ecCodes passes the file to C via a duplicated handle that closes only when the Python file object
    is freed; if an exception escaped from here, its traceback would keep the file open, and Windows
    would then refuse to move the folder. Found by test_incomplete/corrupt_download_* tests.)
    """
    count = 0
    try:
        with open(path, "rb") as f:
            while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
                count += 1
                try:
                    _check_message(gid, run_init, grid, problems, seen, increments, stats)
                finally:
                    eccodes.codes_release(gid)
    except eccodes.CodesInternalError as e:   # corrupt or truncated GRIB
        problems.append(f"file unreadable after {count} message(s): {type(e).__name__}: {e}")
    return count


def validate_run_file(path: Path, run_init: dt.datetime, expected_steps: list[int], grid: dict = REAL_GRID) -> dict:
    """Return a report dict if the file is a complete, valid run; raise ValidationError otherwise."""
    problems, seen, increments = [], [], {}
    stats = {"min": math.inf, "max": -math.inf}
    count = _scan(path, run_init, grid, problems, seen, increments, stats)

    if count == 0 and not problems:
        problems.append("no GRIB messages in file")
    if count:
        c = Counter(seen)
        missing = sorted(set(expected_steps) - set(seen))
        extra = sorted(set(seen) - set(expected_steps))
        dups = sorted(s for s, n in c.items() if n > 1)
        if missing:
            problems.append(f"missing steps: {missing}")
        if extra:
            problems.append(f"unexpected steps: {extra}")
        if dups:
            problems.append(f"duplicate steps: {dups}")
    if problems:
        raise ValidationError(problems)
    return {"run_init_utc": run_init.isoformat(), "message_count": count, "steps": sorted(seen),
            "increments_mm": {s: increments[s] for s in sorted(increments)},
            "min_value_m": stats["min"], "max_value_m": stats["max"]}
