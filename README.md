# Rain Forecast (ECMWF IFS HRES Open Data)

Precipitation forecast web application for small farmers in a pilot region of India
(provisionally Tamil Nadu), built on ECMWF IFS HRES Open Data (0.25°, total precipitation `tp`).

Status: **project set up; application not built yet.** Data semantics are verified (see `docs/`).

Data: ECMWF Open Data, licensed CC BY 4.0. Attribution to ECMWF is required.

## Folder structure

| Folder | Contents |
|---|---|
| `pipeline/` | Forecast processing: download, validate, compute rainfall, write JSON (to be built) |
| `api/` | FastAPI app serving the processed JSON (to be built) |
| `web/` | Frontend (to be built) |
| `tests/` | Automated tests, run with pytest (to be built) |
| `scripts/` | One-off investigation and verification tools used to establish the data facts |
| `docs/` | Decision log, inspection and analysis reports, verbatim evidence outputs |
| `data/` | Downloaded GRIB and derived files. **Git-ignored**; raw files are read-only and never modified |

## Setup (Windows, Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # runtime + test tools
.\.venv\Scripts\python.exe -m cfgrib selfcheck                      # expect: "Your system is ready."
```

`requirements.txt` holds the pinned runtime packages (for the server). `requirements-dev.txt` adds pytest.

**Known Windows issue:** with Windows 11 *Smart App Control* enabled, the unsigned compiled
modules of `eccodes` and `pandas` are blocked at import time
(`DLL load failed ... An Application Control policy has blocked this file`).
See `docs/DECISIONS.md` (D-001).

## Useful commands (available now)

```powershell
# Which recent run has tp for the sample steps
.\.venv\Scripts\python.exe scripts\check_availability.py
# Download tp for all steps up to 258 h of a run (refuses to overwrite)
.\.venv\Scripts\python.exe scripts\download_run.py 20261111 00 258
# Verify a downloaded run (metadata, telescoping, negative-difference evidence)
.\.venv\Scripts\python.exe scripts\verify_run.py data\raw\20261111T00Z\tp_steps_0-258.grib2 data\raw\20261111T00Z\manifest_tp_steps_0-258.json data\raw\20261111T00Z\tp_steps_0-3-6-144-150-240.grib2 out.txt
# Run tests
.\.venv\Scripts\python.exe -m pytest
```

Commands for the pipeline, API and web app will be added when they are built.
