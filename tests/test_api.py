"""Tests for the API (api/app.py), using real pipeline output (fetch + publish) from a synthetic run.

Synthetic run as in test_publish.py: running total at grid point i = step * (i + 1) * 2^-14 m.
Grid rows north->south (13.5, 13.25, 13.0), columns west->east (79.5, 79.75, 80.0, 80.25).
Point 13.25,79.50 is row 1, col 0 -> i = 4 -> factor 5 -> full day = 24 * 5 * 0.06103515625 = 7.32421875 mm.
"""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from gribfactory import SMALL_GRID, write_run
from pipeline.config import Region
from pipeline.fetch import fetch_run
from pipeline.publish import publish_run

TEST_REGION = Region("Test", 13.1, 13.4, 79.6, 80.1)
N = SMALL_GRID["Ni"] * SMALL_GRID["Nj"]


def make_and_publish(data_root, day):
    init = dt.datetime(2026, 11, day, tzinfo=dt.timezone.utc)

    def download(i, steps, target):
        write_run(target, steps, date=int(i.strftime("%Y%m%d")),
                  values={s: [s * (k + 1) * 2.0 ** -14 for k in range(N)] for s in steps})

    run_dir = fetch_run(init, data_root, download=download, grid=SMALL_GRID)
    publish_run(run_dir, data_root, region=TEST_REGION, grid=SMALL_GRID)


@pytest.fixture
def setup(tmp_path):
    data_root = tmp_path / "data"
    make_and_publish(data_root, 11)
    latest = data_root / "processed" / "latest.json"
    return data_root, latest, TestClient(create_app(latest))


# ---------------------------------------------------------------- normal requests

def test_forecast_for_location_inside_region(setup):
    _, latest, client = setup
    r = client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6})
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == {"lat": 13.3, "lon": 79.6}
    assert body["grid_point"] == {"lat": 13.25, "lon": 79.5}
    assert len(body["days"]) == 11 and len(body["intervals"]) == 67
    assert body["days"][0]["partial"] is True
    assert [d["raw_mm"] for d in body["days"][1:]] == [7.32421875] * 10     # hand-worked above
    # identical to what is stored in latest.json for that grid point
    stored = json.loads(latest.read_text(encoding="utf-8"))["points"]["13.25,79.50"]
    assert body["days"] == stored["days"] and body["intervals"] == stored["intervals"]
    assert body["run"]["init_utc"] == "2026-11-11T00:00:00Z"
    assert body["units"]["rain"] == "mm" and "ECMWF" in body["attribution"]
    assert body["quality"]["status"] == "ok"


@pytest.mark.parametrize("lat, lon, expected", [
    (13.125, 79.7, (13.25, 79.75)),     # exact latitude tie -> north
    (13.2, 79.625, (13.25, 79.75)),     # exact longitude tie -> east
    (13.4, 80.1, (13.5, 80.0)),         # box corner (edges are inside)
])
def test_snapping(setup, lat, lon, expected):
    r = setup[2].get("/api/forecast", params={"lat": lat, "lon": lon})
    assert r.status_code == 200
    assert (r.json()["grid_point"]["lat"], r.json()["grid_point"]["lon"]) == expected


# ---------------------------------------------------------------- refused requests

@pytest.mark.parametrize("lat, lon", [
    (22.5675, 88.37),     # Kolkata
    (13.09, 79.7),        # just south of the box; its nearest grid point (13.0) is stored, but the box decides
    (13.3, 80.11),        # just east of the box
])
def test_outside_region_is_404(setup, lat, lon):
    r = setup[2].get("/api/forecast", params={"lat": lat, "lon": lon})
    assert r.status_code == 404
    assert "outside the forecast region" in r.json()["detail"]


@pytest.mark.parametrize("params", [
    {"lat": "abc", "lon": 79.6},
    {"lat": 95, "lon": 79.6},
    {"lat": 13.3, "lon": 181},
    {"lat": 13.3},
    {"lat": "nan", "lon": 79.6},
    {"lat": "inf", "lon": 79.6},
])
def test_invalid_input_is_422(setup, params):
    assert setup[2].get("/api/forecast", params=params).status_code == 422


def test_no_forecast_published_is_503(tmp_path):
    client = TestClient(create_app(tmp_path / "processed" / "latest.json"))
    r = client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6})
    assert r.status_code == 503 and "no forecast" in r.json()["detail"]
    s = client.get("/api/status").json()
    assert s["forecast_available"] is False


# ---------------------------------------------------------------- updates and failures

def test_new_forecast_is_picked_up_without_restart(setup):
    data_root, _, client = setup
    assert client.get("/api/status").json()["run_init_utc"] == "2026-11-11T00:00:00Z"
    make_and_publish(data_root, 12)                       # atomically replaces latest.json
    assert client.get("/api/status").json()["run_init_utc"] == "2026-11-12T00:00:00Z"
    r = client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6})
    assert r.json()["run"]["init_utc"] == "2026-11-12T00:00:00Z"


def test_corrupt_latest_keeps_serving_previous_forecast(setup):
    _, latest, client = setup
    assert client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6}).status_code == 200
    latest.write_text("{ this is not json", encoding="utf-8")
    r = client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6})
    assert r.status_code == 200 and r.json()["run"]["init_utc"] == "2026-11-11T00:00:00Z"
    s = client.get("/api/status").json()
    assert s["forecast_available"] is True and s["last_reload_error"]


def test_corrupt_latest_with_nothing_loaded_is_503(tmp_path):
    p = tmp_path / "latest.json"
    p.write_text("not json", encoding="utf-8")
    client = TestClient(create_app(p))
    assert client.get("/api/forecast", params={"lat": 13.3, "lon": 79.6}).status_code == 503


# ---------------------------------------------------------------- status

def test_status(setup):
    s = setup[2].get("/api/status").json()
    assert s["forecast_available"] is True
    assert s["run_init_utc"] == "2026-11-11T00:00:00Z" and s["run_init_ist"] == "2026-11-11T05:30+05:30"
    assert s["points"] == 9 and s["quality"]["status"] == "ok" and s["region"]["name"] == "Test"
    assert isinstance(s["age_hours"], float) and s["last_reload_error"] is None
