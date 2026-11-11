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
