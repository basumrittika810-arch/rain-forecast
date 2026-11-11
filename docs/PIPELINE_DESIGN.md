# Pipeline and JSON Design (P1 + J1)

- **Status:** design for review, **not implemented**. Decided in D-012 (`docs/DECISIONS.md`).
- **Date:** 2026-11-12

## 1. Pipeline structure (P1: one run, stages in sequence)

```
pipeline/
  config.py    (exists) load region + settings from config/settings.toml
  fetch.py     find newest complete 00/12 UTC run; download tp, steps 0–258; checksum + manifest
  validate.py  check every GRIB message against the verified rules (tp, m, accum, startStep=0, steps, grid…)
  compute.py   crop to region grid points; intervals, daily totals, rates; apply negative-value rule
  publish.py   build JSON → validate JSON → write temp file → atomically replace latest.json
  run.py       calls the stages in order; stops at the first failure; previous forecast stays live
```

| Stage | Input | Output | Stops the run if… |
|---|---|---|---|
| fetch | server listing | raw GRIB (read-only) + manifest | required steps missing on server; download incomplete |
| validate | raw GRIB | "OK" or error | any metadata rule fails (same rules as `scripts/verify_run.py`) |
| compute | raw GRIB + region | in-memory results | a negative difference exceeds the threshold (D-008) |
| publish | results | `data/processed/latest.json` | any JSON check fails (§4) |

- GRIB is read with **ecCodes directly** (not cfgrib), so the `0-N` accumulation window is checked on every run.
- A **missing boundary step** does not stop the run (decision 6.4): the two affected days and their intervals
  are marked `unavailable`. A missing step that is *not* a boundary only affects the intervals that use it.
- **Negative threshold (D-008):** derived per pair from the actual packing increments (2^E) of the two fields.
  Whether "one rounding step" means the finer or the coarser increment is still to be fixed by tests.
  Observed so far: every negative is exactly one finer increment.

## 2. JSON output (J1): sample for one location

Real values from run 2026-11-11 00 UTC, grid point 13.00 N 80.25 E (nearest Chennai); lists shortened with `…`.

```json
{
  "schema_version": "1.0",
  "generated_utc": "2026-11-11T08:05:00Z",
  "run": {
    "model": "ECMWF IFS HRES (open data, 0.25°)",
    "variable": "tp (total precipitation)",
    "init_utc": "2026-11-11T00:00:00Z",
    "init_ist": "2026-11-11T05:30:00+05:30",
    "horizon_hours": 258,
    "steps_used": 68,
    "source": "https://data.ecmwf.int/forecasts",
    "source_sha256": "6de90b3f713cbdc191689e21659a7216a421f4c376af0a15f971f89cbc6f3132"
  },
  "attribution": "Contains ECMWF Open Data, licensed under CC BY 4.0.",
  "units": {"rain": "mm", "rate": "mm/h", "time": "ISO 8601 with UTC offset (IST = +05:30)"},
  "day_definition": "23:30 IST to 23:30 IST (18:00–18:00 UTC). First period runs from forecast start (05:30 IST) and is partial.",
  "region": {"name": "Tamil Nadu", "lat_min": 8.083333, "lat_max": 13.583333, "lon_min": 76.25, "lon_max": 80.333333},
  "quality": {
    "status": "ok",
    "negative_adjustments": {"count": 0, "largest_raw_mm": null},
    "unavailable_periods": 0
  },
  "points": {
    "13.00,80.25": {
      "lat": 13.0,
      "lon": 80.25,
      "days": [
        {"date": "2026-11-11", "start": "2026-11-11T05:30+05:30", "end": "2026-11-11T23:30+05:30",
         "hours": 18, "partial": true,  "mm": 0.0,   "raw_mm": 0.0,   "status": "ok"},
        {"date": "2026-11-12", "start": "2026-11-11T23:30+05:30", "end": "2026-11-12T23:30+05:30",
         "hours": 24, "partial": false, "mm": 0.366, "raw_mm": 0.366, "status": "ok"},
        "…",
        {"date": "2026-11-20", "start": "2026-11-19T23:30+05:30", "end": "2026-11-20T23:30+05:30",
         "hours": 24, "partial": false, "mm": 11.963, "raw_mm": 11.963, "status": "ok"}
      ],
      "intervals": [
        {"start": "2026-11-11T05:30+05:30", "end": "2026-11-11T08:30+05:30", "hours": 3,
         "mm": 0.0, "raw_mm": 0.0, "mm_per_h": 0.0, "status": "ok"},
        "…",
        {"start": "2026-11-12T23:30+05:30", "end": "2026-11-13T02:30+05:30", "hours": 3,
         "mm": 0.732, "raw_mm": 0.732, "mm_per_h": 0.244, "status": "ok"},
        "…",
        {"start": "2026-11-19T23:30+05:30", "end": "2026-11-20T05:30+05:30", "hours": 6,
         "mm": 10.986, "raw_mm": 10.986, "mm_per_h": 1.831, "status": "ok"}
      ]
    }
  }
}
```

The numbers above are shown to 3 decimals for readability. The file will store the **unrounded** values, which
are exact multiples of the packing increment, so the checks in §4 can be exact. Rounding for display is a frontend decision.
`generated_utc` is illustrative.

**Data-quality flags.** These are *format illustrations, not real data* (no such values occur at this point):

```json
{"…": "…", "mm": 0.0,  "raw_mm": -0.244, "status": "adjusted"}
{"…": "…", "mm": null, "raw_mm": null, "mm_per_h": null, "status": "unavailable", "reason": "missing boundary step 42 h"}
```

| `status` | Meaning | `mm` | `raw_mm` |
|---|---|---|---|
| `ok` | normal | = raw_mm (≥ 0) | as calculated |
| `adjusted` | small negative within one rounding step (D-008) | 0 | the negative value, kept |
| `unavailable` | a required step is missing | `null` (never 0) | `null` |

Top-level `quality.status` is `ok`, or `partial` if anything is `unavailable`.

Size estimate: ~10 KB per point × ~374 points ≈ 3–4 MB per run (estimate, to be measured).

## 3. How the API finds one location

1. When the API starts (and whenever `latest.json` changes), it loads the file into memory once.
2. Request: `GET /forecast?lat=13.08&lon=80.27`
3. Check that the location is inside the region box. If not, reply "outside the forecast region" (HTTP 404).
4. Snap to the **nearest grid point** (0.25° spacing): 13.08 → 13.00, 80.27 → 80.25. The tie-breaking
   rule for points exactly halfway will be fixed by tests.
5. Look up the key `"13.00,80.25"`. This is a single dictionary lookup, well under 1 ms.
6. Reply with that point's days and intervals, plus `run`, `units`, `quality`, `attribution`, and both the
   **requested** and the **grid** coordinates, so the user can see which grid point answered.

## 4. Validating the JSON before publishing

The new file is written to a temporary name. It becomes `latest.json` only if **all** checks pass.
Otherwise it is not published, the previous forecast stays live, and the reason is logged.

| # | Check | Catches |
|---|---|---|
| 1 | All required fields present, correct types, `schema_version` known | broken or partial file |
| 2 | Number of points = number of grid points inside the configured region | missing or extra locations |
| 3 | Each point: 11 days and 67 intervals, in time order, **each start = previous end** | gaps, overlaps, misordered times |
| 4 | Interval hours are 3 up to 144 h, then 6; day 1 = 18 h partial, others 24 h | wrong durations or day boundaries |
| 5 | `status` rules from the table above hold for every value; no `mm` < 0; missing is `null`, never 0 | silent zero-filling, unflagged negatives |
| 6 | No raw negative larger than the threshold | invalid data being published |
| 7 | For every day: the day's `raw_mm` = sum of its intervals' `raw_mm` (exact) | arithmetic or alignment errors |
| 8 | **Independent spot check:** a few points recomputed straight from the GRIB with separate, simple code; must match | the main calculation being wrong in a consistent way |
| 9 | `run.init_utc` is newer than or equal to the currently published run | accidentally publishing an older forecast |

Publishing itself: write `data/processed/forecast.tmp.json`, run checks 1–9, then rename it to `latest.json`
in one step (`os.replace`, atomic on the same disk). A copy is also kept as `data/processed/<run>.json`.
`data/` stays git-ignored.

## Open points for the test/implementation phase
- Finer vs coarser increment as the negative threshold (D-008).
- Tie-breaking for nearest grid point; how grid points at the box edge are chosen.
- How the frontend shows the partial first day and rounds values.
- 00z only, or 00z + 12z.
