"""Step 1 of the pipeline: find, download and validate a forecast run. Never publishes anything.

Flow:  data/tmp/<run>_<id>/  --download-->  --validate-->  rename to  data/runs/<run>/
       on any failure: the temp folder is moved to data/rejected/<run>_<time>_<id>/ with reason.txt
                       (kept for investigation, never silently deleted).
Never touched: existing data/runs/<other run>/ folders and data/processed/ (incl. latest.json).

Usage:  python -m pipeline.fetch
"""

import datetime as dt
import hashlib
import json
import logging
import os
import re
import stat
import sys
import time
import uuid
from pathlib import Path

import requests

from pipeline.compute import expected_steps
from pipeline.validate import REAL_GRID, ValidationError, validate_run_file

log = logging.getLogger("pipeline.fetch")

BASE_URL = "https://data.ecmwf.int/forecasts"
HORIZON_HOURS = 258                     # D-006
RUN_HOURS = (0,)                        # only 00 UTC runs until the 12 UTC question is decided
LOOKBACK_DAYS = 3                       # ECMWF keeps roughly 2-4 days (conflicting docs, D-005)
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
GRIB_NAME = "tp.grib2"


class FetchError(RuntimeError):
    pass


def run_id(init: dt.datetime) -> str:
    return f"{init:%Y%m%dT%H}Z"


def list_server_steps(init: dt.datetime) -> set[int]:
    """Steps for which both .grib2 and .index are listed on the server (empty set if run not published)."""
    url = f"{BASE_URL}/{init:%Y%m%d}/{init:%H}z/ifs/0p25/oper/"
    r = requests.get(url, timeout=30)
    if r.status_code == 404:
        return set()
    r.raise_for_status()
    stamp = f"{init:%Y%m%d%H}0000"
    grib = {int(s) for s in re.findall(rf"{stamp}-(\d+)h-oper-fc\.grib2", r.text)}
    index = {int(s) for s in re.findall(rf"{stamp}-(\d+)h-oper-fc\.index", r.text)}
    return grib & index


def find_latest_complete_run(now_utc: dt.datetime, list_steps=list_server_steps,
                             horizon_hours: int = HORIZON_HOURS) -> dt.datetime:
    needed = set(expected_steps(horizon_hours))
    for back in range(LOOKBACK_DAYS):
        day = (now_utc - dt.timedelta(days=back)).date()
        for hour in sorted(RUN_HOURS, reverse=True):
            init = dt.datetime(day.year, day.month, day.day, hour, tzinfo=dt.timezone.utc)
            if init > now_utc:
                continue
            available = list_steps(init)
            if needed <= available:
                return init
            log.info("run %s not complete on server: %d of %d required steps listed",
                     run_id(init), len(needed & available), len(needed))
    raise FetchError(f"no complete run found in the last {LOOKBACK_DAYS} days")


def ecmwf_download(init: dt.datetime, steps: list[int], target: Path) -> None:
    from ecmwf.opendata import Client
    Client(source="ecmwf", model="ifs", resol="0p25").retrieve(
        {"date": f"{init:%Y%m%d}", "time": init.hour, "stream": "oper", "type": "fc",
         "param": "tp", "step": steps}, target=str(target))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _reject(tmp: Path, data_root: Path, rid: str, reason: str) -> Path:
    dest = data_root / "rejected" / f"{rid}_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:6]}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.rename(tmp, dest)
    (dest / "reason.txt").write_text(reason + "\n", encoding="utf-8")
    log.error("rejected %s -> %s\n%s", rid, dest, reason)
    return dest


def fetch_run(init: dt.datetime, data_root: Path = DATA_ROOT, download=ecmwf_download,
              grid: dict = REAL_GRID, horizon_hours: int = HORIZON_HOURS) -> Path:
    """Download + validate one run into a new folder data/runs/<run>/. Returns that folder."""
    rid = run_id(init)
    steps = expected_steps(horizon_hours)
    final = data_root / "runs" / rid
    if final.exists():
        raise FileExistsError(f"run folder already exists, not overwriting: {final}")

    tmp = data_root / "tmp" / f"{rid}_{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True)
    target = tmp / GRIB_NAME
    started = dt.datetime.now(dt.timezone.utc)
    t0 = time.monotonic()
    log.info("downloading %s (%d steps, 0-%d h) into %s", rid, len(steps), horizon_hours, tmp)
    try:
        download(init, steps, target)
    except Exception as e:  # any download failure: recorded, kept for investigation, then re-raised
        _reject(tmp, data_root, rid, f"download failed: {type(e).__name__}: {e}")
        raise FetchError(f"download failed for {rid}: {e}") from e
    log.info("downloaded %s bytes in %.0f s", f"{target.stat().st_size:,}", time.monotonic() - t0)

    try:
        report = validate_run_file(target, init, steps, grid=grid)
    except ValidationError as e:
        _reject(tmp, data_root, rid, "validation failed:\n" + "\n".join(e.problems))
        raise
    incs = sorted(set(report["increments_mm"].values()))
    log.info("validation passed: %d messages, steps %d-%d, packing increments (mm) %s",
             report["message_count"], report["steps"][0], report["steps"][-1], incs)

    manifest = {
        "run": rid, "run_init_utc": init.isoformat(), "horizon_hours": horizon_hours,
        "source": BASE_URL, "file": GRIB_NAME, "size_bytes": target.stat().st_size, "sha256": _sha256(target),
        "download_started_utc": started.isoformat(timespec="seconds"),
        "validated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "validation": report,
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.chmod(target, stat.S_IREAD)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(tmp, final)  # same disk -> atomic; raises if final appeared meanwhile
    log.info("stored validated run %s (sha256 %s)", final, manifest["sha256"][:16])
    return final


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    init = find_latest_complete_run(dt.datetime.now(dt.timezone.utc))
    log.info("latest complete run on server: %s", run_id(init))
    if (DATA_ROOT / "runs" / run_id(init)).exists():
        log.info("run %s already fetched; nothing to do", run_id(init))
        return 0
    fetch_run(init)
    return 0


if __name__ == "__main__":
    sys.exit(main())
