"""API reading latest.json from a URL (as on Render, reading from GitHub Pages).

A real local HTTP server stands in for GitHub Pages. Forecast files come from the real pipeline
(fetch + publish of a synthetic run), via the helper in test_api.py.
"""

import functools
import http.server
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from test_api import make_and_publish

Q = {"lat": 13.3, "lon": 79.6}


class FakePages:
    """Serves files from a folder; can be switched to answer HTTP 500; counts requests."""

    def __init__(self, folder):
        self.folder, self.hits, self.fail = folder, 0, False
        pages = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                pages.hits += 1
                if pages.fail:
                    self.send_error(500, "simulated server error")
                    return
                super().do_GET()

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                      functools.partial(Handler, directory=str(folder)))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/latest.json"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def env(tmp_path):
    data_root = tmp_path / "data"
    make_and_publish(data_root, 11)
    site = tmp_path / "site"
    site.mkdir()
    pages = FakePages(site)
    yield data_root, site, pages
    pages.close()


def serve(data_root, site):
    shutil.copyfile(data_root / "processed" / "latest.json", site / "latest.json")


def test_serves_forecast_from_url(env):
    data_root, site, pages = env
    serve(data_root, site)
    client = TestClient(create_app(url=pages.url, refresh_seconds=0))
    r = client.get("/api/forecast", params=Q)
    assert r.status_code == 200 and r.json()["grid_point"] == {"lat": 13.25, "lon": 79.5}
    s = client.get("/api/status").json()
    assert s["source"] == "url" and s["run_init_utc"] == "2026-11-11T00:00:00Z"


def test_nothing_published_yet_is_503(env):
    _, _, pages = env                                   # site folder empty -> 404 from server
    client = TestClient(create_app(url=pages.url, refresh_seconds=0))
    assert client.get("/api/forecast", params=Q).status_code == 503


def test_unreachable_server_is_503_with_error_in_status(env):
    _, _, pages = env
    url = pages.url
    pages.close()                                       # nothing listening any more
    client = TestClient(create_app(url=url, refresh_seconds=0))
    assert client.get("/api/forecast", params=Q).status_code == 503
    assert client.get("/api/status").json()["last_reload_error"]


def test_server_error_keeps_previous_forecast(env):
    data_root, site, pages = env
    serve(data_root, site)
    client = TestClient(create_app(url=pages.url, refresh_seconds=0))
    assert client.get("/api/forecast", params=Q).status_code == 200
    pages.fail = True
    r = client.get("/api/forecast", params=Q)
    assert r.status_code == 200 and r.json()["run"]["init_utc"] == "2026-11-11T00:00:00Z"
    assert "500" in client.get("/api/status").json()["last_reload_error"]


def test_broken_file_keeps_previous_forecast(env):
    data_root, site, pages = env
    serve(data_root, site)
    client = TestClient(create_app(url=pages.url, refresh_seconds=0))
    assert client.get("/api/forecast", params=Q).status_code == 200
    (site / "latest.json").write_text("{ broken", encoding="utf-8")
    r = client.get("/api/forecast", params=Q)
    assert r.status_code == 200 and r.json()["run"]["init_utc"] == "2026-11-11T00:00:00Z"
    assert client.get("/api/status").json()["last_reload_error"]


def test_new_forecast_on_server_is_picked_up(env):
    data_root, site, pages = env
    serve(data_root, site)
    client = TestClient(create_app(url=pages.url, refresh_seconds=0))
    assert client.get("/api/status").json()["run_init_utc"] == "2026-11-11T00:00:00Z"
    make_and_publish(data_root, 12)
    serve(data_root, site)
    assert client.get("/api/status").json()["run_init_utc"] == "2026-11-12T00:00:00Z"


def test_rechecks_only_after_refresh_interval(env):
    data_root, site, pages = env
    serve(data_root, site)
    t = [1000.0]
    client = TestClient(create_app(url=pages.url, refresh_seconds=900, clock=lambda: t[0]))
    for _ in range(3):
        assert client.get("/api/forecast", params=Q).status_code == 200
    assert pages.hits == 1                              # loaded once, then served from memory
    t[0] += 901
    client.get("/api/forecast", params=Q)
    assert pages.hits == 2                              # re-checked after the interval
