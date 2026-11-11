"""Inspect real GRIB precision metadata and grid geometry to evaluate the threshold and grid proposals.
Read-only; implements nothing in the pipeline.

Usage:
    python scripts/inspect_precision.py <run_grib> <output_txt>
"""

import math
import sys
import tomllib
from pathlib import Path

import eccodes
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DAILY = [0, 18, 42, 66, 90, 114, 138, 162, 186, 210, 234, 258]
lines = []


def log(s=""):
    print(s)
    lines.append(s)


def main(argv):
    run_path, out_path = Path(argv[1]), Path(argv[2])
    reg = tomllib.loads((ROOT / "config" / "settings.toml").read_text(encoding="utf-8"))["region"]

    fields, meta = {}, {}
    with open(run_path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                s = int(eccodes.codes_get(gid, "endStep"))
                meta[s] = {k: eccodes.codes_get(gid, k) for k in
                           ("packingType", "bitsPerValue", "binaryScaleFactor", "decimalScaleFactor", "referenceValue")}
                nj, ni = eccodes.codes_get(gid, "Nj"), eccodes.codes_get(gid, "Ni")
                fields[s] = eccodes.codes_get_values(gid).reshape(nj, ni) * 1000.0  # mm
                lats = eccodes.codes_get_array(gid, "distinctLatitudes")
                lons = eccodes.codes_get_array(gid, "distinctLongitudes")
            finally:
                eccodes.codes_release(gid)
    steps = sorted(fields)
    inc = {s: 1000.0 * 2.0 ** meta[s]["binaryScaleFactor"] / 10.0 ** meta[s]["decimalScaleFactor"] for s in steps}

    # ---------------- 1. precision metadata ----------------
    log("## 1. Precision metadata, all messages")
    combos = {}
    for s in steps:
        m = meta[s]
        key = (m["packingType"], m["bitsPerValue"], m["binaryScaleFactor"], m["decimalScaleFactor"], m["referenceValue"])
        combos.setdefault(key, []).append(s)
    for (pt, bits, E, D, R), ss in combos.items():
        log(f"  packing={pt} bits={bits} E={E} D={D} R={R}: steps {ss[0]}..{ss[-1]} ({len(ss)} messages)")
    log("\n  Why E changes: with 12 bits the largest storable integer is 4095, so max value must be <= 4095 * 2^E")
    for s in steps:
        if s == 0:
            continue
        k_max = fields[s].max() / inc[s]
        flag = "  <-- E changed here" if s > 3 and inc[s] != inc[steps[steps.index(s) - 1]] else ""
        if flag or s in (3, 6, 129, 258):
            log(f"  step {s:>3}: max={fields[s].max():9.3f} mm, increment={inc[s]:.4f} mm, max/increment={k_max:7.1f} (limit 4095){flag}")
    log("\n  Every stored value an exact integer multiple of its own increment?")
    worst = max(float(np.abs(fields[s] / inc[s] - np.round(fields[s] / inc[s])).max()) for s in steps if s)
    log(f"  max |value/increment - nearest integer| over all 67 non-constant messages = {worst}")

    # ---------------- 2. negatives vs threshold options ----------------
    lat_m = (lats >= reg["lat_min"]) & (lats <= reg["lat_max"])
    lon_m = (lons >= reg["lon_min"]) & (lons <= reg["lon_max"])
    tn = np.zeros(fields[0].shape, bool)
    tn[np.ix_(lat_m, lon_m)] = True

    def evaluate(pairs, label):
        log(f"\n  {label}")
        tot = {"neg": 0, "a": 0, "b": 0, "c": 0}
        tn_neg = 0
        examples = []
        for a, b in pairs:
            d = fields[b] - fields[a]
            neg = d < 0
            if not neg.any():
                continue
            qa, qb = inc[a], inc[b]
            fine, coarse, mid = min(qa, qb), max(qa, qb), (qa + qb) / 2
            dn = -d[neg]
            tot["neg"] += int(neg.sum())
            tot["a"] += int((dn > fine).sum())
            tot["b"] += int((dn > coarse).sum())
            tot["c"] += int((dn > mid).sum())
            tn_neg += int((neg & tn).sum())
            log(f"    {a:>3}->{b:<3} increments {qa:.4f}/{qb:.4f} mm: {int(neg.sum()):>6} negatives "
                f"(TN box {int((neg & tn).sum())}), largest {dn.max():.4f} mm = {dn.max() / fine:.2f} x finer increment")
            for r, c in zip(*np.where(neg & tn)):
                if len(examples) < 8:
                    examples.append((a, b, lats[r], lons[c], fields[a][r, c], fields[b][r, c], d[r, c], fine))
        log(f"    TOTAL negatives {tot['neg']} (TN box {tn_neg}). Would be BLOCKED under:"
            f" (a) finer increment: {tot['a']}, (b) coarser: {tot['b']}, (c) mean: {tot['c']}")
        if examples:
            log("    Real examples inside the Tamil Nadu box:")
            for a, b, la, lo, va, vb, dd, fine in examples:
                log(f"      {a:>3}->{b:<3} at {la:.2f}N {lo:.2f}E: {va:.6f} -> {vb:.6f} mm, diff {dd:.6f} mm "
                    f"(= {dd / fine:.0f} x {fine:.4f})")

    log("\n## 2. Negative differences vs threshold options (nothing altered)")
    evaluate(list(zip(steps[:-1], steps[1:])), "Consecutive intervals (67):")
    evaluate(list(zip(DAILY[:-1], DAILY[1:])), "Daily periods (11):")

    # ---------------- 3. grid geometry and tie-breaking ----------------
    log("\n## 3. Grid geometry")
    log(f"  latitudes exact multiples of 0.25: {bool(np.all(lats * 4 == np.round(lats * 4)))}; "
        f"longitudes: {bool(np.all(lons * 4 == np.round(lons * 4)))}")
    strict_lat, strict_lon = lats[lat_m], lons[lon_m]
    h = 0.125
    marg_lat = lats[(lats >= reg["lat_min"] - h) & (lats <= reg["lat_max"] + h)]
    marg_lon = lons[(lons >= reg["lon_min"] - h) & (lons <= reg["lon_max"] + h)]
    log(f"  strict box : lat {strict_lat.min()}..{strict_lat.max()} ({strict_lat.size}) x "
        f"lon {strict_lon.min()}..{strict_lon.max()} ({strict_lon.size}) = {strict_lat.size * strict_lon.size} points")
    log(f"  +0.125 margin: lat {marg_lat.min()}..{marg_lat.max()} ({marg_lat.size}) x "
        f"lon {marg_lon.min()}..{marg_lon.max()} ({marg_lon.size}) = {marg_lat.size * marg_lon.size} points")
    log(f"  extra latitudes with margin: {sorted(set(marg_lat) - set(strict_lat))}; "
        f"extra longitudes: {sorted(set(marg_lon) - set(strict_lon))}")

    def snap_half_up(x):
        return math.floor(x * 4 + 0.5) / 4

    log("\n  Snapping examples: rule floor(x*4+0.5)/4 vs Python round(x*4)/4")
    tests = [("Chennai", 13.0825, 80.275), ("Coimbatore", 11.00083, 76.96333), ("Madurai", 9.9252, 78.1198),
             ("tie lat 13.125", 13.125, 80.0), ("tie lat 13.375", 13.375, 80.0), ("tie lon 80.125", 12.0, 80.125),
             ("near south edge 8.09", 8.09, 77.5), ("near east edge 80.33", 12.0, 80.33)]
    for name, la, lo in tests:
        g = (snap_half_up(la), snap_half_up(lo))
        r = (round(la * 4) / 4, round(lo * 4) / 4)
        in_strict = g[0] in strict_lat and g[1] in strict_lon
        in_marg = g[0] in marg_lat and g[1] in marg_lon
        log(f"  {name:<22} ({la}, {lo}) -> half-up {g}  python-round {r}{'  DIFFERENT' if g != r else ''}"
            f" | stored in strict: {in_strict}, with margin: {in_marg}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
