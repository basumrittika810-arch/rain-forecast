"""Tests for pipeline/publish.py (Step 2: compute rainfall, build JSON, check it, publish safely).

Synthetic run on the 3 x 4 test grid. Running total at grid point i (row-major, north->south, west->east):
    total(step) = step * (i + 1) * 2^-14 m        (1 unit = 2^-14 m = 0.06103515625 mm)
so rain falls at a constant (i + 1) units per hour. Hand-worked values for point "13.00,79.50"
(row 2, col 0 -> i = 8, factor 9):
    full day   = 24 h * 9 units = 216 units = 13.18359375 mm
    first day  = 18 h * 9 units = 162 units =  9.8876953125 mm  (partial, 05:30 -> 23:30 IST)
    3-h slot   =  3 h * 9 units =  27 units =  1.64794921875 mm
    6-h slot   =  6 h * 9 units =  54 units =  3.2958984375 mm
    rate       =  9 units per h             =  0.54931640625 mm/h
"""

import copy
import datetime as dt
import hashlib
import json

import pytest

from gribfactory import SMALL_GRID, write_run
from pipeline import publish as pub
from pipeline.compute import expected_steps
from pipeline.config import Region
from pipeline.fetch import fetch_run

INIT = dt.datetime(2026, 11, 11, 0, tzinfo=dt.timezone.utc)
STEPS = expected_steps(258)
U = 0.06103515625                      # mm per unit
TEST_REGION = Region("Test", 13.1, 13.4, 79.6, 80.1)   # with the 0.125 margin: 3 x 3 = 9 grid points
N = SMALL_GRID["Ni"] * SMALL_GRID["Nj"]


def steady_values(step):
    return [step * (i + 1) * 2.0 ** -14 for i in range(N)]


def make_run(data_root, init=INIT, values=steady_values):
    def download(i, steps, target):
        write_run(target, steps, date=int(i.strftime("%Y%m%d")), values={s: values(s) for s in steps})
    return fetch_run(init, data_root, download=download, grid=SMALL_GRID)


def publish(run_dir, data_root):
    return pub.publish_run(run_dir, data_root, region=TEST_REGION, grid=SMALL_GRID)


@pytest.fixture
def data_root(tmp_path):
    return tmp_path / "data"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ============================================================ building the JSON

def test_json_content_hand_checked(data_root):
    doc = pub.build_forecast(make_run(data_root), region=TEST_REGION, grid=SMALL_GRID)
    assert len(doc["points"]) == 9
    assert sorted(doc["points"])[:2] == ["13.00,79.50", "13.00,79.75"]
    p = doc["points"]["13.00,79.50"]
    assert (p["lat"], p["lon"]) == (13.0, 79.5)
    assert len(p["days"]) == 11 and len(p["intervals"]) == 67

    d0 = p["days"][0]
    assert (d0["date"], d0["start"], d0["end"], d0["hours"], d0["partial"]) == \
        ("2026-11-11", "2026-11-11T05:30+05:30", "2026-11-11T23:30+05:30", 18, True)
    assert (d0["raw_mm"], d0["mm"], d0["status"]) == (9.8876953125, 9.8876953125, "ok")
    for d in p["days"][1:]:
        assert (d["hours"], d["partial"], d["raw_mm"], d["status"]) == (24, False, 13.18359375, "ok")
    assert p["days"][-1]["date"] == "2026-11-21"

    i0, i_last = p["intervals"][0], p["intervals"][-1]
    assert (i0["start"], i0["end"], i0["hours"], i0["raw_mm"], i0["mm_per_h"]) == \
        ("2026-11-11T05:30+05:30", "2026-11-11T08:30+05:30", 3, 1.64794921875, 0.54931640625)
    assert (i_last["end"], i_last["hours"], i_last["raw_mm"], i_last["mm_per_h"]) == \
        ("2026-11-21T23:30+05:30", 6, 3.2958984375, 0.54931640625)

    # first point (13.50,79.50 is i = 0, factor 1): a full day is 24 units = 1.46484375 mm
    assert doc["points"]["13.50,79.50"]["days"][1]["raw_mm"] == 1.46484375


def test_json_metadata(data_root):
    run_dir = make_run(data_root)
    doc = pub.build_forecast(run_dir, region=TEST_REGION, grid=SMALL_GRID)
    assert doc["schema_version"] == "1.0"
    assert doc["run"]["init_utc"] == "2026-11-11T00:00:00Z" and doc["run"]["init_ist"] == "2026-11-11T05:30+05:30"
    assert doc["run"]["horizon_hours"] == 258 and doc["run"]["steps_used"] == 68
    assert doc["run"]["source_sha256"] == json.loads((run_dir / "manifest.json").read_text())["sha256"]
    assert doc["units"] == {"rain": "mm", "rate": "mm/h", "time": "ISO 8601 with UTC offset (IST = +05:30)"}
    assert "ECMWF" in doc["attribution"] and "CC BY 4.0" in doc["attribution"]
    assert doc["quality"] == {"status": "ok", "adjusted_intervals": 0, "adjusted_days": 0,
                              "largest_adjusted_raw_mm": None, "unavailable_periods": 0}
    assert doc["region"]["name"] == "Test" and doc["grid"]["points"] == 9


def test_good_json_passes_all_checks(data_root):
    run_dir = make_run(data_root)
    doc = pub.build_forecast(run_dir, region=TEST_REGION, grid=SMALL_GRID)
    assert pub.check_forecast(doc, run_dir, region=TEST_REGION, grid=SMALL_GRID) == []


# ============================================================ the checks catch broken JSON

def broken(data_root, mutate):
    run_dir = make_run(data_root)
    doc = pub.build_forecast(run_dir, region=TEST_REGION, grid=SMALL_GRID)
    mutate(doc)
    return " | ".join(pub.check_forecast(doc, run_dir, region=TEST_REGION, grid=SMALL_GRID))


def test_check_missing_field(data_root):
    assert "missing top-level field: units" in broken(data_root, lambda d: d.pop("units"))


def test_check_missing_location(data_root):
    assert "points differ" in broken(data_root, lambda d: d["points"].pop("13.25,79.75"))


def test_check_gap_in_time(data_root):
    assert "not contiguous" in broken(data_root, lambda d: d["points"]["13.00,79.50"]["intervals"].pop(10))


def test_check_wrong_duration(data_root):
    def m(d):
        d["points"]["13.00,79.50"]["intervals"][-1]["hours"] = 3
    assert "hours" in broken(data_root, m)


def test_check_hidden_zero_for_missing(data_root):
    def m(d):
        x = d["points"]["13.00,79.50"]["days"][3]
        x.update(status="unavailable", mm=0.0, raw_mm=None, reason="test")
    assert "unavailable must have null" in broken(data_root, m)


def test_check_display_differs_from_raw(data_root):
    def m(d):
        d["points"]["13.00,79.50"]["days"][2]["mm"] = 99.0
    assert "ok value with mm != raw_mm" in broken(data_root, m)


def test_check_day_not_sum_of_intervals(data_root):
    def m(d):
        d["points"]["13.00,79.50"]["intervals"][20]["raw_mm"] += 0.5
        d["points"]["13.00,79.50"]["intervals"][20]["mm"] += 0.5
        d["points"]["13.00,79.50"]["intervals"][20]["mm_per_h"] = d["points"]["13.00,79.50"]["intervals"][20]["mm"] / 3
    assert "day != sum of intervals" in broken(data_root, m)


def test_independent_spot_check_catches_consistent_tampering(data_root):
    # Change a day AND its intervals consistently, so every internal check passes;
    # only the independent recalculation from the GRIB file can notice.
    def m(d):
        p = d["points"]["13.00,79.50"]          # a spot-checked point
        p["days"][5]["raw_mm"] += 0.5
        p["days"][5]["mm"] += 0.5
        iv = next(i for i in p["intervals"] if i["start"] == p["days"][5]["start"])
        iv["raw_mm"] += 0.5
        iv["mm"] += 0.5
        iv["mm_per_h"] = iv["mm"] / iv["hours"]
    assert "spot check" in broken(data_root, m)


def test_check_adjusted_beyond_threshold(data_root):
    def m(d):
        x = d["points"]["13.00,79.50"]["intervals"][4]
        x.update(status="adjusted", mm=0.0, raw_mm=-5.0, mm_per_h=0.0)
    assert "beyond threshold" in broken(data_root, m)


# ============================================================ publishing safely

def test_publish_writes_run_file_and_latest(data_root):
    out = publish(make_run(data_root), data_root)
    latest = data_root / "processed" / "latest.json"
    assert out == data_root / "processed" / "20261111T00Z.json"
    assert latest.read_bytes() == out.read_bytes()
    assert json.loads(latest.read_text())["run"]["init_utc"] == "2026-11-11T00:00:00Z"
    assert not list((data_root / "processed").glob("*.tmp"))


def test_newer_run_replaces_latest_and_keeps_old_run_file(data_root):
    publish(make_run(data_root, init=dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)), data_root)
    old_file = data_root / "processed" / "20261110T00Z.json"
    old_sha = sha(old_file)
    publish(make_run(data_root), data_root)
    assert json.loads((data_root / "processed" / "latest.json").read_text())["run"]["init_utc"].startswith("2026-11-11")
    assert sha(old_file) == old_sha


def published_state(data_root):
    return {p.name: sha(p) for p in sorted((data_root / "processed").iterdir())}


def test_invalid_negative_blocks_publication_and_latest_unchanged(data_root):
    publish(make_run(data_root, init=dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)), data_root)
    before = published_state(data_root)

    def dip(step):  # point 0 drops from 6 units (step 6) to 0 (step 9): far beyond any rounding threshold
        v = steady_values(step)
        if step >= 9:
            v[0] = 0.0
        return v

    with pytest.raises(pub.PublishError, match="invalid"):
        publish(make_run(data_root, values=dip), data_root)
    assert published_state(data_root) == before


def test_failed_json_check_blocks_publication_and_latest_unchanged(data_root, monkeypatch):
    publish(make_run(data_root, init=dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)), data_root)
    before = published_state(data_root)
    real_build = pub.build_forecast

    def bad_build(*a, **k):
        doc = real_build(*a, **k)
        doc["points"].pop("13.00,79.50")
        return doc

    monkeypatch.setattr(pub, "build_forecast", bad_build)
    with pytest.raises(pub.PublishError, match="points differ"):
        publish(make_run(data_root), data_root)
    assert published_state(data_root) == before


def test_older_run_is_not_published_over_newer(data_root):
    publish(make_run(data_root, init=dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc)), data_root)
    before = published_state(data_root)
    with pytest.raises(pub.PublishError, match="older"):
        publish(make_run(data_root), data_root)
    assert published_state(data_root) == before


def test_tampered_grib_file_is_not_published(data_root):
    run_dir = make_run(data_root)
    g = run_dir / "tp.grib2"
    import os
    import stat
    os.chmod(g, stat.S_IWRITE | stat.S_IREAD)
    g.write_bytes(g.read_bytes() + b"x")      # file no longer matches its manifest checksum
    with pytest.raises(pub.PublishError, match="checksum"):
        publish(run_dir, data_root)
    assert not (data_root / "processed" / "latest.json").exists()


def test_republishing_same_run_changes_nothing(data_root):
    run_dir = make_run(data_root)
    publish(run_dir, data_root)
    before = published_state(data_root)
    publish(run_dir, data_root)
    assert published_state(data_root) == before
