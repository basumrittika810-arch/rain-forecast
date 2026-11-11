"""Inspect a tp GRIB file with ecCodes directly (reference decoder). Read-only.

Usage:
    python scripts/inspect_eccodes.py <grib_file> <output_txt>

Reports, per message: metadata keys, grid geometry, global and India-box value statistics,
negative values, and step-to-step differences (to test cumulative vs interval semantics).
Values are reported in the file's native units; any mm figure is labelled as a display-only
x1000 conversion that assumes the declared unit is metres.
"""

import sys
from pathlib import Path

import eccodes
import numpy as np

# India-wide INSPECTION box (not the pilot region). Inclusive bounds, degrees.
INDIA_BOX = {"lat_min": 6.0, "lat_max": 38.0, "lon_min": 68.0, "lon_max": 98.0}

KEYS = [
    "edition", "centre", "shortName", "name", "paramId", "units", "cfName", "cfVarName",
    "typeOfLevel", "level", "dataType", "typeOfProcessedData",
    "stepType", "stepUnits", "stepRange", "startStep", "endStep", "forecastTime",
    "productDefinitionTemplateNumber", "typeOfStatisticalProcessing",
    "lengthOfTimeRange", "indicatorOfUnitForTimeRange",
    "dataDate", "dataTime", "validityDate", "validityTime",
    "gridType", "Ni", "Nj", "numberOfDataPoints", "numberOfValues",
    "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
    "latitudeOfLastGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
    "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees",
    "iScansNegatively", "jScansPositively", "jPointsAreConsecutive",
    "packingType", "bitsPerValue", "referenceValue", "binaryScaleFactor", "decimalScaleFactor",
    "bitmapPresent", "numberOfMissing", "missingValue",
    "minimum", "maximum", "average",
]

_out = None


def log(*args):
    text = " ".join(str(a) for a in args)
    print(text)
    _out.write(text + "\n")


def get_key(gid, key):
    try:
        return eccodes.codes_get(gid, key)
    except eccodes.KeyValueNotFoundError:
        return "<key not present>"


def read_messages(path: Path):
    msgs = []
    with open(path, "rb") as f:  # read-only
        while True:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                meta = {k: get_key(gid, k) for k in KEYS}
                values = eccodes.codes_get_values(gid)  # float64, scanning order
                lats = eccodes.codes_get_array(gid, "distinctLatitudes")
                lons = eccodes.codes_get_array(gid, "distinctLongitudes")
                msgs.append({"meta": meta, "values": values, "lats": lats, "lons": lons})
            finally:
                eccodes.codes_release(gid)
    return msgs


def stats(arr: np.ndarray, label: str):
    a = arr[np.isfinite(arr)]
    p = np.percentile(a, [50, 90, 95, 99, 99.9])
    log(f"    {label}: n={arr.size} finite={a.size} nan={arr.size - a.size}")
    log(f"      min={a.min():.9g} max={a.max():.9g} mean={a.mean():.9g}")
    log(f"      p50={p[0]:.9g} p90={p[1]:.9g} p95={p[2]:.9g} p99={p[3]:.9g} p99.9={p[4]:.9g}")
    log(f"      exactly zero: {(a == 0).sum()} ({100 * (a == 0).mean():.2f}%)   "
        f"negative: {(a < 0).sum()}")


def main(argv):
    global _out
    if len(argv) != 3:
        print(__doc__)
        return 2
    path, out_path = Path(argv[1]), Path(argv[2])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _out = open(out_path, "w", encoding="utf-8")

    log(f"# ecCodes inspection of {path.name}")
    log(f"ecCodes C library {eccodes.codes_get_api_version()}, eccodes-python {eccodes.__version__}")
    msgs = read_messages(path)
    log(f"Messages: {len(msgs)}")

    # ---------- 1. Metadata ----------
    log("\n## 1. Metadata per message (verbatim ecCodes keys)")
    for i, m in enumerate(msgs):
        log(f"\n--- message {i + 1} ---")
        for k in KEYS:
            log(f"  {k:<36} = {m['meta'][k]}")

    # ---------- 2. Grid geometry ----------
    log("\n## 2. Grid geometry (from message 1, checked identical across messages)")
    m0 = msgs[0]
    Ni, Nj = m0["meta"]["Ni"], m0["meta"]["Nj"]
    lats, lons = m0["lats"], m0["lons"]
    same_grid = all(np.array_equal(m["lats"], lats) and np.array_equal(m["lons"], lons)
                    and m["values"].size == Ni * Nj for m in msgs)
    log(f"  identical grid in all messages: {same_grid}")
    log(f"  Ni (columns, longitudes) = {Ni}, Nj (rows, latitudes) = {Nj}, Ni*Nj = {Ni * Nj}")
    log(f"  distinct latitudes : {lats.size}, first={lats[0]}, last={lats[-1]}, "
        f"order={'north->south (descending)' if lats[0] > lats[-1] else 'south->north (ascending)'}")
    log(f"  distinct longitudes: {lons.size}, first={lons[0]}, last={lons[-1]}")
    dlat = np.unique(np.round(np.abs(np.diff(lats)), 6))
    dlon = np.unique(np.round(np.diff(lons), 6))
    log(f"  unique latitude spacing  : {dlat}")
    log(f"  unique longitude spacing : {dlon}")
    log(f"  longitude convention     : "
        f"{'-180..180' if lons.min() < 0 else '0..360'} (min={lons.min()}, max={lons.max()})")

    # 2D fields: rows = latitudes (in file order), cols = longitudes
    fields = {int(m["meta"]["endStep"]): m["values"].reshape(Nj, Ni) for m in msgs}
    steps = sorted(fields)

    lat_mask = (lats >= INDIA_BOX["lat_min"]) & (lats <= INDIA_BOX["lat_max"])
    lon_mask = (lons >= INDIA_BOX["lon_min"]) & (lons <= INDIA_BOX["lon_max"])
    box_lats, box_lons = lats[lat_mask], lons[lon_mask]
    log(f"\n  India inspection box {INDIA_BOX}")
    log(f"    latitudes in box : {box_lats.size} ({box_lats.max()} .. {box_lats.min()})")
    log(f"    longitudes in box: {box_lons.size} ({box_lons.min()} .. {box_lons.max()})")
    log(f"    grid points in box: {box_lats.size * box_lons.size}")

    def india(field):
        return field[np.ix_(lat_mask, lon_mask)]

    # ---------- 3. Value statistics ----------
    log("\n## 3. Value statistics (native units as declared in 'units' key)")
    weights = np.cos(np.deg2rad(lats))[:, None] * np.ones((1, Ni))
    for s in steps:
        f = fields[s]
        log(f"\n  step {s} h (stepRange={msgs[steps.index(s)]['meta']['stepRange']})")
        stats(f, "GLOBAL")
        gm = np.average(f, weights=weights)
        log(f"      area-weighted (cos lat) global mean = {gm:.9g}  "
            f"[display-only x1000 = {gm * 1000:.4f} mm if unit is m]")
        stats(india(f), "INDIA BOX")

    # ---------- 4. Negative values ----------
    log("\n## 4. Negative values in the stored fields")
    any_neg = False
    for s in steps:
        f = fields[s]
        neg = f < 0
        n = int(neg.sum())
        log(f"  step {s:>3} h: negative count global={n}, India box={int((india(f) < 0).sum())}")
        if n:
            any_neg = True
            ii, jj = np.where(neg)
            log(f"    most negative = {f.min():.9g}")
            for r, c in list(zip(ii, jj))[:20]:
                log(f"    lat={lats[r]} lon={lons[c]} value={f[r, c]:.9g}")
    log(f"  any negative value in any message: {any_neg}")

    # ---------- 5. Step-to-step differences ----------
    log("\n## 5. Step-to-step differences  (later - earlier), per grid point")
    log("   If tp is accumulated from initialisation, later >= earlier everywhere (up to packing precision).")
    log("   If tp is per-interval, decreases would be common wherever rain eases off.")
    for a, b in zip(steps[:-1], steps[1:]):
        for label, fa, fb in (("GLOBAL", fields[a], fields[b]),
                              ("INDIA ", india(fields[a]), india(fields[b]))):
            d = fb - fa
            dec = d < 0
            log(f"  {a:>3}->{b:<3} h {label}: decreases={int(dec.sum())} "
                f"({100 * dec.mean():.4f}%), unchanged={int((d == 0).sum())}, "
                f"increases={int((d > 0).sum())}, min diff={d.min():.9g}, max diff={d.max():.9g}")
            if dec.any() and label == "GLOBAL":
                ii, jj = np.where(dec)
                log(f"      decreasing points (first 10 of {dec.sum()}):")
                for r, c in list(zip(ii, jj))[:10]:
                    log(f"        lat={lats[r]} lon={lons[c]} {a}h={fa[r, c]:.9g} {b}h={fb[r, c]:.9g} "
                        f"diff={d[r, c]:.9g}")
                mags, counts = np.unique(d[dec], return_counts=True)
                log(f"      distinct decrease magnitudes: "
                    + ", ".join(f"{mv:.9g} (x{cnt})" for mv, cnt in zip(mags, counts)))
                band_edges = [-90, -60, -30, 0, 30, 60, 90]
                hist, _ = np.histogram(lats[ii], bins=band_edges)
                log("      decreases by latitude band: "
                    + ", ".join(f"[{lo},{hi}): {h}" for lo, hi, h in
                                zip(band_edges[:-1], band_edges[1:], hist)))
            if dec.any() and label.strip() == "INDIA":
                ii, jj = np.where(dec)
                log(f"      India-box decreasing points (all {dec.sum()}, showing up to 60):")
                for r, c in list(zip(ii, jj))[:60]:
                    log(f"        lat={box_lats[r]} lon={box_lons[c]} {a}h={fa[r, c]:.9g} "
                        f"{b}h={fb[r, c]:.9g} diff={d[r, c]:.9g}")

    # ---------- 6. Packing precision ----------
    log("\n## 6. Packing precision (smallest representable increment per message)")
    log("   simple packing: value = (R + X * 2^E) / 10^D  ->  step size = 2^E / 10^D")
    for m in msgs:
        E = m["meta"]["binaryScaleFactor"]
        D = m["meta"]["decimalScaleFactor"]
        if isinstance(E, int) and isinstance(D, int):
            log(f"  step {m['meta']['endStep']:>3} h: E={E} D={D} R={m['meta']['referenceValue']} "
                f"bits={m['meta']['bitsPerValue']} -> increment = {2.0 ** E / 10.0 ** D:.3g}")
        else:
            log(f"  step {m['meta']['endStep']:>3} h: packing keys unavailable ({E}, {D})")

    # ---------- 7. Independent check of the packing formula ----------
    log("\n## 7. Are decoded values exact integer multiples of the packing increment?")
    for m in msgs:
        E, D, R = (m["meta"]["binaryScaleFactor"], m["meta"]["decimalScaleFactor"],
                   m["meta"]["referenceValue"])
        inc = 2.0 ** E / 10.0 ** D
        k = (m["values"] * 10.0 ** D - R) / 2.0 ** E
        off = np.abs(k - np.round(k)).max()
        log(f"  step {m['meta']['endStep']:>3} h: max |k - round(k)| = {off:.3g}  "
            f"(0 => every value = R + integer * {inc:.3g}); max integer k = {int(np.round(k).max())}, "
            f"2^bits - 1 = {2 ** m['meta']['bitsPerValue'] - 1}")

    # ---------- 8. Where is the heaviest accumulated rain in the India box? ----------
    log("\n## 8. Heaviest accumulations in the India inspection box (top 10 grid points)")
    for s in steps[1:]:
        b = india(fields[s])
        flat = np.argsort(b, axis=None)[::-1][:10]
        rr, cc = np.unravel_index(flat, b.shape)
        log(f"  step {s} h:")
        for r, c in zip(rr, cc):
            log(f"    lat={box_lats[r]:>6} lon={box_lons[c]:>6} value={b[r, c]:.9g}")
    log("\n  India box: number of grid points whose accumulation exceeds a threshold")
    log("  (thresholds expressed in the file unit; e.g. 0.001 = 1 mm if unit is m)")
    for s in steps[1:]:
        b = india(fields[s])
        log(f"  step {s:>3} h: " + ", ".join(
            f">={t:g}: {int((b >= t).sum())}" for t in (0.001, 0.01, 0.05, 0.1, 0.2)))

    _out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
