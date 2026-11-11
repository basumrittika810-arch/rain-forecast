"""Download `tp` for every available step of one HRES run up to MAX_STEP (inclusive).

Usage:
    python scripts/download_run.py YYYYMMDD HH MAX_STEP

Behaviour:
  * The step list is taken from the server's directory listing of the run (what actually exists),
    then compared with the expected cadence (0-144 by 3, 150-MAX_STEP by 6). If they differ, the
    script STOPS before downloading and prints both lists.
  * Raw data is immutable: refuses if the target file or manifest already exists; marks the file read-only.
  * Completeness check after download: exactly one `tp` message per step, end steps match the list.
  * Writes a manifest (SHA-256, size, steps, versions, UTC timestamps).
Values are not interpreted here (see scripts/verify_run.py).
"""

import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

import eccodes
import requests
from ecmwf.opendata import Client
from ecmwf.opendata import __version__ as opendata_version

BASE_URL = "https://data.ecmwf.int/forecasts"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def expected_steps(max_step: int) -> list[int]:
    return list(range(0, min(max_step, 144) + 1, 3)) + list(range(150, max_step + 1, 6))


def listed_steps(ymd: str, hh: str) -> list[int]:
    url = f"{BASE_URL}/{ymd}/{hh}z/ifs/0p25/oper/"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    grib = set(int(s) for s in re.findall(rf"{ymd}{hh}0000-(\d+)h-oper-fc\.grib2", r.text))
    index = set(int(s) for s in re.findall(rf"{ymd}{hh}0000-(\d+)h-oper-fc\.index", r.text))
    return sorted(grib & index)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_messages(path: Path) -> list[dict]:
    out = []
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                out.append({k: eccodes.codes_get(gid, k)
                            for k in ("shortName", "stepRange", "startStep", "endStep")})
            finally:
                eccodes.codes_release(gid)
    return out


def main(argv):
    if len(argv) != 4 or argv[2] not in ("00", "12"):
        print(__doc__)
        return 2
    ymd, hh, max_step = argv[1], argv[2], int(argv[3])
    run = dt.datetime.strptime(ymd + hh, "%Y%m%d%H")

    available = [s for s in listed_steps(ymd, hh) if s <= max_step]
    expected = expected_steps(max_step)
    print(f"Server-listed steps <= {max_step}: {len(available)}")
    print(f"Expected-cadence steps:         {len(expected)}")
    if available != expected:
        print("MISMATCH between server listing and expected cadence. Not downloading.")
        print(f"  only on server : {sorted(set(available) - set(expected))}")
        print(f"  only expected  : {sorted(set(expected) - set(available))}")
        return 1
    print("Server listing matches expected cadence.")

    out_dir = PROJECT_ROOT / "data" / "raw" / f"{run:%Y%m%dT%H}Z"
    target = out_dir / f"tp_steps_0-{max_step}.grib2"
    manifest_path = out_dir / f"manifest_tp_steps_0-{max_step}.json"
    if target.exists() or manifest_path.exists():
        print(f"REFUSING: {target.name} or its manifest already exists (raw data is immutable).")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    request = {"date": ymd, "time": int(hh), "stream": "oper", "type": "fc",
               "param": "tp", "step": available}
    started = dt.datetime.now(dt.timezone.utc)
    Client(source="ecmwf", model="ifs", resol="0p25").retrieve(request, target=str(target))
    finished = dt.datetime.now(dt.timezone.utc)

    msgs = list_messages(target)
    problems = []
    if len(msgs) != len(available):
        problems.append(f"expected {len(available)} messages, got {len(msgs)}")
    if any(m["shortName"] != "tp" for m in msgs):
        problems.append("non-tp message present")
    got = [int(m["endStep"]) for m in msgs]
    if sorted(got) != available:
        problems.append(f"end steps differ: missing {sorted(set(available) - set(got))}, "
                        f"extra {sorted(set(got) - set(available))}")
    if len(set(got)) != len(got):
        problems.append("duplicate end steps")

    manifest = {
        "run_init_utc": f"{run:%Y-%m-%dT%H:00:00Z}",
        "request": request,
        "source": BASE_URL,
        "file": target.name,
        "size_bytes": target.stat().st_size,
        "sha256": sha256_of(target),
        "download_started_utc": started.isoformat(timespec="seconds"),
        "download_finished_utc": finished.isoformat(timespec="seconds"),
        "message_count": len(msgs),
        "messages": msgs,
        "completeness_problems": problems,
        "versions": {"ecmwf-opendata": opendata_version, "eccodes-python": eccodes.__version__,
                     "ecCodes-C": eccodes.codes_get_api_version()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    os.chmod(target, stat.S_IREAD)

    print(f"Saved {target} ({manifest['size_bytes']:,} bytes), SHA-256 {manifest['sha256']}")
    print(f"Download time: {(finished - started).total_seconds():.0f} s; messages: {len(msgs)}")
    if problems:
        print("COMPLETENESS CHECK FAILED:", *problems, sep="\n  - ")
        return 1
    print("Completeness check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
