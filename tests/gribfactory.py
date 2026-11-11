"""Build small synthetic tp GRIB2 runs for tests (no network, no real data needed).

Each message mimics the verified real metadata (D-007): paramId 228 (tp), template 8, accumulation from
step 0, hours, regular lat/lon grid. Only the grid is tiny (3 x 4) so tests run fast.
Faults can be injected per step via `overrides`, `skip`, `duplicate`.
"""

import eccodes

SMALL_GRID = {
    "gridType": "regular_ll",
    "Ni": 4, "Nj": 3,
    "latitudeOfFirstGridPointInDegrees": 13.5, "longitudeOfFirstGridPointInDegrees": 79.5,
    "latitudeOfLastGridPointInDegrees": 13.0, "longitudeOfLastGridPointInDegrees": 80.25,
    "iDirectionIncrementInDegrees": 0.25, "jDirectionIncrementInDegrees": 0.25,
}


def make_message(step, date=20261111, time=0, grid=SMALL_GRID, packing="grid_ccsds", values=None, missing=False):
    g = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    # Date must be set BEFORE the step: with template 8 the end-of-interval time is derived when the step is set.
    eccodes.codes_set(g, "dataDate", date)
    eccodes.codes_set(g, "dataTime", time)
    eccodes.codes_set(g, "productDefinitionTemplateNumber", 8)
    eccodes.codes_set(g, "paramId", 228)
    eccodes.codes_set(g, "typeOfStatisticalProcessing", 1)
    eccodes.codes_set(g, "stepUnits", 1)
    eccodes.codes_set(g, "startStep", 0)
    eccodes.codes_set(g, "endStep", step)
    for k, v in grid.items():
        if k != "gridType":
            eccodes.codes_set(g, k, v)
    eccodes.codes_set(g, "bitsPerValue", 12)
    n = grid["Ni"] * grid["Nj"]
    vals = list(values) if values is not None else [step * 1e-5] * n  # metres, rising with step
    if missing:
        # a bitmap must be switched on BEFORE values are set; then the missingValue marks a missing point
        eccodes.codes_set(g, "bitmapPresent", 1)
        vals[0] = eccodes.codes_get(g, "missingValue")
    eccodes.codes_set_values(g, vals)
    eccodes.codes_set(g, "packingType", packing)
    return g


def write_run(path, steps, date=20261111, time=0, grid=SMALL_GRID, overrides=None, skip=(), duplicate=(),
              values=None, missing_at=()):
    """Write a multi-message GRIB file. overrides: {step: {key: value}} applied after normal setup."""
    overrides = overrides or {}
    with open(path, "wb") as f:
        for s in steps:
            if s in skip:
                continue
            for _ in range(2 if s in duplicate else 1):
                ov = dict(overrides.get(s, {}))
                g = make_message(s, date=ov.pop("dataDate", date), time=time, grid=ov.pop("grid", grid),
                                 packing=ov.pop("packingType", "grid_ccsds"),
                                 values=ov.pop("values", values.get(s) if isinstance(values, dict) else None),
                                 missing=s in missing_at)
                for k, v in ov.items():
                    eccodes.codes_set(g, k, v)
                eccodes.codes_write(g, f)
                eccodes.codes_release(g)
    return path
