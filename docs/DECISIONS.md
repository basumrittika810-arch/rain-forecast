# Decision Log

Each entry records: timestamp, context, decision, alternatives considered, who decided,
evidence, and status.

**Status labels**
- **Verified**: confirmed by direct observation or a test in this project (evidence cited)
- **Documented**: stated by authoritative documentation (source cited), not yet observed by us
- **Provisional**: working assumption, still to be verified
- **Decided**: a choice made by the project owner (not a factual claim)

Decision maker: Mrittika Basu (project owner). Claude (AI assistant) proposes, explains and implements.

---

## D-000: Project scope and P1/P2 setup decisions
- **Timestamp:** 2026-11-11 (session start)
- **Status:** Decided
- **Decision:** Agreed scope: ECMWF IFS HRES Open Data, 0.25°, `tp` only, 10-day horizon,
  Python/FastAPI backend, simple responsive frontend, one configurable pilot region in India,
  scheduled updates with safe failure handling, public deployment. Docker, databases, Redis,
  ensembles, extra variables, multiple regions, LLM features and farming advice are excluded.
- **P2 setup decisions (owner-approved):**
  - Git initialised in `C:\Users\HP\rain-forecast`; Python 3.12 virtual environment.
  - GRIB tooling installed via pip first; no Miniforge or system-level changes without explicit approval.
  - Initial sample only: steps 0, 3, 6, 144, 150, 240 h of the latest *complete* 00 or 12 UTC run.
  - Raw GRIB kept in git-ignored `data/`, treated as immutable. No raw data, credentials or keys committed.
  - India-wide bounding box for the initial inspection; pilot region **not yet chosen**.
- **Deferred until after data inspection:** pilot region, daily-aggregation day boundary,
  negative-value tolerance, first-day display rule.
- **Deferred until later:** location selection method, UI language, display granularity,
  hosting platform and scheduler placement, GitHub remote.

## D-001: Windows Smart App Control blocked ecCodes and pandas
- **Timestamp:** 2026-11-11, ~21:00–21:38 IST
- **Status:** Verified (problem and fix both observed)
- **Context:** `pip install ecmwf-opendata eccodes cfgrib xarray` into the Python 3.12.10 venv
  **succeeded**. Importing failed:
  `ImportError: DLL load failed while importing _eccodes: An Application Control policy has blocked this file.`
- **Evidence collected (read-only diagnostics):**
  - Registry `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`
    (Smart App Control **on**).
  - `Get-AuthenticodeSignature` on `eccodes\_eccodes.cp312-win_amd64.pyd` → `NotSigned`.
  - `pandas` import also blocked (`pandas_parser`), so the block was not specific to ecCodes;
    `numpy` imported successfully.
- **Alternatives considered:**
  - A. Turn off Smart App Control: fastest; lowers OS protection; possibly cannot be re-enabled
    without resetting Windows (not verified for this build).
  - B. WSL2 (Linux on Windows): avoids the policy; matches a likely Linux deployment target; costs a
    system-level install and ~20–40 min. (Assistant's recommendation.)
  - C. Cloud dev environment (e.g. GitHub Codespaces): no local change; needs the GitHub remote now.
  - D. Search for older package builds that happen to be trusted: rejected as fragile.
  - Miniforge was judged unlikely to help, since conda-forge DLLs are also unsigned (not tested).
- **Decision (owner):** Option A, turn off Smart App Control ("seems easier").
- **Verification after the change:** registry value `0`; `import eccodes, pandas, xarray, cfgrib`
  succeeds; ecCodes C library 2.50.0; `python -m cfgrib selfcheck` → "Found: ecCodes v2.50.0. Your system is ready."
- **Consequence to remember:** this setup relies on Smart App Control being off. Another Windows
  machine with it on will hit the same error (noted in README).

## D-002: Geographic subsetting is not available; variable subsetting is
- **Timestamp:** 2026-11-11 ~21:40 IST
- **Status:** Verified at client level; ECMWF documentation not yet read
- **Evidence (source of installed `ecmwf-opendata` 0.3.35, `ecmwf/opendata/client.py`):**
  - `area` is in the `POSPROCESSING` set (lines 507–516). When it is passed, the client only logs
    "MARS post-processing keywords ... not supported" (line 535); it does not crop.
  - Data URLs are static file paths
    (`{date}/{HH}z/ifs/0p25/oper/{date}{HH}0000-{step}h-oper-fc.grib2`, lines 35–38), not queries.
  - Each GRIB file has a `.index` JSON-lines sidecar with `_offset`/`_length` per message. The client
    downloads only the requested parameter's bytes (lines 311–357).
- **Consequence:** download global `tp` fields (parameter-only byte ranges) and crop to the region locally.
- **Also observed:** the client's `latest()` checks only that step files exist (HTTP HEAD), not that
  `tp` is inside them (lines 197–210). Our own stricter check is in `scripts/check_availability.py`.

## D-003: Initial sample downloaded (2026-11-11 00 UTC run)
- **Timestamp:** 2026-11-11 16:09 UTC (21:39 IST)
- **Status:** Verified (download and structural completeness only; **no value interpretation yet**)
- **Availability check** (`scripts/check_availability.py`, run at 16:09 UTC):
  - 2026-11-11 **12 UTC**: HTTP 404 for all six sample steps, i.e. not yet published ~4 h after nominal time.
  - 2026-11-11 **00 UTC**: `.index` HTTP 200 for steps 0, 3, 6, 144, 150, 240; exactly one `tp` entry each.
    Step files contain 191 messages (194 at step 0); step-0 `tp` entry `_length` = 224 bytes.
  - Chosen: the 00 UTC run (newest run with `tp` for all sample steps).
- **Download** (`scripts/download_sample.py 20261111 00`):
  - File `data/raw/20261111T00Z/tp_steps_0-3-6-144-150-240.grib2`, 2,244,314 bytes,
    SHA-256 `42570d628ec5f210630e97ed8afd957f3d413a5856d6d0e6b243ec4232a35308`; marked read-only.
  - ecCodes lists 6 messages, all `shortName=tp`, with `stepRange` = `0`, `0-3`, `0-6`, `0-144`,
    `0-150`, `0-240`.
  - Client printed the licence notice: **CC BY 4.0, attribution to ECMWF required** (documented by
    ECMWF's own client; to be shown in the UI).
- **Provisional / not yet concluded:**
  - The `stepRange` values starting at `0` *suggest* accumulation from forecast start. This is **not
    yet verified**; it must be checked against the `stepType`/units keys, the values, and ECMWF documentation.
  - Size estimate for a full run: ~0.45 MB per step × ~65 steps ≈ 30 MB. This is an extrapolation,
    not measured. (The earlier P1 estimate of 100–150 MB was too high.)

## D-004: First data inspection (findings only, no design decisions)
- **Timestamp:** 2026-11-11 16:21–16:24 UTC
- **Status:** Verified for the 6 inspected steps; open items listed in the report
- **Report:** `docs/INSPECTION_20261111T00Z.md` (raw outputs in `docs/inspection/`)
- **Key verified findings:** units `m`; `tp` accumulated from initialisation (metadata + all-zero
  step 0 + growth ~3 mm/day global mean + no decreases in 144→150, 150→240); no missing or negative stored
  values; rare step-to-step decreases ≤ 0.122 mm; quantisation 0.061 mm (E=−14) / 0.244 mm (E=−12);
  cfgrib values identical to ecCodes; cfgrib hides `stepRange`.
- **Correction of an earlier expectation:** in P1 I attributed any negatives to packing. Decreases
  between two fields with the *same* packing increment (3→6 h) cannot come from final packing alone.
  Cause is unresolved.
- **Integrity:** SHA-256 identical before and after inspection; no files written to `data/raw`.
- **Decisions deferred to joint review:** daily-aggregation boundaries, handling of negative interval
  differences, pilot region.

## D-005: Daily rainfall analysis (recommendation pending owner decision)
- **Timestamp:** 2026-11-11 ~17:00 UTC
- **Status:** Findings verified as labelled; recommendations **not yet decided**
- **Report:** `docs/DAILY_RAINFALL_ANALYSIS.md`
- **New verified facts:** the 00z run on the server has 85 steps (0–144 by 3, 150–360 by 6); step 147 → 404;
  all 00 UTC and 18 UTC day-boundary steps exist; 03 UTC boundaries stop at 123 h. Run files `Last-Modified`
  07:34 UTC (13:04 IST). `tp` for steps ≤ 240 h = 33.3 MB.
- **Documentation conflict found:** the installed `ecmwf-opendata` README says HRES steps go to 240 h; the official
  ECMWF pages and the server show 360 h. The server is taken as the authority for what exists.
- **Client behaviour:** a missing step file raises an HTTP error; a missing `tp` inside an existing file only
  produces a warning (quiet failure). Our completeness check covers this.
- **Recommended (pending):** daily window 23:30→23:30 IST (18→18 UTC); daily total = end − start reading;
  no interpolation of missing boundary steps.

## D-006: Owner decisions on daily rainfall
- **Timestamp:** 2026-11-11 18:13 UTC (23:43 IST)
- **Status:** Decided (owner). Details and reasoning in `docs/DAILY_RAINFALL_ANALYSIS.md` §6.
- **Decisions:**
  1. Daily window **23:30→23:30 IST (18→18 UTC)**.
  2. Horizon **258 h**: initial partial period (05:30→23:30 IST on the run date) plus 10 complete
     24-h periods. The partial period must be presented as partial.
  3. Download **all available steps through 258 h** and verify the actual step list and metadata.
  4. Missing boundary: **publish valid periods**, mark both affected periods unavailable, never fill with
     zero or estimates; keep the previous validated forecast if the update fails.
  5. Output **daily totals and 3-/6-h interval rainfall**; rates use the actual interval duration and
     must not imply timing within an interval.
  6. Negative-value handling **left open**.
- **Where the owner differed from the assistant's recommendation:** horizon (assistant: stay within 240 h),
  missing boundary (assistant: reject the whole run), output (assistant: daily totals only for MVP).
  The owner's reasons: a more useful daily forecast; don't discard a usable forecast for one or two gaps;
  timing information improves the user experience.
- **Correction:** the earlier "boundary steps ≈ 6 MB" estimate covered one window option only; both
  options needed 11.4 MB.

## D-007: Full-run download and verification (00 UTC 2026-11-11, steps 0–258)
- **Timestamp:** 2026-11-11 ~18:15–18:25 UTC
- **Status:** Verified (details in `docs/DAILY_RAINFALL_ANALYSIS.md` §7 and
  `docs/inspection/verify_run_20261111T00Z_0-258.txt`)
- **Evidence:** server listing re-checked: 68 steps ≤ 258 h, matching the expected cadence. Downloaded 35.1 MB,
  SHA-256 `6de90b3f713cbdc191689e21659a7216a421f4c376af0a15f971f89cbc6f3132`. All 68 messages pass the metadata rules
  (incl. `startStep=0`), so accumulation from initialisation is now verified for every step used. Shared steps are
  bit-identical to the sample. Telescoping equality is exact for all 11 daily periods.
- **Negative differences (unaltered):** 5 of 67 intervals, 0.24 % of interval values. Every one is exactly one
  increment of the finer field. 96 % occur at increment changes (6→9, 129→132). They also occur where totals are
  large, which corrects the earlier impression that they were limited to near-dry points. They appear in 2 of 11
  daily periods (min −0.244 mm).
- **Negative-value handling remains open (owner decision 6.6).**
- **Process notes (D-007):** a truncated-output command gave exit 255 (pipe closed early) and was re-run in full.
  `2>&1` in PowerShell displayed ECMWF's informational stderr notice as an error; nothing failed.

## D-008: Negative-difference rule and provisional pilot region
- **Timestamp:** 2026-11-12
- **Status:** Decided (owner)
- **Negative differences:**
  - The original GRIB data and the raw calculated differences stay **untouched** (stored as computed).
  - A negative difference whose magnitude is **within one verified rounding step** is **displayed as 0 mm**,
    and the adjustment is **logged** (count and magnitude).
  - A negative difference **larger than that** flags the affected data and **blocks publication** of that forecast;
    the previous validated forecast stays live.
  - The threshold is **derived from the actual data precision** of each run (the packing increment 2^E of the
    fields involved), **not hardcoded** (e.g. not 0.1 mm). Evidence basis: D-007 (all observed negatives = exactly
    one increment of the finer field of the pair).
  - Open for implementation: precisely which increment defines "one rounding step" for a pair with different
    increments (finer vs coarser). D-007 observed max = one *finer* increment. To be settled with tests before use.
- **Pilot region:** **Tamil Nadu (provisional)**, kept **configurable** via a central config file so it can change.
  Its bounding box still has to be defined and checked against a cited source when the config is created.

## D-009: Project structure and dependencies for the application
- **Timestamp:** 2026-11-12
- **Status:** Done (setup only, no application code)
- Before any change, the existing venv (Python 3.12.10, ecCodes 2.50.0, cfgrib 0.9.15.1) was confirmed to read
  `tp_steps_0-258.grib2`: 68 messages via ecCodes; cfgrib reads 68×721×1440; value at 13.0N 80.25E, step 258 =
  27.34375 mm, matching `verify_run.py`. No reinstall was needed.
- Added folders `pipeline/`, `api/`, `web/`, `tests/`. Existing `scripts/` (investigation and verification tools) kept unchanged.
- Added FastAPI + Uvicorn (API) and pytest (tests). Runtime and dev dependencies are pinned separately.

## D-010: Tamil Nadu region configuration
- **Timestamp:** 2026-11-12
- **Status:** Done; source documented; tests pass
- **Config:** `config/settings.toml` `[region]`: lat 8.083333–13.583333 N, lon 76.25–80.333333 E (inclusive).
  Loaded and validated by `pipeline/config.py` (`load_region()`); no coordinates are hardcoded in processing code.
- **Source:** TNAU Agritech Portal, "Tamil Nadu at a glance", §1 Geographical Position: "North Latitude Between
  8° 5' and 13° 35'" / "East Longitude Between 76° 15' and 80° 20'"
  (https://agritech.tnau.ac.in/agriculture/agri_agricultureataglance_tnataglance.html, read directly 2026-11-12).
  A search snippet attributes the same figures to tnbb.tn.gov.in, but that page refused connection, so it is
  not cited as verified. Some education sites give 8°4' / 76°18' (variants, not used).
- **Format choice:** TOML, read with Python's built-in `tomllib`, so no new dependency.
- **Checks (`tests/test_config.py`, 16 passed on first run):** Chennai (13.0825, 80.275), Coimbatore (11.00083, 76.96333),
  Madurai (9.9252, 78.1198) inside; Kolkata (22.5675, 88.37) outside (Wikipedia infobox coordinates). Edges are
  inclusive. Invalid configs are rejected (missing section or key, swapped bounds, out-of-range, 0–360
  longitude, non-numeric, boolean, empty name).
- **Known limitations (open):** the rectangle also covers parts of Kerala, Karnataka, Andhra Pradesh, northern
  Sri Lanka and sea. Chennai is only ~6 km inside the east edge. The source gives the extent to the nearest
  minute. Selecting grid cells for this box (0.25° grid) is a pipeline decision still to make.

## D-011: Repository published to GitHub
- **Timestamp:** 2026-11-12
- **Status:** Done, verified
- **Remote:** https://github.com/basumrittika810-arch/rain-forecast (public). `main` pushed normally: no force,
  no history rewrite.
- **Pre-push checks (whole history, not just current files):** `git fsck` clean; 7 commits intact. No GRIB/data,
  `.idx`, `.venv`, `.env`, key or credential files ever committed. Largest blob ever committed is 31 KB. Secret-pattern
  scan of every file version and every commit message found nothing; the scan was positive-controlled.
- **Owner decision:** the commit author email is publicly visible in history; owner chose to push as-is
  (alternatives offered: make the repo private first, or rewrite the author email).
- **Verification:** local `main` = GitHub `main` = `a87049d1dcdb477e14a94f924eef8dc6714ab657`; ahead/behind 0/0.

## D-012: Pipeline organisation P1 and JSON layout J1
- **Timestamp:** 2026-11-12
- **Status:** Decided (owner). Design in `docs/PIPELINE_DESIGN.md`; **not implemented yet** (tests come first,
  under owner supervision).
- **Pipeline P1:** one run executes fetch → validate → compute → publish in sequence, starting fresh from the raw GRIB.
  It stops at the first failure and the previous validated forecast stays live. GRIB is read with ecCodes directly.
- **JSON J1:** one file per run; every grid point carries its own dates and times next to its values (daily totals,
  3-h/6-h intervals, rates), each value with `raw_mm`, displayed `mm` and `status` (`ok` / `adjusted` / `unavailable`;
  missing = `null`, never 0).
- **Why P1:** it validates every forecast before anyone sees it; it has the fewest moving parts to test; its only
  downside (rerunning everything after a late failure, ~1 min) is negligible for one region.
- **Why J1:** a value cannot easily end up beside the wrong date, because each number sits next to its own times. It
  can be checked by eye. Its extra size (~3–4 MB estimated for ~374 points) is not a problem at this scale.
- **Rejected:**
  - **P2** (stages saving intermediate files): more files to keep consistent; risk of reusing a stale
    intermediate file; its benefit (rerunning one stage) only matters for a much larger, hypothetical workload.
  - **P3** (compute per API request): nothing is validated before a user sees it, which violates the
    validate-before-publish rule; rainfall logic would sit inside the API.
  - **J2** (times listed once, values as position-matched lists): one dropped or added value would shift every
    later value to the wrong date. Hard to check by eye. Its size saving (~0.4 MB vs ~3–4 MB) is not needed now.
  - **J3** (one file per grid point): 374 files must switch to a new forecast at the same moment. An interrupted
    update could mix today's and yesterday's forecasts.
- **Accepted trade-off:** J1 does not scale to very large regions (all India ≈ 150 MB est.). If that ever happens,
  only the JSON writer and loader change, not the rainfall calculations.

## D-013: Rainfall arithmetic tests and minimal implementation
- **Timestamp:** 2026-11-12
- **Status:** Done (tests first, then code); threshold derivation and grid tie-breaking are **proposals only**, not implemented
- **Files:** `tests/test_compute.py` (27 tests, hand-derived expected values on artificial data), `pipeline/compute.py`
  (pure functions: m→mm, intervals, 23:30 IST daily periods incl. 18-h partial first day, daily totals from the two
  boundary readings, missing → `unavailable` (never 0), D-008 classification with the threshold passed in,
  publish gate, day = sum-of-intervals check).
- **Evidence:** the tests were run before the code existed (collection error: module missing), then 43/43 passed
  (27 new + 16 config). Mutation check: changing the day boundary to 00 UTC failed 4 tests; making an exactly-one-step
  negative invalid failed 2 tests. The original code was restored (hash identical) and 43/43 pass.
- **Design detail fixed by tests:** a missing *intermediate* step makes only its two intervals unavailable (no merged
  6-h interval); days are unaffected. The day = sum-of-intervals check skips days with unavailable intervals.

## D-014: Real-data check of the threshold and grid proposals (evidence only)
- **Timestamp:** 2026-11-12
- **Status:** Verified evidence; **proposals still awaiting owner decision; nothing implemented**
- **Script/output:** `scripts/inspect_precision.py` → `docs/inspection/precision_and_grid_20261111T00Z.txt`
  (run 2026-11-11 00z, steps 0–258; raw file SHA-256 unchanged before and after).
- **Precision metadata (all 68 messages):** `grid_ccsds`, 12 bits, D=0, R=0. E = −14 (steps 3–6), −13 (9–129),
  −12 (132–258); step 0 is a constant field. E is set so that the field maximum fits in 12 bits (≤ 4095 increments):
  at step 6 the max is 4022 increments, so step 9 moves to a coarser E. **The maximum is global**, so Tamil Nadu's
  precision depends on rain anywhere on Earth and will differ between runs. The threshold must be read per message,
  never fixed. Every stored value is an exact multiple of its increment (max deviation 0.0).
- **Negatives vs options:** all 168,793 interval negatives and 43,523 daily-total negatives are exactly one finer
  increment. Blocked under (a) finer increment: 0; (b) coarser: 0; (c) mean: 0. **This run cannot tell the options
  apart**; (a) is the strictest one that passes. Tamil Nadu box: 68 interval negatives (6→9: 12; 129→132: 56)
  and 32 daily negatives (period 114→138 = 16 Nov), e.g. 13.50N 79.75E: 3.296 → 3.174 mm. So dips are not only at
  near-zero totals.
- **Grid:** all coordinates are exact multiples of 0.25. Strict box: 22 × 17 = 374 points (lat 8.25–13.5,
  lon 76.25–80.25). With a 0.125° margin: 391 points, adding only the lat 8.0 row. A location at 8.09N (inside the box)
  snaps to 8.0, which is stored only with the margin.
- **Tie rule:** Python `round` sends 13.125 → 13.0 and 80.125 → 80.0 (round-half-to-even); `floor(x*4+0.5)/4`
  sends them to 13.25 and 80.25 (always north/east). Chennai, Coimbatore and Madurai snap identically under both.

## D-015: Negative threshold (option C), tie rule, grid margin
- **Timestamp:** 2026-11-12
- **Status:** Decided (owner) and implemented with tests
- **Owner decisions:**
  1. **Threshold option C:** `(q1 + q2) / 2`, derived per pair from the two readings' own packing increments.
     Owner's reasoning: it accounts for the maximum possible rounding error in both readings, rather than tolerating
     only the smaller error. (The assistant had recommended option A, the finer increment.)
  2. **Exact ties go north/east:** `floor(x / 0.25 + 0.5) * 0.25`.
  3. **Grid margin:** store 391 grid points (box + 0.125°, adding the 8.0N row). The application bounding box stays unchanged.
- **Rounding-mode check (owner asked before implementing):** GRIB metadata defines decoding only; it **does not
  record the encoder's rounding mode**, so the metadata alone cannot confirm round-to-nearest. Empirical test
  (`scripts/inspect_rounding.py` → `docs/inspection/rounding_mode_20261111T00Z.txt`) at the two increment-doubling pairs,
  on points whose earlier value lies between coarse marks: 6→9 h 16 % down / 80 % up; 129→132 h 33 % / 65 %. The shares
  are stable when requiring 12–72 h of no change afterwards. This rules out always-down (up share would fall towards 0)
  and always-up (no downs would occur). **Consistent with round-to-nearest; not proven.** The up/down imbalance is
  unexplained. All observed dips (≤ 1 finer increment) are within option C regardless.
- **Correction found during implementation (by reasoning, before any test caught it):** step 0 is a constant field
  (bitsPerValue 0, E=0). Using 2^E would give an increment of 1000 mm and a 0→3 h threshold of ~500 mm. A constant field
  is exact, so its increment is defined as **0** (`packing_increment_mm(..., bits_per_value=0) = 0`); the 0→3 h threshold
  is then q3/2. Test added: a 1 mm dip at 0→3 h is invalid.
- **Implementation:** `pipeline/compute.py` (`packing_increment_mm`, `negative_threshold_mm`; `build_intervals`/`build_days`
  take per-step increments and raise if a negative appears without them), `pipeline/grid.py` (`snap_to_grid`,
  `region_grid_points`). Tests: `tests/test_compute.py`, `tests/test_grid.py`; tests failed before code existed
  (collection errors), then **77/77 passed**.
- **Real-data check (not a unit test; raw file SHA-256 unchanged):** 391 Tamil Nadu points from run 2026-11-11 00z with
  increments read per message: intervals 26,121 ok / 76 adjusted / **0 invalid**; days 4,269 ok / 32 adjusted / **0 invalid**;
  day ≠ sum(intervals): 0.

## D-016: Pipeline Step 1, fetch + validate (no publishing)
- **Timestamp:** 2026-11-12 (local) / 2026-11-11 ~21:46 UTC
- **Status:** Implemented and tested; real run verified
- **Files:** `pipeline/validate.py`, `pipeline/fetch.py`, `tests/test_fetch_validate.py` (26 tests),
  `tests/gribfactory.py` (synthetic tp GRIB2 runs via ecCodes samples; no network needed).
- **Behaviour:** download into `data/tmp/<run>_<id>/` → validate (all 68 steps 0–258 present once, nothing extra; tp/228,
  units m, accumulation template 8/processing 1, startStep 0, hours, same initialisation, validity = init + step, expected
  grid, packing in {grid_ccsds, grid_simple}, no missing values, no negative or non-finite stored values; readable file)
  → write manifest, make GRIB read-only → atomic rename to new `data/runs/<run>/`. Any failure moves the temp folder to
  `data/rejected/…` with `reason.txt` (kept for investigation, not deleted) and raises. An existing run folder is never
  overwritten (refused before downloading). `data/processed/` / `latest.json` are never touched.
- **Scope choice:** only 00 UTC runs are considered (`RUN_HOURS = (0,)`) because the 00z/12z question is undecided and
  the 23:30 IST / 258 h design was set for 00z. **Open decision.**
- **Bug found by the tests (real, fixed):** on Windows, rejecting an incomplete or corrupt download failed with
  `PermissionError: Access is denied` when moving the temp folder. Cause: ecCodes passes the Python file to C through a
  duplicated handle that closes only when the file object is freed, and the raised error's traceback kept it alive.
  Fix: all reading happens in `_scan()`, which always returns normally before the caller raises. Two tests failed before
  the fix; all pass after.
- **Factory finding:** in template-8 GRIB, `dataDate` must be set before the step, otherwise the end-of-interval (validity)
  time stays stale. Added as a validation test (inconsistent validity rejected).
- **Test results:** 103 passed (26 new).
- **Real run:** latest complete run 20261111T00Z (12 Nov 00z not yet published at 21:46 UTC); 35,139,859 bytes in 66 s;
  validation passed (68 messages; increments 0, 0.061, 0.122, 0.244 mm). SHA-256 `6de90b3f…` is **identical to the
  independent manual download (D-007)**. Pre-existing `data/` files byte-identical before/after; no `latest.json` created;
  `data/tmp` empty; nothing rejected. A second run logged "already fetched; nothing to do" and the stored file was unchanged.
- **Limitation:** no real last-good published forecast exists yet (publishing is Step 2), so "last good unchanged" is
  proven by the tests with a simulated last-good run and `latest.json`, and in the real run only for pre-existing files.

## D-017: Pipeline Step 2, compute + build JSON + check + publish
- **Timestamp:** 2026-11-12
- **Status:** Implemented and tested; real run published
- **Files:** `pipeline/publish.py`, `tests/test_publish.py` (19 tests).
- **Behaviour:** verify the run's GRIB checksum against its manifest → read the 391 region points (ecCodes) → per point,
  `compute.py` intervals/days with per-step packing increments → any `invalid` blocks publication → JSON (J1) → checks:
  required fields; exact set of grid points; 11 days / 67 intervals spanning start→258 h without gaps; durations (3 h to
  144 h, then 6 h; days end 23:30 IST, first partial); status rules (ok: mm = raw ≥ 0; adjusted: mm 0, raw within
  threshold; unavailable: nulls + reason); rates = mm/hours; day = sum of intervals (exact); **independent spot check**
  of 3 points (first, middle, last) recomputed from the GRIB by a separate simple reader; older-than-published run refused.
  Then write `<run>.json.tmp` → `os.replace` → `<run>.json`, same for `latest.json`. Re-publishing the same run is a no-op.
- **Tests:** written first (collection error before code), 19/19 passed on first implementation. Mutation check:
  disabling the spot check failed exactly its test; disabling the threshold check in the JSON failed exactly its test;
  code restored (hash identical). Full suite **122 passed**.
- **Real run:** `python -m pipeline.publish data\runs\20261111T00Z` → 391 points, **4,270,791 bytes** (compact JSON;
  above the earlier 3–4 MB estimate), 6 s, quality ok, adjusted 76 intervals / 32 days, unavailable 0.
  `20261111T00Z.json` = `latest.json` (identical hash).
- **Worked check, Chennai grid point 13.00,80.25, 20 Nov:** GRIB 0-234 h = 0.02587890625 m, 0-210 h = 0.013916015625 m →
  25.87890625 − 13.916015625 = **11.962890625 mm** = JSON `raw_mm`, and matches D-007's independent verification.
- **Inconsistency flagged for the owner (not changed):** D-006 6.4 says to publish valid periods and mark the two days
  around a missing boundary step unavailable. Step 1 (owner instruction, D-016) rejects any run that lacks a step, so in
  practice the partial-publication path cannot occur. The code supports it (tested in `compute.py`). Current effective
  behaviour is the stricter "reject the whole run, keep the previous forecast". **Owner decision needed.**

## D-018: Partial publication when a step is missing; 00 UTC only (supersedes D-016's whole-run rejection)
- **Timestamp:** 2026-11-11 22:53 UTC (2026-11-12 04:23 IST)
- **Status:** Decided (owner). **Not implemented yet** (change list below).
- **Context:** D-006 6.4 said to publish valid periods and mark the two days around a missing boundary step unavailable.
  D-016 (Step 1) rejects any run lacking a step, so 6.4 could never take effect (flagged in D-017).
- **Decision (replaces 6.4 and the missing-step rejection in D-016):** partial publication.
  - Principle: **don't discard valid information because other information is unavailable, and never present
    unavailable information as valid.**
  - Still validate every available file; verify all readings belong to the same run and the same grid.
  - Still **reject runs that are corrupt or inconsistent** (unreadable or truncated GRIB, wrong variable or units,
    window not from step 0, other run, grid mismatch, duplicates, unexpected steps, missing or negative stored values,
    unknown packing).
  - A **missing step** no longer rejects the run. Only the periods that need it are marked `unavailable` (null, never 0,
    with a reason): a missing day-boundary step affects its two adjacent days; any missing step affects its two intervals.
- **Run frequency:** **00 UTC only** for now. Adding 12 UTC runs is **deferred**, only if time allows after deployment.
- **Owner's reasoning:** farmers need fresh data. The assistant's evidence that a missing file is most likely a delivery
  problem is a hypothesis, not proof that the rest of the run is correct, hence keep validating everything that is
  available. Partial publication already avoids farmers being stuck with very old forecasts, and staying on 00 UTC
  keeps the work small before the deadline.
- **Differs from the assistant's recommendation:** the assistant's first choice was "add 12 UTC runs and keep the strict
  rule" (a rejection would then cost ~12 h of freshness instead of ~24 h). For a 00 UTC-only setup, the assistant had
  advised partial publication, which matches this decision. The assistant also conceded that its earlier claim
  ("a missing step makes the other days untrustworthy") was an assumption without evidence.
- **Staleness (from D-016/D-017 observations, one publication time 07:34 UTC):** 00 UTC only, normal worst ~31.5 h; with
  partial publication a delivery gap no longer forces a ~55.5 h-old forecast.
- **Open questions to settle before implementing (assistant proposals in brackets):**
  1. When is a run treated as "partial" rather than "still uploading"? [accept missing steps only after init + 10 h,
     i.e. ~2.5 h after the observed 07:34 UTC completion; before that keep waiting]
  2. Minimum content to publish at all? [at least one complete day available; otherwise keep the previous forecast]
  3. May a later complete download of the same run replace a partial one? [yes, only if it has fewer missing steps]

## D-019: Partial publication deferred until after deployment
- **Timestamp:** 2026-11-12
- **Status:** Decided (owner)
- **Decision:** implementing D-018 (partial publication) is **deferred until after deployment**. Until then the strict
  rule from D-016 stays live: a run with any missing step is rejected and the previous validated forecast stays
  published (clearly dated). D-018 remains the agreed target behaviour and is the **first enhancement after deployment**.
- **Owner's reasoning:** deployment is the bigger risk to the deadline, and a missing step has never been observed
  (every run checked so far had all 68 steps).
- **Estimates given (assistant, not measured):** minimal partial publication ~1–1.5 h; replacing a partial run with a
  later complete one (D-018 Q3) +~45 min. Q3 is to be deferred even when D-018 is implemented.
- **Still open for when D-018 is implemented:** D-018 Q1 (waiting period before accepting missing steps), Q2 (minimum
  content to publish).

## D-020: Step 3, read-only API
- **Timestamp:** 2026-11-12
- **Status:** Implemented and tested; real server run verified
- **Files:** `api/app.py` (FastAPI, `create_app(latest_path)`), `tests/test_api.py` (18 tests). New **dev-only**
  dependency: `httpx` 0.28.1 (+ `httpcore`), required by FastAPI's TestClient; pinned in `requirements-dev.txt`, not in
  the runtime `requirements.txt`.
- **Behaviour:** loads `latest.json` into memory and reloads when its identity (mtime, size, inode) changes.
  `GET /api/forecast?lat&lon`: lat in [-90, 90], lon in [-180, 180], NaN and inf rejected (422). The location must be
  inside the published region box (box from the JSON, unchanged by the grid margin), else 404. Snaps north/east via
  `pipeline.grid.snap_to_grid`. Returns the stored point's days and intervals unchanged, plus run, units, attribution,
  day definition, quality, region, requested and grid coordinates. 503 if nothing has been published.
  `GET /api/status`: live run, age in hours, quality, point count, last reload error. A broken new `latest.json` keeps
  the previous forecast in service, and the error is reported in status.
- **Tests:** written first (collection error before code), 18/18 passed. Mutation check: disabling the region check failed
  the 3 outside-region tests; restored (hash identical). Full suite **140 passed**. Known warning: Starlette says the
  `httpx` TestClient backend is deprecated in favour of `httpx2` (test-only; no effect on the API).
- **Real run** (uvicorn, real `latest.json`): status 200, run 2026-11-11 05:30 IST, **age 37.78 h**, 391 points, quality ok.
  Chennai (13.0825, 80.275) → grid point 13.00, 80.25, 11,833-byte response, daily mm identical to D-017. Coimbatore
  ×20 requests: median 4.4 ms, max 5.9 ms (local HTTP round trip). Kolkata → 404; `lat=abc` → 422; `lat=95` → 422.
- **Observation:** the live forecast is 37.8 h old because nothing fetches new runs automatically yet. The scheduler
  step must fix that.

## D-021: Deployment architecture (option A)
- **Timestamp:** 2026-11-12
- **Status:** Decided (owner); implementation starting
- **Decision:** the pipeline runs on **GitHub Actions** (scheduled ~08:30, 11:30, 14:30 UTC + manual start). The published
  forecast is served from **GitHub Pages** (deployed from a workflow artifact, never committed to git). The API runs on a
  **Render free web service** and downloads `latest.json` from Pages (no local state).
- **Owner's reasoning:** keeps the heavy pipeline and the always-on API separate, survives restarts, and a failed run never
  replaces the last good forecast (a failed workflow does not deploy Pages).
- **Rejected:** everything on Render (free disk is wiped on restart; free tier has no scheduled jobs; sleeping stops an
  in-process timer); Hugging Face Spaces (needs Docker; storage not persistent); PythonAnywhere free (outbound access
  restricted to approved sites; believed to exclude ECMWF); Fly.io/Railway (believed no longer free). Free-tier facts
  are from the assistant's knowledge and are re-checked at setup.
- **Owner actions:** enable GitHub Pages (source: GitHub Actions); create the Render account. The assistant provides
  click-by-click steps.
- **Known trade-offs:** Render free sleeps after inactivity (~30–60 s first response); Actions schedules can start late.

## D-022: Pipeline deployed on GitHub Actions + Pages (verified)
- **Timestamp:** 2026-11-12 15:38–15:46 UTC
- **Status:** Live and verified
- **Setup:** owner enabled Pages (source: GitHub Actions); confirmed via API (`build_type: workflow`). Workflow
  `.github/workflows/pipeline.yml` (actions: checkout v7, setup-python v7, upload-artifact v7, upload-pages-artifact v5,
  deploy-pages v5, versions looked up from GitHub at setup time).
- **Run 43250043754 (manual, normal):** ecCodes 2.50.0 loads on the GitHub Linux runner ("Your system is ready");
  **155 tests passed** there. No forecast was published yet, so it fetched the newest complete run **20261112T00Z**:
  34,466,914 bytes in 47 s, 68 messages validated, SHA-256 `1fbb55d1…`. Published 391 points, 4,164,510 bytes,
  quality ok (adjusted 145 intervals / 63 days, 0 invalid). Pages deployed.
  - Run-to-run precision differs as predicted (D-014): this run includes increment 0.0305 mm (E = −15), absent in 20261111T00Z.
- **Published file:** `https://basumrittika810-arch.github.io/rain-forecast/latest.json` → HTTP 200, 4,164,510 bytes,
  run 2026-11-12 05:30 IST, same source SHA-256, 391 points; ETag `"6af5de12-3f8b9e"`. Index page HTTP 200.
- **Run 43250610272 (manual, normal, same run already published):** "nothing to do", outcome `unchanged`, no download,
  deploy skipped.
- **Run 43250883126 (manual, simulated failure):** forced corrupt download → `ValidationError: no GRIB messages in file`.
  Run concluded **failure**; rejected download kept as artifact `rejected-downloads`; deploy skipped. Pages ETag
  **unchanged** (`"6af5de12-3f8b9e"`), still run 2026-11-12. **A failed update did not replace the last good forecast.**
- **Note:** GitHub annotation: the `ubuntu-latest` label is migrating to Ubuntu 26 (since 19 Oct 2026). Runs pass;
  pinning a fixed runner image is an option if it ever causes problems.
- **Next:** API on Render via `render.yaml` Blueprint (free plan, Singapore, Python 3.12.10, FORECAST_URL → Pages,
  health check `/api/status`).

## D-023: API deployed on Render (verified)
- **Timestamp:** 2026-11-12 ~17:50 UTC
- **Status:** Live and verified; **restart test still pending** (owner action)
- **Setup:** owner created a Render account and applied the `render.yaml` Blueprint (name `rain-forecast`, branch `main`).
  Service `rain-forecast-api`, plan Free, deployed commit `2799195` in 59 s. Public address:
  **https://rain-forecast-api-qii4.onrender.com** (Render added the suffix `-qii4`; the plain name was not available).
- **Smoke test** (`scripts/smoke_test.py` with `--published-url` = the Pages `latest.json`): **20/20 passed**. Run 2026-11-12 05:30 IST,
  17.86 h old, quality ok (adjusted 145 intervals / 63 days), Chennai → grid 13.00, 80.25, values **identical to the published
  file**, Kolkata → 404, `lat=abc` → 422. `/api/status` reports `"source": "url"`; `/docs` HTTP 200. The owner also tested via `/docs`.
- **Observation:** the bare address `/` returns 404 `{"detail":"Not Found"}`, because no page exists there yet; the web page (Step 4) will live there.

## D-024: Place-name search (option A) + "use my location" (option D)
- **Timestamp:** 2026-11-12 ~18:30 UTC
- **Status:** Decided (owner); evidence below; **building A awaits answers to the open questions**; D is built in Step 4 (website)
- **Context:** farmers do not know coordinates. The owner wants them to type a place name; turning it into coordinates happens
  in the backend. A farmer may want the forecast for a place where they are not present (e.g. their field), so GPS alone is not enough.
- **Decision:**
  - **A:** our own stored list of Tamil Nadu places with coordinates, searched by a new API endpoint. No outside service at request time.
  - **D:** a "use my location" button on the website (Step 4), as a shortcut.
  - Search uses **English spellings for now**; Tamil script is to be checked later.
  - Results **show the district**, so places with the same name can be told apart.
- **Rejected:** B (online geocoder per search: rate limit ~1 request/s, outage risk, searches go to a third party, paid keys for
  commercial services); C (District → Taluk → Village dropdowns: same data need as A, more taps, more work).
- **Evidence, place list** (`scripts/inspect_places.py` → `docs/inspection/places_geonames_20261112.txt`). Source: GeoNames
  `IN.zip`, CC BY 4.0 (attribution "GeoNames" required), downloaded 2026-11-12, SHA-256 `fa6d874b…`.
  - Tamil Nadu (admin1 code 25): 46,004 records; **40,444 populated places** (class P). By code: 39,876 PPL, 291 PPLQ (abandoned),
    249 PPLX (section of a place), and a few others.
  - **Mostly villages:** only 1,068 have a population figure (1,066 ≥ 1,000; 501 ≥ 15,000). The other ~39,400 have none, which
    in this file typically means small villages. The random sample below supports this (Verified for the sample only).
  - **District:** 40,281 of 40,444 have a district code that resolves to one of **38 district names** (all current districts,
    incl. the newer ones such as Ranipet and Tenkasi). 163 have no district.
  - **Name quirks:** two names need cleaning for display: "Tirunelveli Kattabo" (a truncated name; display "Tirunelveli"), and
    9 names ending in " district".
  - **Same name, different districts:** 3,206 of 28,006 distinct names occur in more than one district (e.g. Virapandi in 6
    districts; Melur in Madurai, Chengalpattu ×2, Dharmapuri). Showing the district is therefore necessary, but **not always
    enough**: the same name can occur twice in one district.
  - **Common alternative names are included:** Trichy → Tiruchirappalli, Udhagamandalam → Ooty.
  - **Tamil script:** only **143 of 40,444** (0.35 %) carry a Tamil-script name, so this file **cannot support Tamil search**.
    Another source would be needed (open).
  - **Forecast box:** 40,432 inside; **12 outside** by ≤ 0.02° (Kanniyakumari southern tip, Thiruvallur coast, Nilgiris western
    edge). All 12 snap to stored grid points, but `/api/forecast` refuses locations outside the box.
- **Evidence, coordinates vs a second source** (OpenStreetMap Nominatim, 30 places: 20 villages without population + 10 towns
  ≥ 15,000, fixed random seed; `docs/inspection/places_crosscheck_osm_20261112.txt`):
  - **Name search:** OSM found only 8/30 by name, because spellings differ (GeoNames "-kavundan-" vs OSM "-goundan-",
    "Soviriyampatti" vs "Soriyampatti"). All 8 found lie **0.03–1.11 km** from GeoNames, in the **same forecast grid cell**.
  - **Reverse lookup** (which place and district lie at the GeoNames coordinate):
    - State: Tamil Nadu 30/30.
    - District: **29/30 agree** (allowing spellings Sivagangai/Thoothukudi). The exception is Nalambur: GeoNames says
      Thiruvallur, OSM says Chennai District (near Ambattur, on the district border).
    - Place name: about 10/30 match or nearly match (e.g. Valavettikuppam, Kidarakulam, Vazhapadi, Omalur). The rest name a
      neighbouring village or town, which is consistent with nearby coordinates but **not proof** of village-level accuracy.
  - D-010 towns compared with Wikipedia coordinates: Chennai, Coimbatore and Madurai are each within ~0.7 km of GeoNames.
  - **Conclusion (Verified for the sample, not the whole list):** coordinates are consistently in the right state and district
    and near the named place. One grid cell (~27 km) is much larger than the observed differences (≤ 1.1 km), so the list is
    precise enough for a 0.25° forecast. Village-level precision is not proven.
- **Probe for the owner's choices** (`scripts/probe_places.py` → `docs/inspection/places_probe_20261113.txt`):
  - **No-district places are often not in Tamil Nadu:** the sample contains Bellandur and Hulimavu (Bengaluru, Karnataka),
    Bahur, Saram and Tiruvandarkovil (Puducherry), and Parassala (Kerala), all wrongly tagged as Tamil Nadu by GeoNames.
  - **Abandoned (PPLQ):** e.g. Bekuppa, Gerhatti, Kottayur (many near Hosur). 88 of 283 names also exist as a living place,
    so they would appear as confusing duplicates. Whether "abandoned" is still true is GeoNames' claim, not checked.
  - **Sections (PPLX):** city neighbourhoods such as Thyagaraya Nagar, Padmanabha Nagar, Jeeva Nagar North (Chennai).
  - **Outside the box:** by 0.01–2.1 km only. Two of the 12 (Vellara, Cholatipuzha) have no district and are dropped anyway.
    The remaining **10 have a district**; all of them snap to grid points that are already stored. Box needed to cover all
    kept places: lat ≥ 8.08206, lon 76.24385–80.34498.
  - **Spelling, 12 hand-picked variants (indicative, not random):** start of name + GeoNames alternative names found 7/12;
    adding close-spelling suggestions (Python `difflib`, cutoff 0.8) found 11/12. Valavettikuppam was not found (GeoNames
    has "Valavettikkuppamtattanur"). Suggestions include lookalikes (e.g. Kidarakulam → Kidarikulam, Kodarankulam, Kidarangulam).
- **Owner decisions (2026-11-13), with reasons:**
  1. **Storage: the cleaned place list is committed to Git**, built by a script from the GeoNames download (checksum recorded).
     Reason: the "no data in the repo" rule exists to protect privacy and prevent data leaks; this is public geography data, so
     it is a deliberate, limited exception. Raw GeoNames downloads stay in git-ignored `data/`.
  2. **Places: drop abandoned (PPLQ) and places without a district.** Reason: the evidence showed the no-district places are
     often in other states, so keeping them would mislead farmers. Sections (PPLX) are kept.
  3. **Edge places: widen the region box slightly** to lat 8.08–13.583333, lon 76.24–80.35 (was 8.083333 / 76.25 / 80.333333).
     Reason: if a forecast exists for a village, the farmer should be able to see it. Documented in the config as "official
     boundary (TNAU), extended slightly". Stored grid points stay 391 (to be confirmed by tests). The published forecast
     carries its box, so the API accepts the wider box from the next published run onwards.
  4. **Spelling: smart search with "did you mean".** Exact and start-of-name matches (names and alternative names) first; if
     none, close-spelling suggestions, clearly marked as suggestions, always with the district. Reason: seeing a few wrong
     suggestions the farmer can skip is better than finding nothing.
- **Differs from the assistant's first recommendation:** Q2. The assistant first recommended keeping no-district places, then
  changed the recommendation after the probe found places from other states among them.
- **Implementation (2026-11-13):**
  - **Files:** `pipeline/places.py` (build / load / search; standard library only), `config/places_tamil_nadu.csv`
    (2,156,648 bytes) + `config/places_tamil_nadu.source.json` (IN.zip SHA-256 `fa6d874b…`), `GET /api/places?q=&limit=`
    in `api/app.py`, region box widened in `config/settings.toml`.
  - **Tests:** `tests/test_places.py` + updated config/grid tests, written first. The new tests failed before the code existed
    (collection error; 12 config/grid failures).
  - **Built list:** **39,997 places = the hand count** (40,444 − 291 − 163 + 7). Raw IN.zip SHA-256 unchanged.
  - **Two test expectations were wrong, not the code:**
    - A float comparison needed a 1e-6 tolerance (13.583333 vs 13 + 35/60).
    - GeoNames has its own small "Trichy" entry (Tiruchirappalli district, 1.4 km from the city point). It ranks before the
      city's nickname match, and both snap to the same forecast point 10.75, 78.75. Both tests were corrected.
  - **Result:** full suite **214 passed**.
  - **Mutation check:** keeping abandoned places failed the builder test; disabling "did you mean" failed 3 tests. Code
    restored (hash identical).
  - **Stored grid points:** still 391 with the wider box (test).
  - **Local server:** name matches 7–54 ms, suggestions ~120 ms.
- **Known limits (open, not fixed):**
  - The same name can occur twice in one district with identical labels, e.g. Melur (Chengalpattu) ×2. Those two snap to the
    same forecast point, but this is not guaranteed in general.
  - "T Nagar" is not found: GeoNames has "Thyagaraya Nagar" without that short form.
  - Valavettikuppam is not found (as in the probe).
  - Some alternative names are machine transliterations from other scripts (e.g. "trwchraply"); harmless, but they may
    appear as the "matched" spelling.
  - The wider box reaches the live API only with the next published forecast, because the API takes the box from the
    published JSON.
- **Owner decision (2026-11-13): ranking rule kept.** Among exact matches, an exact *name* ranks before an exact *alternative
  name*, then bigger places first (e.g. "trichy" → the small GeoNames entry "Trichy" before Tiruchirappalli city). Reason:
  both results give the same forecast (same district, same grid point 10.75, 78.75), so a change is not worth it before
  the deadline. The rejected alternative was "bigger place first among all exact matches", which would also let a big town
  outrank a village whose real name matches exactly.

## D-025: Restart test for the Render API satisfied by redeploy
- **Timestamp:** 2026-11-13
- **Status:** Verified
- **Evidence:** pushing `cf224f6` made Render replace the running instance with a new one (a full redeploy, which covers
  a restart). Within ~80 s the new instance served `/api/places`. It loaded the forecast from GitHub Pages again (run
  2026-11-12 00 UTC) and the smoke test passed **20/20** with values identical to the published `latest.json`.
- **Conclusion:** the API keeps no state on Render; after a restart it serves the same published forecast. A manual
  "Restart service" was offered to the owner as optional and not needed.

## D-026: Website (Step 4) display decisions
- **Timestamp:** 2026-11-13
- **Status:** Decided (owner); plan below; not implemented yet
- **Decisions:**
  1. **Messages describe the rain only** (amount, category, when in the day, how certain, missing data). No farming advice:
     "farming decisions are the farmer's to make" (consistent with D-000).
  2. **Rain categories: IMD's**, used only once verified against an official IMD source and cited.
  3. **Rounding: 1 decimal; tiny amounts shown as "< 0.1 mm"**, because "0.0" would wrongly look like no rain. Raw values
     stay unchanged in the data; this is display only. Adjusted values (D-008, shown as 0) are not "tiny amounts".
  4. **Old-forecast warning after 36 hours.** Reason: a normal daily update keeps the forecast fresher than that (worst
     normal case ~31.5 h, D-018), so 36 h means an update was missed.
- **Plan (assistant, accepted as the skeleton):** search box + place list (D-024), "use my location" button, a 10-day bar
  chart coloured by category, one row per day with amount + message, tap a day for its 3-/6-hour chart, forecast age,
  ECMWF and GeoNames attribution. Category and message are computed in Python (tested) and added by the API; the page only
  displays them. Charts are drawn as plain SVG by our own code (no chart library). Served by the Render API at `/`.
- **Order:** (1) categories + messages, (2) page skeleton, (3) charts, (4) checks (phone width, slow network, smoke test,
  screenshot); a commit after each.

## D-027: IMD rainfall categories verified (source evidence)
- **Timestamp:** 2026-11-13
- **Status:** Verified from official IMD documents; **how to apply them awaits owner decisions** (listed in the session)
- **Sources** (PDFs in git-ignored `data/imd_sources/`; verbatim extracts in `docs/inspection/imd_rain_categories_20261113.txt`):
  1. IMD, *Standard Operation Procedure – Weather Forecasting and Warning Services*, Ministry of Earth Sciences, 2021
     (https://mausam.imd.gov.in/imd_latest/contents/pdf/forecasting_sop.pdf, SHA-256 `f5330b3a…`): §1.7.2 Table 1.5
     "Terminology for intensity of 24 hour accumulated rainfall" (PDF p. 25); §5.2.1 Table 5.2 (PDF p. 110).
  2. IMD RSMC New Delhi, *FAQ on Tropical Cyclones and Marine Weather Services*, Q93
     (https://rsmcnewdelhi.imd.gov.in/images/pdf/faq.pdf, SHA-256 `7c772d6a…`), PDF p. 31.
- **Categories (mm per 24 h), identical in all three tables:**

  | Category | mm |
  |---|---|
  | Very light | Trace – 2.4 |
  | Light | 2.5 – 15.5 |
  | Moderate | 15.6 – 64.4 |
  | Heavy | 64.5 – 115.5 |
  | Very heavy | 115.6 – 204.4 |
  | Extremely heavy | ≥ 204.5 |

  The FAQ adds "No rain: 0.0".
- **Differences between the documents:**
  - Extremely heavy: SOP Table 1.5 says "Greater than or equal to 204.5 mm"; the FAQ says ">204.5".
  - "Exceptionally heavy" applies only above 12 cm (Table 1.5, FAQ) or 24 cm (Table 5.2). It is defined relative to the
    station's own record, which we do not have.
- **Context stated by IMD:**
  - The categories describe **24-hour accumulated rainfall at a station**: "range of daily rainfall of a station",
    "for the past 24 hrs ending at 0830 hrs IST" (Table 5.2).
  - Trace: "less than 2.5 mm in monsoon season and less than 0.1 mm in other seasons in a subdivision" (§1.7.1 note, used
    for describing a subdivision as "mainly dry").
- **Differences from our data (affect how categories are applied):**
  - Our values are ECMWF **grid-box** amounts (~27 km square), not a station measurement.
  - Our day is 23:30→23:30 IST (D-006), not 08:30→08:30.
  - Our first day is partial (18 h).
  - Our values have more than one decimal, whereas IMD's bands are written to one decimal.
- **Process note:** the assistant's web-fetch tool could not open the PDFs (one >10 MB, one HTTP 403), so they were
  downloaded with curl and read with pdftotext's table mode (the default layout mode had scrambled the table columns).
- **Owner decisions (2026-11-13), with reasons:**
  1. **Classify the rounded number shown** (1 decimal): if the screen shows "2.5 mm" the label says "Light", so the word always
     matches the number the farmer sees.
  2. **Today gets a label too** (e.g. "Light") although it covers only 18 h: it is the day the farmer cares about most. The day
     row still says it is partial (D-006).
  3. **Add an "area average" sentence:** our number covers an area about 27 km wide, not the farmer's exact field, so nobody
     should treat it as a promise for their exact spot.
  4. **"Exceptionally heavy" is not used** (needs station records; IMD documents disagree: 12 vs 24 cm).
  5. **Exactly 204.5 mm = extremely heavy** (SOP 2021 Table 1.5, "greater than or equal to 204.5 mm").
- **Source for the area sentence (Documented):** ECMWF Forecast User Guide (Cy50r1), Section 9.5 Large Scale Precipitation
  and Section 9.6 Convective Precipitation: "Precipitation is the grid box average value, not a point value." Section 9.6:
  "Localised extreme values in precipitation totals are systematically underestimated in IFS output because of the
  resolution". Section 8.1.7 Point rainfall gives an example box: "whilst the gridbox average rainfall total is about 17mm,"
  "the minimum and maximum rainfall amounts are about 2mm and 60mm respectively." (confluence.ecmwf.int/spaces/FUG, pages
  673551727, 673551728, 673551197; read 2026-11-13)
- **Implementation (2026-11-13):**
  - **Files:** `pipeline/messages.py`; `/api/forecast` adds `shown`, `category`, `label` and `message` to each day, `shown` to
    each interval, plus `area_note` and `category_source`. The published JSON is unchanged.
  - **Owner-approved details:** true zero is shown as "0 mm", tiny amounts as "< 0.1 mm". Timing names the parts of the
    day (night 23:30–05:30, morning, afternoon, evening IST) whose shown rain is ≥ 0.1 mm. No "less certain further ahead"
    note, because no source has been found for where it should start.
  - **Tests:** `tests/test_messages.py` (53, written first; collection error before the code existed). The API equality test
    and the smoke test now check that every published field is returned unchanged and that the only additions are the
    display fields (stricter than before).
  - **One test expectation was wrong:** a 2.0 mm day was expected as "Light"; IMD says very light (≤ 2.4). The test now uses
    3.0 mm.
  - **Result:** full suite **267 passed**.
  - **Mutation check:** light starting at 2.6 failed 2 tests; halves-to-even rounding failed 7; tiny amounts shown as
    "0.0 mm" failed 3. Code restored (hash identical).
  - **Real data** (published run 2026-11-12, local API reading Pages): smoke test 21/21. Example, Chennai 13 Nov:
    "1.6 mm | Very light | Very light rain expected, through the day."

## D-028: Website "Vaanam" (Step 4, page + charts)
- **Timestamp:** 2026-11-13
- **Status:** Implemented and tested; checked in a real browser at phone width
- **Owner decisions:**
  - Name **"Vaanam"** (Tamil for "sky"); title "Vaanam: Rain Forecast for Tamil Nadu".
  - Design list given by the owner: search, "Use my location", name + district, forecast time, day and area notes, IMD
    labels + messages, missing days never shown as no rain, 36 h warning, wake-up note, charts, credits, rain only.
  - Calm blues / sky blue / green. IMD categories go from pale sky blue to deep blue, green for no rain, and always carry
    their word.
  - **Watermark:** a simple Tamil Nadu outline drawn in our own code, faint, so the text above stays clear.
- **Files:** `web/index.html`, `web/app.js`, `web/style.css`, `web/tn-outline.svg` (29 KB in total), served by the API
  at `/` (mounted after all API routes). `scripts/make_outline.py` builds the outline from Natural Earth 1:50m admin-1
  "Tamil Nadu" (public domain; raw file in git-ignored `data/naturalearth/`, SHA-256 `69a0e06e…`).
- **Outline check (decoration only, nothing computed from it):** Chennai, Coimbatore and Madurai are inside; Kolkata,
  Bengaluru and Thiruvananthapuram are outside; 39,760 of 39,997 listed places (99.4 %) are inside. Puducherry also falls
  inside, because the 1:50m outline is simplified.
- **New endpoint `/api/places/nearest?lat&lon`:** names a GPS position as "Near <place>, <district> district", so the
  page never shows coordinates. If no name can be found, the page says "Your location".
- **Presentation choices made by the assistant (owner's rule: decide and log):**
  - Days already over are hidden. The day containing "now" is marked "Today".
  - The partial first day's label gets " (18 hours)" (owner's list). The day note mentions the partial day only while
    that day is still shown.
  - Bar labels use the shown amount without "mm" ("0", "< 0.1", "2.7"). The chart scale is the next of 5/10/25/50/100/150/
    250/400 mm above the largest day, so tiny rain is not exaggerated. No rain is drawn as a thin green line at the base.
    A missing day is drawn as a dashed empty box with "no data", never as 0.
  - 3-hour chart: one bar per block with its start time in IST, plus the note "Rain can fall at any time within a block"
    (D-006). Blocks use one blue (IMD categories are 24-hour terms), green for 0 and grey for missing.
  - Wake-up note after 3 s of waiting; requests give up after 90 s with a "Try again" button. Search runs 0.4 s after
    typing stops (at least 2 letters). The result list folds away once a place is chosen.
  - Location messages: denied, unavailable, too slow, not supported and outside Tamil Nadu each say what happened and
    point to the search box.
  - Animation: bars grow, cards fade in, the title raindrop moves slightly. All of it is switched off when the phone asks
    for reduced motion.
  - Fonts are the phone's own system fonts (no download). Tap targets are at least 48 px.
- **Tests:** `tests/test_web.py` (33, written first; 32 failed before the files existed):
  - the page and its files are served; `/api` and `/docs` are not hidden behind the page;
  - all required texts are present; the 36-hour rule; every category has a colour class and a word;
  - no farming-advice words; nothing loaded from other sites; page weight under 60 KB; phone viewport;
    reduced-motion support;
  - the nearest-place function and endpoint (including real Chennai at 0 km).
  - **Result:** full suite **300 passed**.
- **Browser check** (Edge, headless, 360 × 780, local API reading the published forecast; Playwright in a throwaway
  scratch environment, not a project dependency):
  - search "melur" lists every Melur with its district; "kidarakulam" gives "Did you mean…?" with districts; "zzqqxx"
    gives "No place found…"; "m" asks for 2 letters;
  - location denied gives a polite message; Kolkata gives "outside Tamil Nadu"; a Madurai position gives "Near Sellur,
    Madurai district" with no coordinates on screen.
  - No page errors. The only console line is the expected 404 for the Kolkata forecast request.
  - **Fixed after looking at the screenshots:** larger chart text; result list folds away; background band removed;
    3-hour bar colours (an SVG attribute ignored CSS variables).
- **Limits:** the JavaScript has no automated unit tests (no Node.js here). The slow-server wake-up state has not been seen
  live yet. Not yet tested on a real phone (owner to test).

## D-029: Rain colours changed to yellow → orange → red
- **Timestamp:** 2026-11-13
- **Status:** Implemented and tested; checked in a real browser at phone width
- **Owner decision:** rain colours go from light to orange to red as rain increases, with the most rain in red. This
  replaces the blue shades of D-028. Green for no rain and grey hatching for missing days stay the same; every colour
  still has its word next to it.
- **Colours (chosen by the assistant, owner's rule: decide and log):**

  | Category | Colour | Text on it | Text contrast |
  |---|---|---|---|
  | No rain | `#3fa36b` green | dark `#06213a` | 5.2 : 1 |
  | Very light | `#fde9a9` pale yellow | dark `#10304a` | 11.3 : 1 |
  | Light | `#fbd05c` yellow | dark `#10304a` | 9.3 : 1 |
  | Moderate | `#f5a33a` amber | dark `#06213a` | 7.9 : 1 |
  | Heavy | `#e8641c` orange | dark `#06213a` | 4.9 : 1 |
  | Very heavy | `#c62a1a` red | white | 5.6 : 1 |
  | Extremely heavy | `#7f0d10` deep red | white | 10.7 : 1 |

  - Hue moves from yellow (46°) to red (358°), and each step is darker than the one before.
  - **Fixed along the way:** the "No rain" chip had white text at only 3.2 : 1, below the WCAG AA level of 4.5 : 1. It
    now uses dark text.
  - **3-hour blocks** now use the site blue for any rain. They used the "moderate" colour, which would now look like an
    orange "Moderate" label. IMD categories are 24-hour terms (D-028), so blocks must not look like a category.
- **Note:** IMD's own warning colours (green / yellow / orange / red) measure expected impact, not rain amount. Our
  colours show the amount category only, and the word is always printed.
- **Tests (written first; all 3 failed on the old colours):** colours go yellow → red and get darker, and the last one
  is clearly red; every category word reaches 4.5 : 1 contrast on its colour; 3-hour blocks use no category colour.
  **Full suite: 303 passed.**
- **Browser check** (Edge, 360 px):
  - real forecast for Melur;
  - a display-only demo where the browser altered the forecast so all seven categories appear once (nothing stored or
    published was changed);
  - no page errors.

## D-030: IMD warnings note, wider layout on computers, clearer map, darker blue
- **Timestamp:** 2026-11-13
- **Status:** Implemented and tested; checked in a real browser on a phone-size and a laptop-size screen
- **Owner decisions:**
  - Under the app name: "Colours show forecast rain amounts, not official warnings. For official weather warnings, see
    IMD (mausam.imd.gov.in)." The address is a link that opens IMD's site in a new tab. Checked on 13 Nov: IMD's site
    answered "200 OK".
  - On wide screens, the forecast spreads out instead of one item below another. Phones keep one column, because that
    is what fits a phone screen.
  - The Tamil Nadu map in the background is bigger and easier to see.
  - The blue is darker.
- **How (chosen by the assistant, owner's rule: decide and log):**
  - **Two columns from 900 px wide:** left has the notes, the 10-day chart and the colour key, and stays in view while
    scrolling; right has the day-by-day list. The page is up to 1120 px wide; the search card stays 640 px.
  - **Map:**
    - fills the screen height (`contain`, with 3 % margins);
    - fill opacity 0.10 → 0.16; outline is the new dark blue at 0.5 opacity (was 0.35); line is thinner (0.6 → 0.35)
      because the map is now drawn larger;
    - cards are slightly see-through (white at 86 %, was 93 %);
    - header and footer text get a soft light halo, so the outline crossing them does not blur the words.
  - **Blue:** main `#1f6fc0` → `#1a5ea6` (white text 5.1 → 6.6 : 1); dark `#174f8c` → `#0f3f73` (8.3 → 10.6 : 1).
  - The outline was rebuilt with `scripts/make_outline.py` from the same Natural Earth file. Only the style attributes
    changed; the 147 points are identical (checked in the diff).
- **Test changed:** `test_no_frameworks_or_outside_files` used to forbid any `href="https://…"`. It now forbids loading
  anything from other sites (`src=` and `<link href=…>`). It allows `<a>` links only to `https://mausam.imd.gov.in/`. A
  link the reader taps loads nothing by itself, so the rule's purpose (no outside files) is kept.
- **New tests (written first; all 4 failed before the change):**
  - the note text is in the header, with the IMD link;
  - white on the blue reaches 6 : 1 (dark blue 9 : 1);
  - a wide-screen rule with two grid columns, plus the new page sections;
  - the map is stronger and fills the screen behind everything.
  - **Full suite: 307 passed.**
- **Browser check:** Edge at 360 × 780 and 1366 × 768, search "melur" and open its forecast. No sideways scrolling
  (page width equals screen width). No page errors.

## D-031: New look: header band, tagline, heading font, bigger search box, footer band, darker background
- **Timestamp:** 2026-11-13
- **Status:** Implemented and tested; checked in a real browser on a phone-size and a laptop-size screen
- **Owner decisions:**
  - Tagline under the title: **"Your village's rain, day by day"**, with "Rain forecast for Tamil Nadu" in small text
    below it.
    - Not "hour by hour": the data has 3-hour blocks (days 1–6) and 6-hour blocks (days 7–11), and no hourly values.
  - Day-list hint changed from "Tap a day to see its rain in 3-hour blocks." to "Tap a day to see when the rain is
    expected." The old text was wrong for days 7–11, which have 6-hour blocks.
  - Header band: gradient from deep blue to sky blue behind the title, with white text. "Vaanam" is larger and in a
    friendly heading font.
  - The IMD note moves from under the title to just below the colour key, in smaller text, so the search box is the
    first thing people use. Wording unchanged (D-030).
  - The map must not run behind the title or any text.
  - Softer cards (rounded corners, gentle shadow); a bigger, highlighted search box with a search icon inside.
  - Simple footer band with the credits and a very small "Made by Mrittika".
  - Darker blue page background, so the white cards with the amounts and charts stand out.
- **How (chosen by the assistant, owner's rule: decide and log):**
  - **Heading font: Baloo 2 Bold** (Ek Type), SIL Open Font License 1.1:
    - Latin letters only, 19,436 bytes (SHA-256 `8e7ffc9b…`); licence text in `web/fonts/OFL.txt`;
    - stored with the site (`web/fonts/`), not loaded from Google, so the page still loads nothing from other sites;
    - `font-display: swap`: text appears at once in the phone's own font and switches when the heading font arrives.
    - **Why Baloo 2:** rounded and friendly but plain; it has a Tamil sister font (Baloo Thambi 2) for later. The other
      candidate, Nunito Extra Bold (16.5 KB), was less distinctive.
    - Body text stays in the phone's own font, for readability and size.
    - The font file was downloaded into an empty scratch folder and checked (`wOF2` signature, size) before copying.
  - **Title:** 3 rem on phones (was 2.1), 3.6 rem on wide screens. Header gradient `#0c335e → #1a5ea6 → #3f93d3`.
    - The band's background is opaque, with rounded bottom corners and a soft shadow; the raindrop is light blue.
  - **Search:**
    - box 58 px tall, with a 2 px blue border and a soft glow;
    - magnifier icon drawn inside the box (an inline SVG in the stylesheet, no extra file);
    - placeholder "Village or town", shortened so it is not cut off on a 360 px phone.
  - **Cards:** 20 px corners, two-layer soft shadow, white at 97 % (was 86 %), so readings sit on almost solid white.
  - **Background:** blue gradient `#8fbde3 → #79aedb` (was a very pale sky blue). Not "fixed", because a fixed background
    produced a visible band before (D-028).
  - **Footer:** deep navy band with light text and rounded top corners, pushed to the bottom of the screen on short
    pages. "Made by Mrittika" is 0.7 rem at 80 % opacity.
  - **Map:**
    - outline now white (fill 18 %, line 60 %), to suit the darker background;
    - phones: it sits in the lower part of the screen; computers: in the empty space right of the search card;
    - the header and footer bands are opaque and the cards nearly opaque, so the map shows only in empty space;
    - the light text halo from D-030 was removed because it is no longer needed;
    - outline rebuilt with `scripts/make_outline.py` (style only; same 147 points).
- **Tests:**
  - **New (written first; all 10 failed before the change):**
    - tagline;
    - hint without "3-hour";
    - header band gradient with white text and an opaque background;
    - font stored locally, under 30 KB, licensed, and used for headings;
    - title larger;
    - search box at least 56 px, with an icon and room for it;
    - softer, nearly opaque cards;
    - darker background;
    - footer band with credits and a small maker line.
  - **Changed:**
    - IMD note: now must sit after the colour key, in small text (the owner moved it).
    - Page weight: the old 60 KB rule for page files is kept, plus a new 90 KB limit including the font (about 51 KB
      now).
    - Outside-files check: now also forbids `url(http…)` in the stylesheet.
  - **One check fixed:** my new header test first flagged the band's shadow colour as "see-through". It now checks only
    the background.
- **Browser check:** Edge at 360 × 780 and 1366 × 768, start screen and Melur forecast.
  - No sideways scrolling, no page errors.
  - The map is not behind any text.
  - The title shows in Baloo 2.

## D-032: Title font Arima; background "rain falling on fields" replaces the Tamil Nadu map
- **Timestamp:** 2026-11-13
- **Status:** Implemented and tested; checked in a real browser on a phone-size and a laptop-size screen
- **Owner decisions:**
  - The map in the background is replaced by option F, rain falling on green fields. The owner chose it from six
    previewed options (plain, rain streaks, clouds, fields, kolam dots, rain on fields).
  - Only the title "Vaanam" changes font, to **Arima**. The owner chose it from nine previewed fonts. Other headings
    stay Baloo 2 and body text stays the phone's own font.
- **How (chosen by the assistant, owner's rule: decide and log):**
  - **Arima Bold:** by NDISCOVER, SIL Open Font License 1.1, licence in `web/fonts/OFL-Arima.txt`.
    - Cut to the four letters V, a, n, m: 1,268 bytes. Any other letter shows in Baloo 2.
    - Arima also has Tamil letters, so a Tamil title can match later.
    - Downloaded into an empty scratch folder and checked (`wOF2` signature, size) before copying.
    - Baloo 2's licence file was renamed to `OFL-Baloo2.txt` so each font has its own licence file.
  - **Scene:** a strip between the content and the footer, own drawings in two small SVG files.
    - `scene-rain.svg`: a tile of slanted white raindrops, fading in from the top.
    - `scene-fields.svg`: two green hills; the footer continues the front hill's green `#1e5137`.
    - The strip fills the space left on short pages (at least 170 px), so it is never behind any text.
    - The rain drifts down slowly (1.6 s loop) and is switched off when the phone asks for reduced motion.
  - **Footer:** now green instead of navy, so the fields flow into it. Text `#e6f2ea` on `#1e5137` passes a
    contrast check of at least 7 : 1 (a test enforces this).
  - **Removed:** the map outline (`web/tn-outline.svg`), its builder (`scripts/make_outline.py`) and the "Map
    outline: Natural Earth" credit, because nothing uses Natural Earth any more. Both files remain in git history (D-028).
  - **Browser-tab icon:** a blue raindrop (`web/icon.svg`, own drawing). The map file was the icon before and had become
    white, so it would have been invisible.
  - **Page weight:** all files a phone downloads, including both fonts, total 52854 bytes.
- **Tests:**
  - **Written or changed first; 9 failed before the change:**
    - the new files are served;
    - both fonts are stored with the site and each has its licence file;
    - headings use Baloo 2 and the title uses Arima, which holds only the letters of "Vaanam" and is under 5 KB;
    - the scene sits between the content and the footer, the footer matches the front field, the rain has reduced-motion
      support, and no map remains;
    - the footer text contrast check (already passed with the navy footer; it now guards the green one);
    - the raindrop icon.
  - **Changed:** the footer credits test no longer requires "Natural Earth".
- **Browser check:** Edge at 360 × 780 and 1366 × 768. No sideways scrolling, no page errors. The title shows in
  Arima; rain falls onto the fields above the green footer.
