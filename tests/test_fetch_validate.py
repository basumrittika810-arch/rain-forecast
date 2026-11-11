"""Tests for pipeline/validate.py and pipeline/fetch.py (Step 1: fetch + validate, no publishing).

Synthetic GRIB runs from gribfactory.py; downloads are faked, so no network is used.
"""

import datetime as dt
import hashlib
import json

import pytest

from gribfactory import SMALL_GRID, write_run
from pipeline.compute import expected_steps
from pipeline.fetch import FetchError, fetch_run, find_latest_complete_run, run_id
from pipeline.validate import ValidationError, validate_run_file

INIT = dt.datetime(2026, 11, 11, 0, tzinfo=dt.timezone.utc)
STEPS = expected_steps(258)


def validate(path):
    return validate_run_file(path, INIT, STEPS, grid=SMALL_GRID)


def problems_of(path):
    with pytest.raises(ValidationError) as e:
        validate(path)
    return " | ".join(e.value.problems)


# ============================================================ validation

def test_good_run_passes(tmp_path):
    rep = validate(write_run(tmp_path / "tp.grib2", STEPS))
    assert rep["message_count"] == 68 and rep["steps"] == STEPS
    assert set(rep["increments_mm"]) == set(STEPS)          # one precision value per step, for the threshold


def test_missing_step_rejected(tmp_path):
    assert "missing steps: [42]" in problems_of(write_run(tmp_path / "f", STEPS, skip={42}))


def test_missing_last_step_258_rejected(tmp_path):
    assert "missing steps: [258]" in problems_of(write_run(tmp_path / "f", STEPS, skip={258}))


def test_duplicate_step_rejected(tmp_path):
    assert "duplicate steps: [42]" in problems_of(write_run(tmp_path / "f", STEPS, duplicate={42}))


def test_unexpected_extra_step_rejected(tmp_path):
    assert "unexpected steps: [147]" in problems_of(write_run(tmp_path / "f", sorted(STEPS + [147])))


def test_wrong_variable_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS, overrides={9: {"paramId": 167}})      # 2 m temperature
    assert "step 9: shortName" in problems_of(p)


def test_accumulation_not_from_start_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS, overrides={6: {"startStep": 3}})      # window 3-6 instead of 0-6
    assert "step 6: startStep" in problems_of(p)


def test_message_from_another_run_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS, overrides={12: {"dataDate": 20261110}})
    assert "step 12: initialisation" in problems_of(p)


def test_inconsistent_validity_time_rejected(tmp_path):
    # dataDate changed AFTER the step was set: the end-of-window time stays stale (found while building the factory).
    p = write_run(tmp_path / "f", STEPS, overrides={15: {"dataDate": 20261111, "yearOfEndOfOverallTimeInterval": 2007}})
    assert "step 15: validity" in problems_of(p)


def test_grid_mismatch_rejected(tmp_path):
    # one message on a 5-column grid instead of 4
    wider = dict(SMALL_GRID, Ni=5, longitudeOfLastGridPointInDegrees=80.5)
    p = write_run(tmp_path / "f", STEPS, overrides={18: {"grid": wider}})
    assert "step 18: grid" in problems_of(p)


def test_missing_values_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS, missing_at={21})
    assert "step 21: missing values" in problems_of(p)


def test_negative_stored_value_rejected(tmp_path):
    vals = {24: [-0.001] + [0.0] * 11}
    assert "step 24: negative" in problems_of(write_run(tmp_path / "f", STEPS, values=vals))


def test_unknown_packing_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS, overrides={27: {"packingType": "grid_ieee"}})
    assert "step 27: packing" in problems_of(p)


def test_truncated_file_rejected(tmp_path):
    p = write_run(tmp_path / "f", STEPS)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    msg = problems_of(p)
    assert "unreadable" in msg or "missing steps" in msg


def test_garbage_file_rejected(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"<html>503 Service Unavailable</html>")
    assert "no GRIB messages" in problems_of(p)


def test_empty_file_rejected(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"")
    assert "no GRIB messages" in problems_of(p)


# ============================================================ fetch: safe download and move

def snapshot(root):
    """{relative path: sha256} of every file under root."""
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def data_root(tmp_path):
    """A data folder that already holds a last good run and a published latest.json."""
    root = tmp_path / "data"
    good = root / "runs" / "20261110T00Z"
    good.mkdir(parents=True)
    write_run(good / "tp.grib2", STEPS, date=20261110)
    (good / "manifest.json").write_text('{"run": "20261110T00Z"}', encoding="utf-8")
    (root / "processed").mkdir()
    (root / "processed" / "latest.json").write_text('{"run": {"init_utc": "2026-11-10T00:00:00Z"}}', encoding="utf-8")
    return root


def protected(root):
    """Everything that must never change: the last good run and the published file."""
    return {k: v for k, v in snapshot(root).items() if k.startswith(("runs", "processed"))}


def good_download(init, steps, target):
    write_run(target, steps, date=int(init.strftime("%Y%m%d")))


def test_successful_fetch_creates_new_run_folder_only(data_root):
    before = protected(data_root)
    final = fetch_run(INIT, data_root, download=good_download, grid=SMALL_GRID)
    assert final == data_root / "runs" / "20261111T00Z"
    assert (final / "tp.grib2").is_file()
    man = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert man["sha256"] == hashlib.sha256((final / "tp.grib2").read_bytes()).hexdigest()
    assert man["validation"]["message_count"] == 68
    after = protected(data_root)
    assert {k: v for k, v in after.items() if not k.startswith("runs\\20261111T00Z") and
            not k.startswith("runs/20261111T00Z")} == before          # old run + latest.json untouched
    assert not any((data_root / "tmp").iterdir())                    # temporary folder cleaned up


def test_failed_download_leaves_last_good_forecast_unchanged(data_root):
    before = protected(data_root)

    def broken(init, steps, target):
        target.write_bytes(b"partial")
        raise ConnectionError("connection reset by peer")

    with pytest.raises(FetchError, match="connection reset"):
        fetch_run(INIT, data_root, download=broken, grid=SMALL_GRID)
    assert protected(data_root) == before                            # byte-for-byte identical
    assert not (data_root / "runs" / "20261111T00Z").exists()
    rejected = list((data_root / "rejected").iterdir())
    assert len(rejected) == 1 and "connection reset" in (rejected[0] / "reason.txt").read_text(encoding="utf-8")


def test_incomplete_download_leaves_last_good_forecast_unchanged(data_root):
    before = protected(data_root)

    def incomplete(init, steps, target):
        write_run(target, steps, skip={258})

    with pytest.raises(ValidationError, match="258"):
        fetch_run(INIT, data_root, download=incomplete, grid=SMALL_GRID)
    assert protected(data_root) == before
    assert not (data_root / "runs" / "20261111T00Z").exists()
    rejected = list((data_root / "rejected").iterdir())
    assert len(rejected) == 1
    assert (rejected[0] / "tp.grib2").is_file()                      # kept for investigation, not deleted
    assert "missing steps: [258]" in (rejected[0] / "reason.txt").read_text(encoding="utf-8")


def test_corrupt_download_leaves_last_good_forecast_unchanged(data_root):
    before = protected(data_root)

    def corrupt(init, steps, target):
        good_download(init, steps, target)
        target.write_bytes(target.read_bytes()[:5000])

    with pytest.raises(ValidationError):
        fetch_run(INIT, data_root, download=corrupt, grid=SMALL_GRID)
    assert protected(data_root) == before
    assert not (data_root / "runs" / "20261111T00Z").exists()


def test_existing_run_is_never_overwritten(data_root):
    calls = []
    existing = data_root / "runs" / "20261110T00Z"
    before = protected(data_root)
    with pytest.raises(FileExistsError):
        fetch_run(dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc), data_root,
                  download=lambda *a: calls.append(a), grid=SMALL_GRID)
    assert calls == []                                               # refused before downloading
    assert protected(data_root) == before and existing.is_dir()


def test_fetch_never_creates_or_changes_latest_json(data_root):
    latest = data_root / "processed" / "latest.json"
    before = latest.read_bytes()
    fetch_run(INIT, data_root, download=good_download, grid=SMALL_GRID)
    assert latest.read_bytes() == before
    assert sorted(p.name for p in (data_root / "processed").iterdir()) == ["latest.json"]


# ============================================================ choosing the run

def test_latest_complete_00z_run_is_chosen():
    now = dt.datetime(2026, 11, 12, 20, 0, tzinfo=dt.timezone.utc)
    listings = {
        dt.datetime(2026, 11, 12, 0, tzinfo=dt.timezone.utc): set(STEPS) - {258},   # still arriving
        dt.datetime(2026, 11, 11, 0, tzinfo=dt.timezone.utc): set(STEPS) | {264, 360},
    }
    chosen = find_latest_complete_run(now, list_steps=lambda init: listings.get(init, set()))
    assert chosen == dt.datetime(2026, 11, 11, 0, tzinfo=dt.timezone.utc)


def test_12z_runs_are_not_used():
    now = dt.datetime(2026, 11, 12, 20, 0, tzinfo=dt.timezone.utc)
    seen = []
    find_latest_complete_run(now, list_steps=lambda init: seen.append(init.hour) or set(STEPS))
    assert set(seen) == {0}


def test_no_complete_run_raises():
    now = dt.datetime(2026, 11, 12, 20, 0, tzinfo=dt.timezone.utc)
    with pytest.raises(FetchError, match="no complete"):
        find_latest_complete_run(now, list_steps=lambda init: set())


def test_run_id_format():
    assert run_id(INIT) == "20261111T00Z"
