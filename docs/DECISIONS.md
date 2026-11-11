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
