"""Cross-check (D-024): ask OpenStreetMap Nominatim which place and district lie AT each sampled GeoNames coordinate.
Usage: python scripts/crosscheck_places_reverse.py data/geonames_raw"""
import json, random, sys, time, urllib.parse, urllib.request
raw = sys.argv[1]
adm2 = {}
for line in open(f"{raw}/admin2Codes.txt", encoding="utf-8"):
    code, name, ascii_, gid = line.rstrip("\n").split("\t")
    if code.startswith("IN.25."): adm2[code.split(".")[2]] = ascii_.replace(" district", "").replace(" Kattabo", "")
P = [c for c in (l.rstrip("\n").split("\t") for l in open(f"{raw}/extracted/IN.txt", encoding="utf-8"))
     if c[10] == "25" and c[6] == "P" and c[7] == "PPL" and c[11] in adm2]
rng = random.Random(20261112)
villages = rng.sample([c for c in P if int(c[14] or 0) == 0], 20)
towns = rng.sample([c for c in P if int(c[14] or 0) >= 15000], 10)
print("kind | GeoNames name | GeoNames district | OSM place at that point | OSM district | OSM state")
for kind, group in (("village", villages), ("town", towns)):
    for c in group:
        q = urllib.parse.urlencode({"lat": c[4], "lon": c[5], "format": "jsonv2", "zoom": 14, "accept-language": "en"})
        req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q, headers={"User-Agent": "rain-forecast-datacheck/0.1 (one-off coordinate cross-check)"})
        a = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("address", {})
        time.sleep(1.5)
        place = a.get("village") or a.get("hamlet") or a.get("town") or a.get("suburb") or a.get("city") or "-"
        print(f"{kind} | {c[2]} | {adm2[c[11]]} | {place} | {a.get('state_district') or a.get('county') or '-'} | {a.get('state','-')}")
