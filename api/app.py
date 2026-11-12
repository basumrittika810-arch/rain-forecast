"""Read-only API over the published forecast (data/processed/latest.json). No calculations happen here.

Endpoints
  GET /api/forecast?lat=..&lon=..   forecast for the nearest grid point (ties north/east) inside the region box
  GET /api/status                   which forecast is live, how old it is, last reload problem (if any)

latest.json is loaded into memory and reloaded automatically when the file changes. If a new file cannot be
read, the previously loaded forecast keeps being served and the problem is reported in /api/status.

Run locally:  .venv\\Scripts\\python.exe -m uvicorn api.app:app --port 8000
"""

import datetime as dt
import json
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from pipeline.config import Region
from pipeline.grid import snap_to_grid

log = logging.getLogger("api")
DEFAULT_LATEST = Path(__file__).resolve().parent.parent / "data" / "processed" / "latest.json"


class ForecastStore:
    """Holds the last successfully loaded latest.json; reloads when the file's identity changes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.doc = None
        self.signature = None
        self.error = None
        self.lock = threading.Lock()

    def _current_signature(self):
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino)

    def get(self):
        sig = self._current_signature()
        if sig is None or sig == self.signature:
            return self.doc
        with self.lock:
            if sig == self.signature:
                return self.doc
            try:
                doc = json.loads(self.path.read_text(encoding="utf-8"))
                doc["run"]["init_utc"], doc["region"]["name"], doc["points"]  # minimal shape check
            except (OSError, ValueError, KeyError, TypeError) as e:
                self.error = f"{type(e).__name__}: {e}"
                log.error("could not load %s; keeping previous forecast: %s", self.path, self.error)
            else:
                self.doc, self.error = doc, None
                log.info("loaded forecast run %s (%d points)", doc["run"]["init_utc"], len(doc["points"]))
            self.signature = sig  # do not retry the same broken file on every request
        return self.doc


def _region(doc) -> Region:
    r = doc["region"]
    return Region(r["name"], r["lat_min"], r["lat_max"], r["lon_min"], r["lon_max"])


def create_app(latest_path: Path = DEFAULT_LATEST) -> FastAPI:
    app = FastAPI(title="Rain forecast API", version="1.0")
    store = ForecastStore(latest_path)

    @app.get("/api/forecast")
    def forecast(lat: float = Query(..., ge=-90, le=90, allow_inf_nan=False, description="latitude, degrees north"),
                 lon: float = Query(..., ge=-180, le=180, allow_inf_nan=False, description="longitude, degrees east")):
        doc = store.get()
        if doc is None:
            raise HTTPException(503, "no forecast has been published yet")
        region = _region(doc)
        if not region.contains(lat, lon):
            raise HTTPException(404, f"location ({lat}, {lon}) is outside the forecast region {region.name} "
                                     f"(lat {region.lat_min:.4f}-{region.lat_max:.4f}, "
                                     f"lon {region.lon_min:.4f}-{region.lon_max:.4f})")
        glat, glon = snap_to_grid(lat), snap_to_grid(lon)
        point = doc["points"].get(f"{glat:.2f},{glon:.2f}")
        if point is None:  # should not happen: grid margin covers the whole box (tests/test_grid.py)
            raise HTTPException(404, f"no grid point stored for ({glat}, {glon})")
        return {
            "requested": {"lat": lat, "lon": lon},
            "grid_point": {"lat": point["lat"], "lon": point["lon"]},
            "run": doc["run"], "units": doc["units"], "attribution": doc["attribution"],
            "day_definition": doc["day_definition"], "quality": doc["quality"], "region": doc["region"],
            "days": point["days"], "intervals": point["intervals"],
        }

    @app.get("/api/status")
    def status():
        doc = store.get()
        if doc is None:
            return {"forecast_available": False, "last_reload_error": store.error}
        init = dt.datetime.fromisoformat(doc["run"]["init_utc"].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - init).total_seconds() / 3600
        return {"forecast_available": True, "run_init_utc": doc["run"]["init_utc"],
                "run_init_ist": doc["run"]["init_ist"], "generated_utc": doc.get("generated_utc"),
                "age_hours": round(age, 2), "quality": doc["quality"], "points": len(doc["points"]),
                "region": doc["region"], "last_reload_error": store.error}

    return app


app = create_app()
