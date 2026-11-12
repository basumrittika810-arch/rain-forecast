"""Tests for pipeline/run.py: the one-command pipeline used by the scheduled GitHub Actions workflow.

Network calls are replaced by fakes: the ECMWF listing, the download, and the currently published latest.json.
"""

import datetime as dt
import json

import pytest

from gribfactory import SMALL_GRID, write_run
from pipeline.compute import expected_steps
from pipeline.config import Region
from pipeline.fetch import FetchError
from pipeline.run import PublishedFetchError, run_pipeline
from pipeline.validate import ValidationError

TEST_REGION = Region("Test", 13.1, 13.4, 79.6, 80.1)
STEPS = expected_steps(258)
N = SMALL_GRID["Ni"] * SMALL_GRID["Nj"]
NOW = dt.datetime(2026, 11, 12, 20, 0, tzinfo=dt.timezone.utc)
NEWEST = dt.datetime(2026, 11, 12, 0, tzinfo=dt.timezone.utc)


def listing(init):
    return set(STEPS) if init <= NEWEST else set()


class Downloads:
    def __init__(self):
        self.calls = 0

    def __call__(self, init, steps, target):
        self.calls += 1
        write_run(target, steps, date=int(init.strftime("%Y%m%d")),
                  values={s: [s * (k + 1) * 2.0 ** -14 for k in range(N)] for s in steps})


def published_doc(init_utc):
    return json.dumps({"run": {"init_utc": init_utc}, "points": {}})


def go(tmp_path, published=None, download=None, simulate_failure=False):
    download = download or Downloads()
    outcome = run_pipeline(
        data_root=tmp_path / "data", site_dir=tmp_path / "site", now=NOW,
        fetch_published=lambda: published, list_steps=listing, download=download,
        region=TEST_REGION, grid=SMALL_GRID, simulate_failure=simulate_failure)
    return outcome, download


def test_first_ever_run_publishes_and_builds_site(tmp_path):
    outcome, dl = go(tmp_path, published=None)
    assert outcome == "published" and dl.calls == 1
    site_latest = tmp_path / "site" / "latest.json"
    assert site_latest.read_bytes() == (tmp_path / "data" / "processed" / "latest.json").read_bytes()
    assert json.loads(site_latest.read_text())["run"]["init_utc"] == "2026-11-12T00:00:00Z"
    assert (tmp_path / "site" / "index.html").is_file() and (tmp_path / "site" / ".nojekyll").is_file()


def test_newer_run_than_published_is_published(tmp_path):
    outcome, dl = go(tmp_path, published=published_doc("2026-11-11T00:00:00Z"))
    assert outcome == "published" and dl.calls == 1


def test_same_run_already_published_downloads_nothing(tmp_path):
    outcome, dl = go(tmp_path, published=published_doc("2026-11-12T00:00:00Z"))
    assert outcome == "unchanged" and dl.calls == 0
    assert not (tmp_path / "site").exists()


def test_published_newer_than_server_downloads_nothing(tmp_path):
    outcome, dl = go(tmp_path, published=published_doc("2026-11-13T00:00:00Z"))
    assert outcome == "unchanged" and dl.calls == 0


def test_simulated_failure_is_rejected_and_nothing_is_published(tmp_path):
    with pytest.raises(ValidationError):
        go(tmp_path, published=published_doc("2026-11-12T00:00:00Z"), simulate_failure=True)
    assert not (tmp_path / "site").exists()
    processed = tmp_path / "data" / "processed"
    # only the seeded copy of the published forecast exists; nothing new was written
    assert sorted(p.name for p in processed.iterdir()) == ["latest.json"]
    assert json.loads((processed / "latest.json").read_text())["run"]["init_utc"] == "2026-11-12T00:00:00Z"
    rejected = list((tmp_path / "data" / "rejected").iterdir())
    assert len(rejected) == 1 and "no GRIB messages" in (rejected[0] / "reason.txt").read_text(encoding="utf-8")


def test_failed_download_publishes_nothing(tmp_path):
    def broken(init, steps, target):
        raise ConnectionError("ECMWF unreachable")
    with pytest.raises(FetchError):
        go(tmp_path, published=published_doc("2026-11-11T00:00:00Z"), download=broken)
    assert not (tmp_path / "site").exists()


def test_unreadable_published_forecast_stops_the_run(tmp_path):
    def cannot_read():
        raise PublishedFetchError("HTTP 500")
    with pytest.raises(PublishedFetchError):
        run_pipeline(data_root=tmp_path / "data", site_dir=tmp_path / "site", now=NOW,
                     fetch_published=cannot_read, list_steps=listing, download=Downloads(),
                     region=TEST_REGION, grid=SMALL_GRID)
    assert not (tmp_path / "site").exists()


def test_corrupt_published_forecast_stops_the_run(tmp_path):
    with pytest.raises(PublishedFetchError):
        go(tmp_path, published="{ not json")
    assert not (tmp_path / "site").exists()
