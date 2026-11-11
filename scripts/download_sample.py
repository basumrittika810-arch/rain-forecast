"""Download the initial inspection sample: `tp` only, steps 0,3,6,144,150,240 h, one HRES run.

Usage:
    python scripts/download_sample.py YYYYMMDD HH        (HH must be 00 or 12)

Behaviour:
  * Fetches only the `tp` GRIB messages (byte ranges via the server's .index files)
    using ECMWF's official `ecmwf-opendata` client.
  * Raw data is immutable: refuses to run if the target file already exists, and marks
    the downloaded file read-only.
  * Completeness check: exactly one `tp` message per requested step, no extras.
    Any mismatch -> non-zero exit, file kept for investigation (not deleted silently).
  * Writes manifest.json (SHA-256, size, request, versions, UTC timestamp) next to the file.

This script deliberately does NOT interpret units, accumulation or values. That is done
in a separate, explicit inspection step.
"""

import datetime as dt
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import eccodes
from ecmwf.opendata import Client
from ecmwf.opendata import __version__ as opendata_version

SAMPLE_STEPS = [0, 3, 6, 144, 150, 240]
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_messages(path: Path) -> list[dict]:
    """Return shortName and step for every GRIB message (no value decoding)."""
    out = []
    with open(path, "rb") as f:
        while True:
            gid = eccodes.codes_grib_new_from_file(f)
            if gid is None:
                break
            try:
                out.append({
                    "shortName": eccodes.codes_get(gid, "shortName"),
                    "stepRange": eccodes.codes_get(gid, "stepRange"),
                    "endStep": eccodes.codes_get(gid, "endStep"),
                })
            finally:
                eccodes.codes_release(gid)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[2] not in ("00", "12") or len(argv[1]) != 8:
        print(__doc__)
        return 2
    date_str, hh = argv[1], argv[2]
    run = dt.datetime.strptime(date_str + hh, "%Y%m%d%H")

    out_dir = PROJECT_ROOT / "data" / "raw" / f"{run:%Y%m%dT%H}Z"
    target = out_dir / f"tp_steps_{'-'.join(map(str, SAMPLE_STEPS))}.grib2"
    manifest_path = out_dir / "manifest.json"
    if target.exists() or manifest_path.exists():
        print(f"REFUSING: {target} or its manifest already exists (raw data is immutable).")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    request = {
        "date": date_str, "time": int(hh), "stream": "oper", "type": "fc",
        "param": "tp", "step": SAMPLE_STEPS,
    }
    print(f"Requesting: {request}")
    started = dt.datetime.now(dt.timezone.utc)
    client = Client(source="ecmwf", model="ifs", resol="0p25")
    result = client.retrieve(request, target=str(target))
    finished = dt.datetime.now(dt.timezone.utc)

    # --- completeness check (structure only, no value interpretation) ---
    msgs = list_messages(target)
    print(f"\nMessages in file: {len(msgs)}")
    for m in msgs:
        print(f"  shortName={m['shortName']:<4} stepRange={m['stepRange']:<8} endStep={m['endStep']}")
    problems = []
    if len(msgs) != len(SAMPLE_STEPS):
        problems.append(f"expected {len(SAMPLE_STEPS)} messages, got {len(msgs)}")
    if any(m["shortName"] != "tp" for m in msgs):
        problems.append("non-tp message present")
    got_steps = sorted(int(m["endStep"]) for m in msgs)
    if got_steps != sorted(SAMPLE_STEPS):
        problems.append(f"end steps {got_steps} != requested {sorted(SAMPLE_STEPS)}")

    manifest = {
        "run_init_utc": f"{run:%Y-%m-%dT%H:00:00Z}",
        "request": request,
        "source": "https://data.ecmwf.int/forecasts (ecmwf-opendata source='ecmwf')",
        "urls": list(result.urls) if hasattr(result, "urls") else None,
        "file": target.name,
        "size_bytes": target.stat().st_size,
        "sha256": sha256_of(target),
        "download_started_utc": started.isoformat(timespec="seconds"),
        "download_finished_utc": finished.isoformat(timespec="seconds"),
        "messages": msgs,
        "completeness_problems": problems,
        "versions": {
            "ecmwf-opendata": opendata_version,
            "eccodes-python": eccodes.__version__,
            "ecCodes-C": eccodes.codes_get_api_version(),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    # Make raw file read-only (immutability guard; Windows honours the read-only attribute)
    os.chmod(target, stat.S_IREAD)

    print(f"\nSaved:    {target}")
    print(f"Size:     {manifest['size_bytes']:,} bytes")
    print(f"SHA-256:  {manifest['sha256']}")
    print(f"Manifest: {manifest_path}")
    if problems:
        print("\nCOMPLETENESS CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nCompleteness check passed: one tp message for each requested step.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
