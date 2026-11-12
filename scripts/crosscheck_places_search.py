"""Cross-check (D-024): look up a fixed random sample of GeoNames places BY NAME in OpenStreetMap Nominatim (1 request / 1.5 s).
Usage: python scripts/crosscheck_places_search.py data/geonames_raw"""
import json, math, random, sys, time, urllib.parse, urllib.request
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
def km(a, b, c, d):
    p = math.pi / 180
    return 6371 * 2 * math.asin(math.sqrt(math.sin((c-a)*p/2)**2 + math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2))
print("kind    | GeoNames name, district | GeoNames lat,lon | OSM best match (name) | OSM lat,lon | distance km | grid cell same?")
snap = lambda x: math.floor(x / 0.25 + 0.5) * 0.25
for kind, group in (("village", villages), ("town", towns)):
    for c in group:
        q = urllib.parse.urlencode({"q": f"{c[2]}, {adm2[c[11]]}, Tamil Nadu, India", "format": "jsonv2", "limit": 5, "countrycodes": "in"})
        req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + q, headers={"User-Agent": "rain-forecast-datacheck/0.1 (one-off coordinate cross-check)"})
        res = json.loads(urllib.request.urlopen(req, timeout=60).read())
        time.sleep(1.5)
        glat, glon = float(c[4]), float(c[5])
        if not res:
            print(f"{kind:7s} | {c[2]}, {adm2[c[11]]} | {glat:.4f},{glon:.4f} | NOT FOUND in OSM"); continue
        best = min(res, key=lambda r: km(glat, glon, float(r["lat"]), float(r["lon"])))
        d = km(glat, glon, float(best["lat"]), float(best["lon"]))
        same = (snap(glat), snap(glon)) == (snap(float(best["lat"])), snap(float(best["lon"])))
        print(f"{kind:7s} | {c[2]}, {adm2[c[11]]} | {glat:.4f},{glon:.4f} | {best['display_name'][:60]} | {float(best['lat']):.4f},{float(best['lon']):.4f} | {d:.2f} | {same}")
