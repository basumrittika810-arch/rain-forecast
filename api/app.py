"""Read-only API over the published forecast (data/processed/latest.json). No rainfall calculations happen here; it only adds display text (pipeline/messages.py, D-027).

Endpoints
  GET /api/forecast?lat=..&lon=..   forecast for the nearest grid point (ties north/east) inside the region box
  GET /api/status                   which forecast is live, how old it is, last reload problem (if any)
  GET /api/places?q=..              find a Tamil Nadu place by name -> coordinates and district (D-024)

Where the forecast comes from:
  * FORECAST_URL set (deployment): latest.json is downloaded from that URL (GitHub Pages) and re-checked every
    FORECAST_REFRESH_SECONDS (default 900).
  * otherwise (local): data/processed/latest.json, re-checked on every request (a cheap file-status check).
If a new version cannot be read, the previously loaded forecast keeps being served and the problem is reported
in /api/status.

Run locally:  .venv\\Scripts\\python.exe -m uvicorn api.app:app --port 8000
"""

import datetime as dt
import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from pipeline.config import Region
from pipeline.grid import snap_to_grid
from pipeline.messages import AREA_NOTE, CATEGORY_SOURCE, describe_day, format_mm
from pipeline.places import ATTRIBUTION as PLACES_ATTRIBUTION, DEFAULT_PLACES_PATH, PlaceIndex, load_places

log = logging.getLogger("api")
DEFAULT_LATEST = Path(__file__).resolve().parent.parent / "data" / "processed" / "latest.json"


class SourceError(RuntimeError):
    pass


class FileSource:
    kind = "file"

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self, token):
        """(new_token, text), or None if unchanged or not published yet."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return None
        sig = (st.st_mtime_ns, st.st_size, st.st_ino)
        if sig == token:
            return None
        try:
            return sig, self.path.read_text(encoding="utf-8")
        except OSError as e:
            raise SourceError(f"{type(e).__name__}: {e}") from e


class UrlSource:
    kind = "url"

    def __init__(self, url: str, timeout: float = 30):
        self.url, self.timeout = url, timeout

    def read(self, token):
        req = urllib.request.Request(self.url, headers={"If-None-Match": token} if token else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read()
                etag = r.headers.get("ETag") or hashlib.sha256(body).hexdigest()
        except urllib.error.HTTPError as e:
            if e.code in (304, 404):   # unchanged / not published yet
                return None
            raise SourceError(f"HTTP {e.code} from {self.url}") from e
        except (urllib.error.URLError, OSError) as e:
            raise SourceError(f"cannot reach {self.url}: {getattr(e, 'reason', e)}") from e
        if etag == token:
            return None
        return etag, body.decode("utf-8")


class ForecastStore:
    """Holds the last successfully loaded latest.json and refreshes it from its source."""

    def __init__(self, source, refresh_seconds: float, clock=time.monotonic):
        self.source, self.refresh, self.clock = source, refresh_seconds, clock
        self.doc = self.token = self.error = self.last_check = None
        self.lock = threading.Lock()

    def get(self):
        if self.last_check is not None and self.clock() - self.last_check < self.refresh:
            return self.doc
        with self.lock:
            if self.last_check is not None and self.clock() - self.last_check < self.refresh:
                return self.doc
            self.last_check = self.clock()
            try:
                result = self.source.read(self.token)
            except SourceError as e:
                self.error = str(e)
                log.error("forecast source problem; keeping previous forecast: %s", self.error)
                return self.doc
            if result is None:
                return self.doc
            token, text = result
            try:
                doc = json.loads(text)
                doc["run"]["init_utc"], doc["region"]["name"], doc["points"]  # minimal shape check
            except (ValueError, KeyError, TypeError) as e:
                self.error = f"{type(e).__name__}: {e}"
                log.error("could not parse forecast; keeping previous forecast: %s", self.error)
            else:
                self.doc, self.error = doc, None
                log.info("loaded forecast run %s (%d points)", doc["run"]["init_utc"], len(doc["points"]))
            self.token = token  # do not re-parse the same broken content on every check
        return self.doc


def _region(doc) -> Region:
    r = doc["region"]
    return Region(r["name"], r["lat_min"], r["lat_max"], r["lon_min"], r["lon_max"])


def create_app(latest_path: Path | None = None, url: str | None = None, refresh_seconds: float | None = None,
               clock=time.monotonic, places_path: Path = DEFAULT_PLACES_PATH) -> FastAPI:
    url = url or (None if latest_path else os.environ.get("FORECAST_URL"))
    if url:
        source = UrlSource(url)
        refresh = refresh_seconds if refresh_seconds is not None else float(
            os.environ.get("FORECAST_REFRESH_SECONDS", "900"))
    else:
        source = FileSource(latest_path or DEFAULT_LATEST)
        refresh = refresh_seconds if refresh_seconds is not None else 0
    app = FastAPI(title="Rain forecast API", version="1.0")
    store = ForecastStore(source, refresh, clock=clock)
    places = PlaceIndex(load_places(places_path))   # committed file; a broken file stops startup (no silent empty list)

    @app.get("/api/places")
    def find_places(q: str = Query(..., max_length=100, description="place name, English spelling"),
                    limit: int = Query(10, ge=1, le=50)):
        try:
            result = places.search(q, limit=limit)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {**result, "attribution": PLACES_ATTRIBUTION}

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
            # published fields unchanged; display text added (D-027): shown amount, IMD label, message
            "days": [{**d, **describe_day(d, point["intervals"])} for d in point["days"]],
            "intervals": [{**i, "shown": format_mm(i["mm"])} for i in point["intervals"]],
            "area_note": AREA_NOTE, "category_source": CATEGORY_SOURCE,
        }

    @app.get("/api/status")
    def status():
        doc = store.get()
        if doc is None:
            return {"forecast_available": False, "source": source.kind, "last_reload_error": store.error}
        init = dt.datetime.fromisoformat(doc["run"]["init_utc"].replace("Z", "+00:00"))
        age = (dt.datetime.now(dt.timezone.utc) - init).total_seconds() / 3600
        return {"forecast_available": True, "run_init_utc": doc["run"]["init_utc"],
                "run_init_ist": doc["run"]["init_ist"], "generated_utc": doc.get("generated_utc"),
                "age_hours": round(age, 2), "quality": doc["quality"], "points": len(doc["points"]),
                "region": doc["region"], "source": source.kind, "last_reload_error": store.error}

    return app


app = create_app()
