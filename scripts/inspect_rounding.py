"""Empirical test of the encoder's rounding mode (nearest vs always-down vs always-up). Read-only.

GRIB metadata defines how to DECODE values (value = R + k * 2^E) / 10^D) but not how the producer
ROUNDED when encoding. This script tests it from the data.

Idea: at a step where the increment doubles (fine f -> coarse 2f), look at grid points whose
earlier stored value is an ODD multiple of f (sits between coarse marks) and that show no rain
change just before and just after the pair (quiet points). For such a point with ~no rain in between:
  * round-down (floor): the later value always drops by f      -> nearly all "-f"
  * round-up  (ceil)  : the later value always rises by f      -> nearly all "+f"
  * round-to-nearest  : drops or rises depending on the true value -> a mix of "-f" and "+f"

Usage:
    python scripts/inspect_rounding.py <run_grib> <output_txt>
"""

import sys
from collections import Counter
from pathlib import Path

import eccodes
import numpy as np

lines = []


def log(s=""):
    print(s)
    lines.append(s)


def main(argv):
    run_path, out_path = Path(argv[1]), Path(argv[2])
    fields, E = {}, {}
    with open(run_path, "rb") as f:
        while (gid := eccodes.codes_grib_new_from_file(f)) is not None:
            try:
                s = int(eccodes.codes_get(gid, "endStep"))
                E[s] = eccodes.codes_get(gid, "binaryScaleFactor")
                nj, ni = eccodes.codes_get(gid, "Nj"), eccodes.codes_get(gid, "Ni")
                k = eccodes.codes_get_values(gid).reshape(nj, ni) / 2.0 ** E[s]
                fields[s] = np.round(k).astype(np.int64)  # exact integers (verified: deviation 0)
            finally:
                eccodes.codes_release(gid)
    steps = sorted(fields)
    log("GRIB metadata does not record the encoder's rounding mode; testing it from the data.")

    for i in range(1, len(steps) - 2):
        prev, a, b, nxt = steps[i - 1], steps[i], steps[i + 1], steps[i + 2]
        if E[b] != E[a] + 1:
            continue  # only pairs where the increment doubles
        # express everything in units of the FINE increment f = 2^E[a]
        A = fields[a]                     # fine units
        B = fields[b] * 2                 # coarse -> fine units
        P = fields[prev] * 2 ** (E[prev] - E[a]) if E[prev] >= E[a] else None
        N = fields[nxt] * 2 ** (E[nxt] - E[a])
        quiet = (A % 2 == 1)
        if P is not None:
            quiet &= (P == A)             # no change prev -> a
        quiet &= (N == B)                 # no change b -> next
        diffs = Counter((B[quiet] - A[quiet]).tolist())
        n = int(quiet.sum())
        down, up = diffs.get(-1, 0), diffs.get(1, 0)
        log(f"\nPair {a}->{b} h (increment {2.0 ** E[a] * 1000:.4f} -> {2.0 ** E[b] * 1000:.4f} mm), "
            f"quiet points with odd earlier value: {n}")
        log(f"  change in fine increments: " + ", ".join(f"{k:+d}: {v}" for k, v in sorted(diffs.items())))
        if n:
            log(f"  down (-1): {down} ({100 * down / n:.1f}%)   up (+1): {up} ({100 * up / n:.1f}%)   "
                f"other: {n - down - up}")
            log("  expected: round-down ~100% down; round-up ~100% up; nearest = a mix of both")

        # Sharper test: require the later value to stay unchanged for longer dry periods after b.
        # Under round-down, '+1' needs real rain inside a->b only; isolated rain in exactly that slot
        # becomes rarer as the dry period after it grows, so the '+1' share should fall towards 0.
        # Under nearest rounding, '+1' happens without any rain, so the share should stay high.
        log("  Longer dry period after the pair (later value unchanged up to step X):")
        base = (A % 2 == 1)
        if P is not None:
            base &= (P == A)
        for horizon in (12, 24, 48, 72):
            later = [s for s in steps if b < s <= b + horizon]
            m = base.copy()
            for s in later:
                m &= (fields[s] * 2 ** (E[s] - E[a]) == B)
            d = B[m] - A[m]
            n2 = int(m.sum())
            if n2:
                log(f"    dry for {horizon:>2} h after: points {n2:>6}  down {int((d == -1).sum()):>6} "
                    f"({100 * (d == -1).mean():5.1f}%)  up {int((d == 1).sum()):>6} ({100 * (d == 1).mean():5.1f}%)")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
