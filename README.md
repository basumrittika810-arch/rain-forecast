# Rain Forecast (ECMWF IFS HRES Open Data)

Precipitation forecast web application for small farmers in a pilot region of India,
built on ECMWF IFS HRES Open Data (0.25°, total precipitation `tp`, 10-day horizon).

Status: **setup / data inspection phase**. No forecast processing, API or frontend exists yet.

## Reproducing the development environment (Windows)

Requirements: Python 3.12, Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Verify the ecCodes C library actually loads (installation alone is not proof):
.\.venv\Scripts\python.exe -m cfgrib selfcheck   # expect: "Your system is ready."
```

**Known Windows issue:** with Windows 11 *Smart App Control* enabled, the unsigned compiled
modules of `eccodes` and `pandas` are blocked at import time
(`DLL load failed ... An Application Control policy has blocked this file`).
See `docs/DECISIONS.md` (D-001) for the evidence and the decision taken.

## Repository layout

- `data/` — raw downloaded GRIB files (git-ignored, treated as immutable)
- `docs/DECISIONS.md` — decision log with evidence and verification status
- `requirements.txt` — pinned Python dependencies
