"""Check which recent ECMWF IFS HRES 00/12 UTC run has `tp` available for the sample steps.

Downloads only the small `.index` sidecar files (JSON lines describing each GRIB message
in the corresponding .grib2 file), never the GRIB data itself.

A run counts as available for our sample only if, for EVERY requested step:
  * the .index file returns HTTP 200, and
  * the index contains an entry whose "param" is "tp".

Exit code 0 and prints the chosen run on success; exit code 1 if no candidate run qualifies.
"""

import datetime as dt
import json
import sys

import requests

BASE_URL = "https://data.ecmwf.int/forecasts"  # source "ecmwf" in ecmwf-opendata 0.3.35 (urls.py)
MODEL, RESOL, STREAM, TYPE = "ifs", "0p25", "oper", "fc"
SAMPLE_STEPS = [0, 3, 6, 144, 150, 240]
TIMEOUT_S = 30


def index_url(run: dt.datetime, step: int) -> str:
    # Mirrors HOURLY_PATTERN in ecmwf/opendata/client.py
    ymd = run.strftime("%Y%m%d")
    hh = run.strftime("%H")
    stamp = run.strftime("%Y%m%d%H%M%S")
    return (f"{BASE_URL}/{ymd}/{hh}z/{MODEL}/{RESOL}/{STREAM}/"
            f"{stamp}-{step}h-{STREAM}-{TYPE}.index")


def candidate_runs(now_utc: dt.datetime) -> list[dt.datetime]:
    """Newest-first 00/12 UTC runs covering the last ~2 days."""
    latest_cycle_hour = 12 if now_utc.hour >= 12 else 0
    start = now_utc.replace(hour=latest_cycle_hour, minute=0, second=0, microsecond=0)
    return [start - dt.timedelta(hours=12 * i) for i in range(4)]


def check_run(session: requests.Session, run: dt.datetime) -> tuple[bool, dict | None]:
    print(f"\nRun {run:%Y-%m-%d %H} UTC")
    all_ok = True
    example_entry = None
    for step in SAMPLE_STEPS:
        url = index_url(run, step)
        r = session.get(url, timeout=TIMEOUT_S)
        if r.status_code != 200:
            print(f"  step {step:>3} h: HTTP {r.status_code}  -> missing")
            all_ok = False
            continue
        lines = [ln for ln in r.text.splitlines() if ln.strip()]
        entries = [json.loads(ln) for ln in lines]  # a malformed line raises loudly
        tp = [e for e in entries if e.get("param") == "tp"]
        status = "tp present" if len(tp) == 1 else f"tp entries found: {len(tp)}  -> UNEXPECTED"
        if len(tp) != 1:
            all_ok = False
        else:
            example_entry = example_entry or tp[0]
        print(f"  step {step:>3} h: HTTP 200, {len(entries)} messages in file, {status}")
    return all_ok, example_entry


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    print(f"Current time: {now:%Y-%m-%d %H:%M} UTC")
    with requests.Session() as s:
        for run in candidate_runs(now):
            ok, example = check_run(s, run)
            if ok:
                print(f"\nCHOSEN RUN: {run:%Y-%m-%d %H} UTC (all {len(SAMPLE_STEPS)} sample steps have tp)")
                print("Example raw index entry for tp (verbatim from server):")
                print(json.dumps(example, indent=2))
                return 0
    print("\nNo candidate run has tp for all sample steps.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
