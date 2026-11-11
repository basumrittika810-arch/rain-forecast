"""Step 2 of the pipeline: compute rainfall for the region, build the J1 JSON, check it, publish safely.

Publishing = write data/processed/<run>.json, then atomically replace data/processed/latest.json.
Nothing is written unless every check passes; the previous latest.json is otherwise left untouched.

Usage:  python -m pipeline.publish [data/runs/<run>]      (default: newest folder in data/runs)
"""

import datetime as dt
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

import eccodes
import numpy as np

from pipeline.compute import (IST, build_days, build_intervals, daily_periods, days_not_matching_intervals,
                              expected_steps, m_to_mm, negative_threshold_mm, packing_increment_mm)
from pipeline.config import Region, load_region
from pipeline.fetch import DATA_ROOT, GRIB_NAME, HORIZON_HOURS
from pipeline.grid import region_grid_points
from pipeline.validate import REAL_GRID

log = logging.getLogger("pipeline.publish")

SCHEMA_VERSION = "1.0"
ATTRIBUTION = "Contains ECMWF Open Data (IFS HRES 0.25°), licensed under CC BY 4.0. Source: ECMWF."
UNITS = {"rain": "mm", "rate": "mm/h", "time": "ISO 8601 with UTC offset (IST = +05:30)"}
DAY_DEFINITION = ("23:30 IST to 23:30 IST (18:00-18:00 UTC). The first period runs from the forecast start "
                  "and is partial.")
SPOT_CHECK_POINTS = 3
MAX_REPORTED = 50


class PublishError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _key(lat: float, lon: float) -> str:
    return f"{lat:.2f},{lon:.2f}"


def _iso(t: dt.datetime) -> str:
    return t.astimezone(IST).isoformat(timespec="minutes")


def _load_run(run_dir: Path):
    """Manifest + checksum check. Returns (manifest, init datetime)."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    actual = _sha256(run_dir / GRIB_NAME)
    if actual != manifest["sha256"]:
        raise PublishError(f"checksum mismatch for {run_dir / GRIB_NAME}: file {actual[:16]}, "
                           f"manifest {manifest['sha256'][:16]}")
    return manifest, dt.datetime.fromisoformat(manifest["run_init_utc"])


def _read_region(run_dir: Path, region: Region, grid: dict):
    """Region values in mm per step, packing increments per step, and the selected grid axes."""
    cum, increments, sel = {}, {}, None
    with open(run_dir / GRIB_NAME, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                step = int(eccodes.codes_get(gid, "endStep"))
                if sel is None:
                    lats = eccodes.codes_get_array(gid, "distinctLatitudes")
                    lons = eccodes.codes_get_array(gid, "distinctLongitudes")
                    lat_sel, lon_sel = region_grid_points(region, lats, lons)
                    rows = [int(np.where(lats == x)[0][0]) for x in lat_sel]
                    cols = [int(np.where(lons == x)[0][0]) for x in lon_sel]
                    sel = (lat_sel, lon_sel, rows, cols)
                vals = eccodes.codes_get_values(gid).reshape(grid["Nj"], grid["Ni"])
                cum[step] = m_to_mm(vals[np.ix_(sel[2], sel[3])])
                increments[step] = packing_increment_mm(eccodes.codes_get(gid, "binaryScaleFactor"),
                                                        eccodes.codes_get(gid, "decimalScaleFactor"),
                                                        eccodes.codes_get(gid, "bitsPerValue"))
            finally:
                eccodes.codes_release(gid)
    return cum, increments, sel[0], sel[1]


def build_forecast(run_dir: Path, region: Region | None = None, grid: dict = REAL_GRID,
                   horizon_hours: int = HORIZON_HOURS) -> dict:
    region = region or load_region()
    manifest, init = _load_run(run_dir)
    cum, increments, lat_sel, lon_sel = _read_region(run_dir, region, grid)
    steps = expected_steps(horizon_hours)
    periods = daily_periods(init, horizon_hours)

    points, invalid = {}, []
    adj_iv = adj_day = unavailable = 0
    largest_adj = None
    for r, lat in enumerate(lat_sel):
        for c, lon in enumerate(lon_sel):
            key = _key(lat, lon)
            series = {s: float(cum[s][r, c]) for s in steps if s in cum}
            ivs = build_intervals(series, steps, increments=increments)
            days = build_days(series, periods, increments=increments)
            out_iv, out_days = [], []
            for i in ivs:
                e = {"start": _iso(init + dt.timedelta(hours=i["start_step"])),
                     "end": _iso(init + dt.timedelta(hours=i["end_step"])), "hours": i["hours"],
                     "mm": i["mm"], "raw_mm": i["raw_mm"], "mm_per_h": i["mm_per_h"], "status": i["status"]}
                out_iv.append(e)
            for d in days:
                e = {"date": d["date"].isoformat(), "start": _iso(d["start_ist"]), "end": _iso(d["end_ist"]),
                     "hours": d["hours"], "partial": d["partial"], "mm": d["mm"], "raw_mm": d["raw_mm"],
                     "status": d["status"]}
                out_days.append(e)
            for src, out in ((ivs, out_iv), (days, out_days)):
                for s, e in zip(src, out):
                    if s["status"] == "unavailable":
                        e["reason"] = s["reason"]
                        unavailable += 1
                    elif s["status"] == "invalid":
                        invalid.append(f"{key} {e['start']}->{e['end']}: raw {s['raw_mm']} mm")
                    elif s["status"] == "adjusted":
                        largest_adj = s["raw_mm"] if largest_adj is None else min(largest_adj, s["raw_mm"])
            adj_iv += sum(1 for i in ivs if i["status"] == "adjusted")
            adj_day += sum(1 for d in days if d["status"] == "adjusted")
            points[key] = {"lat": float(lat), "lon": float(lon), "days": out_days, "intervals": out_iv}

    if invalid:
        raise PublishError(f"{len(invalid)} invalid value(s) (negative beyond rounding threshold); not publishing. "
                           f"First: {invalid[:5]}")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "run": {"model": "ECMWF IFS HRES (open data, 0.25°)", "variable": "tp (total precipitation)",
                "init_utc": init.isoformat().replace("+00:00", "Z"), "init_ist": _iso(init),
                "horizon_hours": horizon_hours, "steps_used": len(steps),
                "source": manifest.get("source"), "source_sha256": manifest["sha256"]},
        "attribution": ATTRIBUTION,
        "units": UNITS,
        "day_definition": DAY_DEFINITION,
        "region": {"name": region.name, "lat_min": region.lat_min, "lat_max": region.lat_max,
                   "lon_min": region.lon_min, "lon_max": region.lon_max},
        "grid": {"spacing_deg": 0.25, "points": len(points),
                 "selection": "grid points within the region box expanded by 0.125 deg; ties snap north/east"},
        "quality": {"status": "partial" if unavailable else "ok", "adjusted_intervals": adj_iv,
                    "adjusted_days": adj_day, "largest_adjusted_raw_mm": largest_adj,
                    "unavailable_periods": unavailable},
        "points": points,
    }


# ------------------------------------------------------------------ checks before publishing

REQUIRED = ["schema_version", "generated_utc", "run", "attribution", "units", "day_definition",
            "region", "grid", "quality", "points"]


def _spot_values(run_dir: Path, keys: list[str], steps: set[int]) -> dict:
    """Independent, deliberately simple reader: raw mm at given points and steps, straight from the GRIB."""
    want = {k: tuple(float(x) for x in k.split(",")) for k in keys}
    out = {k: {} for k in keys}
    with open(run_dir / GRIB_NAME, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                step = int(eccodes.codes_get(gid, "endStep"))
                if step in steps:
                    lats = list(eccodes.codes_get_array(gid, "distinctLatitudes"))
                    lons = list(eccodes.codes_get_array(gid, "distinctLongitudes"))
                    ni = eccodes.codes_get(gid, "Ni")
                    vals = eccodes.codes_get_values(gid)
                    for k, (la, lo) in want.items():
                        out[k][step] = vals[lats.index(la) * ni + lons.index(lo)] * 1000.0
            finally:
                eccodes.codes_release(gid)
    return out


def check_forecast(doc: dict, run_dir: Path, region: Region | None = None, grid: dict = REAL_GRID,
                   horizon_hours: int = HORIZON_HOURS) -> list[str]:
    """Return a list of problems (empty = publishable)."""
    region = region or load_region()
    problems = [f"missing top-level field: {k}" for k in REQUIRED if k not in doc]
    if problems:
        return problems
    if doc["schema_version"] != SCHEMA_VERSION:
        problems.append(f"unknown schema_version {doc['schema_version']}")
    _, init = _load_run(run_dir)
    if doc["run"].get("init_utc") != init.isoformat().replace("+00:00", "Z"):
        problems.append("run.init_utc does not match the run folder")

    # (2) exactly the expected grid points
    cum, increments, lat_sel, lon_sel = _read_region(run_dir, region, grid)
    expected = {_key(a, b) for a in lat_sel for b in lon_sel}
    if set(doc["points"]) != expected:
        problems.append(f"points differ from expected: missing {sorted(expected - set(doc['points']))[:5]}, "
                        f"extra {sorted(set(doc['points']) - expected)[:5]}")

    steps = expected_steps(horizon_hours)
    n_days = len(daily_periods(init, horizon_hours))
    start_iso, end_iso = _iso(init), _iso(init + dt.timedelta(hours=horizon_hours))
    step_of = {_iso(init + dt.timedelta(hours=s)): s for s in steps}

    def entry_problems(key, e, kind):
        p = []
        st = e["status"]
        if st == "ok":
            if e["raw_mm"] is None or e["raw_mm"] < 0 or e["mm"] != e["raw_mm"]:
                p.append(f"{key} {kind} {e['start']}: ok value with mm != raw_mm or negative")
        elif st == "adjusted":
            a, b = step_of.get(e["start"]), step_of.get(e["end"])
            if e["mm"] != 0.0 or e["raw_mm"] is None or e["raw_mm"] >= 0:
                p.append(f"{key} {kind} {e['start']}: adjusted must have mm 0 and negative raw_mm")
            elif a is None or b is None or -e["raw_mm"] > negative_threshold_mm(increments[a], increments[b]):
                p.append(f"{key} {kind} {e['start']}: adjusted value {e['raw_mm']} beyond threshold")
        elif st == "unavailable":
            if e["mm"] is not None or e["raw_mm"] is not None or not e.get("reason"):
                p.append(f"{key} {kind} {e['start']}: unavailable must have null mm/raw_mm and a reason")
        else:
            p.append(f"{key} {kind} {e['start']}: status {st!r} not publishable")
        if kind == "interval" and st != "unavailable" and e["mm_per_h"] != e["mm"] / e["hours"]:
            p.append(f"{key} interval {e['start']}: mm_per_h inconsistent")
        return p

    for key, pt in doc["points"].items():
        if len(problems) > MAX_REPORTED:
            break
        try:
            ivs, days = pt["intervals"], pt["days"]
            # (3) counts and continuity
            if len(ivs) != len(steps) - 1 or len(days) != n_days:
                problems.append(f"{key}: {len(ivs)} intervals / {len(days)} days, expected {len(steps) - 1} / {n_days}")
            for seq, name in ((ivs, "intervals"), (days, "days")):
                if seq and (seq[0]["start"] != start_iso or seq[-1]["end"] != end_iso):
                    problems.append(f"{key}: {name} do not span {start_iso} -> {end_iso}")
                if any(x["end"] != y["start"] for x, y in zip(seq, seq[1:])):
                    problems.append(f"{key}: {name} not contiguous")
            # (4) durations
            for e in ivs:
                a, b = step_of.get(e["start"]), step_of.get(e["end"])
                ok = a is not None and b is not None and e["hours"] == b - a == (3 if b <= 144 else 6)
                if not ok:
                    problems.append(f"{key} interval {e['start']}: hours {e['hours']} wrong")
            for d in days:
                a, b = step_of.get(d["start"]), step_of.get(d["end"])
                if a is None or b is None or d["hours"] != b - a or d["partial"] != (d["hours"] != 24) \
                        or not d["end"].endswith("T23:30+05:30"):
                    problems.append(f"{key} day {d['date']}: wrong window/hours")
            # (5, 6) status rules and threshold
            for e in ivs:
                problems += entry_problems(key, e, "interval")
            for d in days:
                problems += entry_problems(key, d, "day")
            # (7) day = sum of its intervals (exact), for fully available days
            for d in days:
                parts = [e for e in ivs if d["start"] <= e["start"] and e["end"] <= d["end"]]
                if d["raw_mm"] is None or any(e["raw_mm"] is None for e in parts):
                    continue
                if sum(e["raw_mm"] for e in parts) != d["raw_mm"]:
                    problems.append(f"{key} day {d['date']}: day != sum of intervals")
        except (KeyError, TypeError) as exc:
            problems.append(f"{key}: malformed entry ({type(exc).__name__}: {exc})")

    # (8) independent spot check from the GRIB file
    keys = sorted(doc["points"])
    picks = [keys[0], keys[len(keys) // 2], keys[-1]] if keys else []
    if picks:
        bounds = {step_of[d["start"]] for k in picks for d in doc["points"][k].get("days", []) if d["start"] in step_of}
        bounds |= {step_of[d["end"]] for k in picks for d in doc["points"][k].get("days", []) if d["end"] in step_of}
        raw = _spot_values(run_dir, picks, bounds)
        for k in picks:
            for d in doc["points"][k].get("days", []):
                a, b = step_of.get(d["start"]), step_of.get(d["end"])
                if a in raw[k] and b in raw[k] and d["raw_mm"] is not None and raw[k][b] - raw[k][a] != d["raw_mm"]:
                    problems.append(f"spot check {k} {d['date']}: JSON {d['raw_mm']} != GRIB {raw[k][b] - raw[k][a]}")
    return problems


# ------------------------------------------------------------------ publishing

def publish_run(run_dir: Path, data_root: Path = DATA_ROOT, region: Region | None = None,
                grid: dict = REAL_GRID) -> Path:
    processed = data_root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    rid = run_dir.name
    out, latest = processed / f"{rid}.json", processed / "latest.json"
    if out.exists():
        log.info("run %s already published (%s); nothing to do", rid, out)
        return out

    _, init = _load_run(run_dir)
    if latest.exists():   # (9) never replace a newer forecast with an older one
        current = json.loads(latest.read_text(encoding="utf-8"))["run"]["init_utc"]
        if init < dt.datetime.fromisoformat(current.replace("Z", "+00:00")):
            raise PublishError(f"run {rid} is older than the published forecast ({current}); not publishing")

    doc = build_forecast(run_dir, region=region, grid=grid)
    problems = check_forecast(doc, run_dir, region=region, grid=grid)
    if problems:
        raise PublishError(f"JSON checks failed ({len(problems)}):\n  " + "\n  ".join(problems[:MAX_REPORTED]))

    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    for target in (out, latest):
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)   # atomic swap on the same disk
    q = doc["quality"]
    log.info("published %s: %d points, %s bytes, quality %s (adjusted: %d intervals, %d days; unavailable: %d)",
             rid, len(doc["points"]), f"{len(text.encode('utf-8')):,}", q["status"], q["adjusted_intervals"],
             q["adjusted_days"], q["unavailable_periods"])
    return out


def main(argv) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    if len(argv) > 1:
        run_dir = Path(argv[1])
    else:
        runs = sorted((DATA_ROOT / "runs").iterdir()) if (DATA_ROOT / "runs").exists() else []
        if not runs:
            log.error("no fetched runs in %s", DATA_ROOT / "runs")
            return 1
        run_dir = runs[-1]
    publish_run(run_dir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
