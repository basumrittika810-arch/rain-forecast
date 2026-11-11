"""Verify a full-run tp GRIB file against the semantics established in the inspection. Read-only.

Usage:
    python scripts/verify_run.py <run_grib> <manifest_json> <sample_grib> <output_txt>

Checks (each reported PASS/FAIL or as measured evidence; nothing is clamped or altered):
  A. SHA-256 matches manifest
  B. Per-message metadata rules (tp, m, accum, startStep=0, stepRange 0-N, template 8 / processing 1,
     same init time, validity = init + step, identical grid, no bitmap/missing values)
  C. Step list vs expected cadence; actual interval durations
  D. Steps shared with the earlier sample file are bit-identical
  E. Negative differences for every consecutive interval, in units of packing increments
  F. Same for daily periods (18 UTC boundaries = 23:30 IST), incl. partial first period
  G. Telescoping: (end - start) == sum of consecutive interval differences, exactly, on every grid point
  H. Where the packing increment (2^E) changes
  I. Worked example: real daily + interval values at the grid point nearest Chennai
"""

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import eccodes
import numpy as np

INDIA_BOX = (6.0, 38.0, 68.0, 98.0)  # lat_min, lat_max, lon_min, lon_max (inspection box)
DAILY_BOUNDARIES = [0, 18, 42, 66, 90, 114, 138, 162, 186, 210, 234, 258]
CHENNAI_GRID = (13.0, 80.25)
IST = dt.timedelta(hours=5, minutes=30)
META_KEYS = ["shortName", "units", "stepType", "startStep", "endStep", "stepRange",
             "productDefinitionTemplateNumber", "typeOfStatisticalProcessing", "lengthOfTimeRange",
             "dataDate", "dataTime", "validityDate", "validityTime", "Ni", "Nj",
             "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
             "latitudeOfLastGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
             "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees",
             "bitmapPresent", "numberOfMissing", "binaryScaleFactor", "decimalScaleFactor",
             "referenceValue", "bitsPerValue"]

lines = []


def log(s=""):
    print(s)
    lines.append(s)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_messages(path, with_values=True):
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                meta = {k: eccodes.codes_get(gid, k) for k in META_KEYS}
                vals = eccodes.codes_get_values(gid).reshape(meta["Nj"], meta["Ni"]) if with_values else None
                if with_values and "lats" not in iter_messages.__dict__:
                    iter_messages.lats = eccodes.codes_get_array(gid, "distinctLatitudes")
                    iter_messages.lons = eccodes.codes_get_array(gid, "distinctLongitudes")
                yield meta, vals
            finally:
                eccodes.codes_release(gid)


def to_dt(date, time):
    return dt.datetime.strptime(f"{date}{time:04d}", "%Y%m%d%H%M")


def neg_report(label, diff, inc_a, inc_b, earlier, box):
    """Evidence on negative differences; returns dict. Nothing is altered."""
    neg = diff < 0
    n = int(neg.sum())
    nb = int(neg[box].sum())
    res = {"n": n, "n_box": nb}
    if n:
        coarse, fine = max(inc_a, inc_b), min(inc_a, inc_b)
        res.update(min=float(diff.min()), in_coarse_inc=float(-diff.min() / coarse),
                   in_fine_inc=float(-diff.min() / fine),
                   max_earlier_at_neg=float(earlier[neg].max()))
    return res


def main(argv):
    run_path, manifest_path, sample_path, out_path = map(Path, argv[1:5])

    # ---- A. integrity ----
    log("## A. Integrity")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sha = sha256_of(run_path)
    log(f"  manifest sha256: {manifest['sha256']}")
    log(f"  computed sha256: {sha}")
    log(f"  {'PASS' if sha == manifest['sha256'] else 'FAIL'}: checksum matches manifest")

    # ---- B/C. metadata pass (no values) ----
    metas = [m for m, _ in iter_messages(run_path, with_values=False)]
    steps = [int(m["endStep"]) for m in metas]
    log("\n## B. Per-message metadata rules")
    log(f"  messages: {len(metas)}; file order ascending by step: {steps == sorted(steps)}")
    if steps != sorted(steps):
        log("  FAIL: messages not in ascending step order; streaming checks below would be invalid. Stopping.")
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    init = to_dt(metas[0]["dataDate"], metas[0]["dataTime"])
    ref_grid = {k: metas[0][k] for k in META_KEYS if k.startswith(("Ni", "Nj", "latitudeOf", "longitudeOf", "iDir", "jDir"))}
    rules = {
        "shortName == tp": lambda m: m["shortName"] == "tp",
        "units == m": lambda m: m["units"] == "m",
        "stepType == accum": lambda m: m["stepType"] == "accum",
        "startStep == 0": lambda m: int(m["startStep"]) == 0,
        "stepRange == '0-N' (or '0' at step 0)": lambda m: m["stepRange"] == (f"0-{m['endStep']}" if m["endStep"] else "0"),
        "lengthOfTimeRange == endStep": lambda m: int(m["lengthOfTimeRange"]) == int(m["endStep"]),
        "template 8, statistical processing 1 (accumulation)":
            lambda m: m["productDefinitionTemplateNumber"] == 8 and m["typeOfStatisticalProcessing"] == 1,
        "same initialisation time": lambda m: to_dt(m["dataDate"], m["dataTime"]) == init,
        "validity == init + endStep": lambda m: to_dt(m["validityDate"], m["validityTime"]) == init + dt.timedelta(hours=int(m["endStep"])),
        "identical grid": lambda m: all(m[k] == v for k, v in ref_grid.items()),
        "no bitmap / no missing": lambda m: m["bitmapPresent"] == 0 and m["numberOfMissing"] == 0,
        "decimalScaleFactor 0, referenceValue 0": lambda m: m["decimalScaleFactor"] == 0 and m["referenceValue"] == 0,
    }
    for name, rule in rules.items():
        bad = [int(m["endStep"]) for m in metas if not rule(m)]
        log(f"  {'PASS' if not bad else 'FAIL'}: {name}" + (f"  -> failing steps {bad}" if bad else ""))
    log(f"  initialisation: {init:%Y-%m-%d %H:%M} UTC = {init + IST:%Y-%m-%d %H:%M} IST")

    log("\n## C. Step list and interval durations")
    expected = list(range(0, 145, 3)) + list(range(150, 259, 6))
    log(f"  {'PASS' if steps == expected else 'FAIL'}: steps == 0..144 by 3 + 150..258 by 6 ({len(steps)} steps)")
    durs = np.diff(steps)
    for d in sorted(set(durs)):
        idx = [i for i, x in enumerate(durs) if x == d]
        log(f"  {d} h intervals: {len(idx)} (from {steps[idx[0]]}->{steps[idx[0] + 1]} to {steps[idx[-1]]}->{steps[idx[-1] + 1]})")
    log(f"  daily boundaries present: {all(b in steps for b in DAILY_BOUNDARIES)}")

    log("\n## H. Packing increment (2^binaryScaleFactor) by step")
    prevE = None
    for m in metas:
        E = m["binaryScaleFactor"]
        if E != prevE:
            log(f"  from step {m['endStep']:>3}: E={E}, increment = {2.0 ** E * 1000:.4f} mm, bitsPerValue={m['bitsPerValue']}")
            prevE = E

    # ---- D. cross-check with sample ----
    log("\n## D. Steps shared with the earlier sample file are bit-identical")
    sample = {int(m["endStep"]): v for m, v in iter_messages(sample_path)}

    # ---- streaming value pass: E, F, G, I ----
    lats, lons = None, None
    prev_vals, prev_step, prev_inc = None, None, None
    boundary_vals, boundary_inc = {}, {}
    running_sum = None  # sum of consecutive interval diffs since the last daily boundary
    tele_results = []
    interval_neg = []
    ch = {}
    box = None
    for m, vals in iter_messages(run_path):
        s, inc = int(m["endStep"]), 2.0 ** m["binaryScaleFactor"]
        if lats is None:
            lats, lons = iter_messages.lats, iter_messages.lons
            box = np.zeros(vals.shape, bool)
            box[np.ix_((lats >= INDIA_BOX[0]) & (lats <= INDIA_BOX[1]),
                       (lons >= INDIA_BOX[2]) & (lons <= INDIA_BOX[3]))] = True
            ci = int(np.where(lats == CHENNAI_GRID[0])[0][0]); cj = int(np.where(lons == CHENNAI_GRID[1])[0][0])
        if s in sample:
            same = np.array_equal(vals, sample[s])
            log(f"  {'PASS' if same else 'FAIL'}: step {s} identical to sample")
        ch[s] = vals[ci, cj]
        if prev_vals is not None:
            d = vals - prev_vals
            interval_neg.append((prev_step, s, neg_report("", d, prev_inc, inc, prev_vals, box)))
            running_sum = d if running_sum is None else running_sum + d
        if s in DAILY_BOUNDARIES:
            if boundary_vals and running_sum is not None:
                b0 = max(boundary_vals)
                direct = vals - boundary_vals[b0]
                tele_results.append((b0, s, bool(np.array_equal(direct, running_sum)),
                                     float(np.abs(direct - running_sum).max())))
            boundary_vals[s], boundary_inc[s] = vals, inc
            running_sum = None
        prev_vals, prev_step, prev_inc = vals, s, inc

    # ---- E. interval negatives ----
    log("\n## E. Negative differences, consecutive intervals (later - earlier); values NOT altered")
    tot = sum(r["n"] for _, _, r in interval_neg)
    tot_box = sum(r["n_box"] for _, _, r in interval_neg)
    log(f"  intervals examined: {len(interval_neg)}; grid points per interval: {lats.size * lons.size}")
    log(f"  total negative interval values: global {tot}, India box {tot_box}")
    worst_coarse = max((r.get("in_coarse_inc", 0) for _, _, r in interval_neg), default=0)
    worst_fine = max((r.get("in_fine_inc", 0) for _, _, r in interval_neg), default=0)
    log(f"  largest negative, in increments of the COARSER field of the pair: {worst_coarse:g}")
    log(f"  largest negative, in increments of the FINER field of the pair:   {worst_fine:g}")
    log("  per interval with negatives: a->b  n_global  n_box  min(mm)  min/coarse_inc  min/fine_inc  max earlier value at neg pts (mm)")
    for a, b, r in interval_neg:
        if r["n"]:
            log(f"    {a:>3}->{b:<3} {r['n']:>6} {r['n_box']:>5} {r['min'] * 1000:8.3f} {r['in_coarse_inc']:6.2f} "
                f"{r['in_fine_inc']:6.2f} {r['max_earlier_at_neg'] * 1000:8.3f}")
    clean = [f"{a}->{b}" for a, b, r in interval_neg if not r["n"]]
    log(f"  intervals with no negatives ({len(clean)}): {', '.join(clean)}")

    # ---- F. daily negatives + summary ----
    log("\n## F. Daily periods (18 UTC = 23:30 IST boundaries); values NOT altered")
    bl = DAILY_BOUNDARIES
    for a, b in zip(bl[:-1], bl[1:]):
        d = boundary_vals[b] - boundary_vals[a]
        r = neg_report("", d, boundary_inc[a], boundary_inc[b], boundary_vals[a], box)
        start, end = init + dt.timedelta(hours=a) + IST, init + dt.timedelta(hours=b) + IST
        kind = "PARTIAL" if b - a != 24 else "full"
        db = d[box]
        log(f"  {a:>3}->{b:<3} ({b - a:>2} h, {kind:<7}) IST {start:%d %b %H:%M} -> {end:%d %b %H:%M}: "
            f"neg global={r['n']}, box={r['n_box']}" + (f", min={r['min'] * 1000:.3f} mm ({r['in_coarse_inc']:.2f} coarse inc)" if r['n'] else "")
            + f" | box mm: mean={db.mean() * 1000:.2f} p90={np.percentile(db, 90) * 1000:.2f} max={db.max() * 1000:.2f}")

    # ---- G. telescoping ----
    log("\n## G. Telescoping: (end - start) == sum of consecutive interval differences (whole globe, exact)")
    for a, b, eq, mx in tele_results:
        log(f"  {'PASS' if eq else 'FAIL'}: {a:>3}->{b:<3} exact equality={eq}, max |difference|={mx:.3g}")

    # ---- I. worked example ----
    log(f"\n## I. Worked example at grid point {CHENNAI_GRID} (nearest Chennai); values NOT altered")
    log("  Daily periods:")
    for a, b in zip(bl[:-1], bl[1:]):
        start, end = init + dt.timedelta(hours=a) + IST, init + dt.timedelta(hours=b) + IST
        log(f"    {end:%d %b} ({start:%d %b %H:%M}->{end:%d %b %H:%M} IST, {b - a} h): "
            f"{ch[b] * 1000:8.3f} - {ch[a] * 1000:8.3f} = {(ch[b] - ch[a]) * 1000:8.3f} mm")
    log("  Intervals with non-zero or negative rain:")
    ss = sorted(ch)
    for a, b in zip(ss[:-1], ss[1:]):
        v = (ch[b] - ch[a]) * 1000
        if v != 0:
            log(f"    {a:>3}->{b:<3} ({b - a} h, IST {init + dt.timedelta(hours=a) + IST:%d %b %H:%M}->"
                f"{init + dt.timedelta(hours=b) + IST:%H:%M}): {v:8.3f} mm  avg {v / (b - a):.3f} mm/h")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
