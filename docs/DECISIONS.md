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
