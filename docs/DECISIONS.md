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
