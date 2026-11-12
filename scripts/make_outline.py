"""Make web/tn-outline.svg, the faint Tamil Nadu outline used as the website watermark (decision D-028).

Source: Natural Earth 1:50m admin-1 states and provinces (public domain), feature "Tamil Nadu" (IN-TN), from
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces.geojson
Decoration only: nothing is calculated from this outline.

Usage: python scripts/make_outline.py data/naturalearth/ne_50m_admin1.geojson
"""

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "tn-outline.svg"


def main(src: str) -> None:
    d = json.loads(Path(src).read_text(encoding="utf-8"))
    ring = next(f for f in d["features"] if f["properties"].get("name") == "Tamil Nadu")["geometry"]["coordinates"][0]
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))            # equirectangular: shrink longitude so the shape is not stretched
    lon_min, lat_max = min(p[0] for p in ring), max(p[1] for p in ring)
    xs = [(p[0] - lon_min) * k for p in ring]
    ys = [lat_max - p[1] for p in ring]
    scale = 100 / max(max(xs), max(ys))
    pts = " ".join(f"{x * scale:.2f},{y * scale:.2f}" for x, y in zip(xs, ys))
    w, h = max(xs) * scale, max(ys) * scale
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 {w + 4:.1f} {h + 4:.1f}">'
           f'<!-- Tamil Nadu outline: Natural Earth 1:50m admin-1 (public domain). Decoration only. -->'
           f'<polygon points="{pts}" fill="#2e8b57" fill-opacity="0.10" stroke="#1f6fc0" stroke-opacity="0.35" '
           f'stroke-width="0.6" stroke-linejoin="round"/></svg>\n')
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg)} bytes, {len(ring)} points)")


if __name__ == "__main__":
    main(*sys.argv[1:])
