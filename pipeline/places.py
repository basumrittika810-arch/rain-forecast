"""Place-name search for Tamil Nadu (decision D-024). Standard library only (no ecCodes): used by the API.

Build the committed list from a GeoNames download (raw files stay in git-ignored data/):
    python -m pipeline.places data/geonames_raw
    (folder with extracted/IN.txt, admin2Codes.txt and IN.zip, from https://download.geonames.org/export/dump/)

Rules (owner decisions, D-024):
  * keep populated places (feature class P) of Tamil Nadu (admin1 25); drop abandoned places (PPLQ) and places
    without a known district (the inspection found such entries from Karnataka, Kerala and Puducherry);
  * district names cleaned for display ("Tirunelveli Kattabo" -> "Tirunelveli", " district" suffix removed);
  * English only for now: alternative names kept only if written in plain ASCII letters;
  * every kept place must lie inside the configured region box, otherwise building fails (nothing dropped silently).
Search: exact name / alternative name, then start of name; only if nothing matches, close spellings ("did you mean").
"""

import csv
import datetime as dt
import difflib
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pipeline.config import Region, load_region

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLACES_PATH = ROOT / "config" / "places_tamil_nadu.csv"
DEFAULT_SOURCE_PATH = ROOT / "config" / "places_tamil_nadu.source.json"
TAMIL_NADU_ADMIN1 = "25"
ATTRIBUTION = "Place names and coordinates: GeoNames (geonames.org), CC BY 4.0"
MIN_QUERY = 2
SUGGESTION_CUTOFF = 0.8   # difflib similarity; 11/12 spelling variants found in the D-024 probe

_ASCII_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 .'()-]*$")


class PlaceDataError(ValueError):
    """The GeoNames input does not satisfy the rules above."""


@dataclass(frozen=True)
class Place:
    geonameid: int
    name: str
    district: str
    lat: float
    lon: float
    population: int
    alt_names: tuple[str, ...]


def normalise(s: str) -> str:
    """Lower case, letters and digits only: 'Thyagaraya Nagar' and 'thyagarayanagar' compare equal."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def clean_district(name: str) -> str:
    name = name.strip()
    if name == "Tirunelveli Kattabo":    # GeoNames' truncated name for Tirunelveli district
        return "Tirunelveli"
    if name.endswith(" district"):
        name = name[: -len(" district")]
    return name


def _districts(admin2_path: Path) -> dict[str, str]:
    out = {}
    with open(admin2_path, encoding="utf-8") as f:
        for line in f:
            code, _name, ascii_name, _gid = line.rstrip("\n").split("\t")
            country, admin1, admin2 = code.split(".", 2)
            if country == "IN" and admin1 == TAMIL_NADU_ADMIN1:
                out[admin2] = clean_district(ascii_name)
    return out


def build_places(geonames_path: Path, admin2_path: Path, region: Region | None = None) -> list[Place]:
    region = region or load_region()
    districts = _districts(admin2_path)
    places, outside = [], []
    with open(geonames_path, encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) != 19:
                raise PlaceDataError(f"expected 19 columns, got {len(c)}: {line[:80]!r}")
            if c[10] != TAMIL_NADU_ADMIN1 or c[6] != "P" or c[7] == "PPLQ" or c[11] not in districts:
                continue
            name = c[2].strip()
            seen, alts = {normalise(name)}, []
            for a in c[3].split(","):
                a = a.strip()
                if a and _ASCII_NAME.match(a) and normalise(a) not in seen:
                    seen.add(normalise(a))
                    alts.append(a)
            p = Place(int(c[0]), name, districts[c[11]], float(c[4]), float(c[5]), int(c[14] or 0), tuple(alts))
            (places if region.contains(p.lat, p.lon) else outside).append(p)
    if outside:
        raise PlaceDataError(f"{len(outside)} place(s) outside region {region.name}: "
                             + ", ".join(f"{p.name} ({p.lat}, {p.lon})" for p in outside[:10]))
    return sorted(places, key=lambda p: (p.name.lower(), p.district, p.geonameid))


FIELDS = ["geonameid", "name", "district", "lat", "lon", "population", "alt_names"]


def write_places(places: list[Place], path: Path) -> None:
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(FIELDS)
        for p in places:
            w.writerow([p.geonameid, p.name, p.district, repr(p.lat), repr(p.lon), p.population, ";".join(p.alt_names)])
    tmp.replace(path)


def load_places(path: Path = DEFAULT_PLACES_PATH) -> list[Place]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f)
        if rows.fieldnames != FIELDS:
            raise PlaceDataError(f"{path}: unexpected columns {rows.fieldnames}")
        return [Place(int(r["geonameid"]), r["name"], r["district"], float(r["lat"]), float(r["lon"]),
                      int(r["population"]), tuple(a for a in r["alt_names"].split(";") if a)) for r in rows]


class PlaceIndex:
    def __init__(self, places: list[Place]):
        self.places = list(places)
        self._keys: dict[str, list[tuple[Place, str]]] = defaultdict(list)   # normalised name -> (place, spelling)
        for p in self.places:
            for spelling in (p.name, *p.alt_names):
                self._keys[normalise(spelling)].append((p, spelling))
        self._key_list = list(self._keys)

    @staticmethod
    def _row(p: Place, matched: str) -> dict:
        return {"geonameid": p.geonameid, "name": p.name, "district": p.district, "lat": p.lat, "lon": p.lon,
                "matched": matched}

    def search(self, q: str, limit: int = 10) -> dict:
        key = normalise(q)
        if len(key) < MIN_QUERY:
            raise ValueError(f"query needs at least {MIN_QUERY} letters or digits")
        # tier: 0 exact name, 1 exact alternative name, 2 name starts with, 3 alternative name starts with
        best: dict[int, tuple] = {}
        for k, entries in self._keys.items():
            if not k.startswith(key):
                continue
            for p, spelling in entries:
                tier = (0 if k == key else 2) + (0 if spelling == p.name else 1)
                rank = (tier, -p.population, p.name.lower(), p.district, p.geonameid)
                if p.geonameid not in best or rank < best[p.geonameid][0]:
                    best[p.geonameid] = (rank, p, spelling)
        if best:
            hits = sorted(best.values(), key=lambda t: t[0])[:limit]
            return {"query": q, "kind": "matches", "results": [self._row(p, s) for _, p, s in hits]}
        close = difflib.get_close_matches(key, self._key_list, n=limit, cutoff=SUGGESTION_CUTOFF)
        seen, results = set(), []
        for k in close:   # most similar spelling first; within it, bigger places first
            for p, spelling in sorted(self._keys[k], key=lambda e: (-e[0].population, e[0].district, e[0].geonameid)):
                if p.geonameid not in seen and len(results) < limit:
                    seen.add(p.geonameid)
                    results.append(self._row(p, spelling))
        return {"query": q, "kind": "suggestions" if results else "none", "results": results}

    def nearest(self, lat: float, lon: float) -> dict:
        """Closest listed place (great-circle distance), for naming a GPS position (D-028). Ties: lower geonameid."""
        best = min(self.places, key=lambda p: (_km(lat, lon, p.lat, p.lon), p.geonameid))
        return {**self._row(best, best.name), "distance_km": round(_km(lat, lon, best.lat, best.lon), 1)}


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.pi / 180
    a = (math.sin((lat2 - lat1) * r / 2) ** 2
         + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def main(raw_dir: str) -> None:
    raw = Path(raw_dir)
    places = build_places(raw / "extracted" / "IN.txt", raw / "admin2Codes.txt")
    write_places(places, DEFAULT_PLACES_PATH)
    source = {
        "source": "GeoNames IN.zip, https://download.geonames.org/export/dump/IN.zip",
        "sha256": hashlib.sha256((raw / "IN.zip").read_bytes()).hexdigest(),
        "admin2_sha256": hashlib.sha256((raw / "admin2Codes.txt").read_bytes()).hexdigest(),
        "licence": "CC BY 4.0",
        "attribution": ATTRIBUTION,
        "rules": "Tamil Nadu (admin1 25), feature class P, without PPLQ (abandoned) and without unknown district; "
                 "ASCII alternative names only; all inside config/settings.toml region box (decision D-024)",
        "places": len(places),
        "built_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    DEFAULT_SOURCE_PATH.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(places)} places to {DEFAULT_PLACES_PATH}")


if __name__ == "__main__":
    main(*sys.argv[1:])
