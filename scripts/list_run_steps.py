"""List which forecast steps exist on the ECMWF open-data server for one HRES run, and what the
`tp` entry of each step's .index file says. Metadata only: no GRIB data is downloaded.

Usage:
    python scripts/list_run_steps.py YYYYMMDD HH <output_txt>

Evidence produced:
  * the step list derived from the server's directory listing of the run
  * for every step: whether its .index lists exactly one `tp` message, and the index's `step` field
  * a summary of the spacing between consecutive steps
"""

import json
import re
import sys
from pathlib import Path

import requests

BASE_URL = "https://data.ecmwf.int/forecasts"
TIMEOUT_S = 30


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    ymd, hh, out_path = argv[1], argv[2], Path(argv[3])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines_out = []

    def log(s=""):
        print(s)
        lines_out.append(s)

    run_dir = f"{BASE_URL}/{ymd}/{hh}z/ifs/0p25/oper/"
    r = requests.get(run_dir, timeout=TIMEOUT_S)
    log(f"Directory listing {run_dir} -> HTTP {r.status_code}")
    r.raise_for_status()
    pattern = re.compile(rf"{ymd}{hh}0000-(\d+)h-oper-fc\.(grib2|index)")
    found = {}
    for step, ext in pattern.findall(r.text):
        found.setdefault(int(step), set()).add(ext)
    steps = sorted(found)
    log(f"Steps with files listed: {len(steps)}")
    log(f"Steps: {steps}")
    incomplete = [s for s in steps if found[s] != {"grib2", "index"}]
    log(f"Steps missing either .grib2 or .index in listing: {incomplete}")

    gaps = {}
    for a, b in zip(steps[:-1], steps[1:]):
        gaps.setdefault(b - a, []).append(f"{a}->{b}")
    log("Spacing between consecutive steps:")
    for g, pairs in sorted(gaps.items()):
        log(f"  {g} h: {len(pairs)} intervals, first {pairs[0]}, last {pairs[-1]}")

    log("\nPer-step tp entry from the .index file (verbatim 'step' field):")
    with requests.Session() as s:
        for st in steps:
            url = f"{run_dir}{ymd}{hh}0000-{st}h-oper-fc.index"
            ri = s.get(url, timeout=TIMEOUT_S)
            if ri.status_code != 200:
                log(f"  step {st:>3}: index HTTP {ri.status_code}")
                continue
            entries = [json.loads(x) for x in ri.text.splitlines() if x.strip()]
            tp = [e for e in entries if e.get("param") == "tp"]
            if len(tp) != 1:
                log(f"  step {st:>3}: tp entries = {len(tp)}  <-- UNEXPECTED")
                continue
            log(f"  step {st:>3}: tp step field = {tp[0]['step']!r:>10}  length={tp[0]['_length']}")

    # Negative check: a step that should not exist in the 6-hourly range
    probe = f"{run_dir}{ymd}{hh}0000-147h-oper-fc.index"
    rp = requests.get(probe, timeout=TIMEOUT_S)
    log(f"\nProbe for a non-listed step (147 h): HTTP {rp.status_code}")

    out_path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
