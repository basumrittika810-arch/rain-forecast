"""Demonstration only (not the production calculation): read stored cumulative tp values at a few
exact grid points from the sample file and show interval subtraction step by step. Read-only.

Usage:
    python scripts/demo_interval_subtraction.py <grib_file> <output_txt>
"""

import sys
from pathlib import Path

import eccodes
import numpy as np

# Exact 0.25-degree grid coordinates (no nearest-point logic involved).
POINTS = [
    ("Bay of Bengal, heaviest point in box", 12.5, 83.25),
    ("Grid point nearest Chennai (13.08N, 80.27E)", 13.0, 80.25),
    ("Assam, near Guwahati (3->6 h decrease seen)", 26.25, 91.25),
    ("Jharkhand (6->144 h decrease of 2 increments)", 23.25, 84.75),
    ("Eastern UP, near Varanasi (6->144 h decrease)", 25.5, 82.75),
]
PAIRS = [(0, 3), (3, 6), (6, 144), (144, 150), (150, 240), (0, 240)]


def main(argv):
    path, out_path = Path(argv[1]), Path(argv[2])
    lines = []

    def log(s=""):
        print(s)
        lines.append(s)

    fields, inc = {}, {}
    with open(path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                step = eccodes.codes_get(gid, "endStep")
                nj, ni = eccodes.codes_get(gid, "Nj"), eccodes.codes_get(gid, "Ni")
                fields[step] = eccodes.codes_get_values(gid).reshape(nj, ni)
                inc[step] = 2.0 ** eccodes.codes_get(gid, "binaryScaleFactor")
                lats = eccodes.codes_get_array(gid, "distinctLatitudes")
                lons = eccodes.codes_get_array(gid, "distinctLongitudes")
            finally:
                eccodes.codes_release(gid)
    steps = sorted(fields)

    for name, lat, lon in POINTS:
        r = int(np.where(lats == lat)[0][0])
        c = int(np.where(lons == lon)[0][0])
        log(f"\n=== {name}: lat={lats[r]}, lon={lons[c]} ===")
        log("  stored cumulative tp (m, exact)      = mm (x1000)")
        for s in steps:
            v = fields[s][r, c]
            log(f"  0->{s:<3}h : {v:.12f} m = {v * 1000:8.3f} mm   (stored in steps of {inc[s] * 1000:.4f} mm)")
        log("  interval = later cumulative - earlier cumulative")
        for a, b in PAIRS:
            d = fields[b][r, c] - fields[a][r, c]
            hours = b - a
            log(f"  {a:>3}->{b:<3}h ({hours:>3} h): {fields[b][r, c] * 1000:8.3f} - {fields[a][r, c] * 1000:8.3f} "
                f"= {d * 1000:8.3f} mm   avg rate {d * 1000 / hours:7.3f} mm/h")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
