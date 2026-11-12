"""Probe for the D-024 choices: abandoned / section / no-district places, places outside the box, spelling variants.
Usage: python -X utf8 scripts/probe_places.py data/geonames_raw"""
import collections, difflib, math, random, sys
raw = sys.argv[1]
adm2 = {}
for line in open(f"{raw}/admin2Codes.txt", encoding="utf-8"):
    code, name, ascii_, gid = line.rstrip("\n").split("\t")
    if code.startswith("IN.25."): adm2[code.split(".")[2]] = ascii_
P = [c for c in (l.rstrip("\n").split("\t") for l in open(f"{raw}/extracted/IN.txt", encoding="utf-8")) if c[10] == "25" and c[6] == "P"]
rng = random.Random(1)
def show(rows, n):
    for c in rng.sample(rows, min(n, len(rows))):
        print(f"   {c[2]:28s} {c[7]:5s} {c[4]:>9s} {c[5]:>9s} district={adm2.get(c[11], '-'):22s} pop={c[14]} alt={c[3][:50]}")
for code in ("PPLQ", "PPLX"):
    rows = [c for c in P if c[7] == code]
    print(f"\n== {code} ({len(rows)}): random 12")
    show(rows, 12)
    names = {c[2].lower() for c in rows}
    other = [c for c in P if c[7] not in ("PPLQ",) and c[7] != code and c[2].lower() in names]
    print(f"   {code} names that also exist as another (non-abandoned) place: {len({c[2].lower() for c in other})} of {len(names)}")
nod = [c for c in P if c[11] not in adm2]
print(f"\n== no district ({len(nod)}): by code {dict(collections.Counter(c[7] for c in nod))}; random 12")
show(nod, 12)
print("   no-district lat range", min(float(c[4]) for c in nod), max(float(c[4]) for c in nod), "lon range", min(float(c[5]) for c in nod), max(float(c[5]) for c in nod))
snap = lambda x: math.floor(x / 0.25 + 0.5) * 0.25
box = (8.083333, 13.583333, 76.25, 80.333333)
out = [c for c in P if not (box[0] <= float(c[4]) <= box[1] and box[2] <= float(c[5]) <= box[3])]
print(f"\n== outside box ({len(out)})")
for c in out:
    la, lo = float(c[4]), float(c[5])
    dla = max(box[0]-la, la-box[1], 0); dlo = max(box[2]-lo, lo-box[3], 0)
    print(f"   {c[2]:22s} {la:.5f} {lo:.5f} {adm2.get(c[11], '-'):16s} outside by lat {dla*111:.2f} km, lon {dlo*111*math.cos(la*math.pi/180):.2f} km -> grid {snap(la):.2f},{snap(lo):.2f}")
print("   box needed to cover all TN places: lat", min(float(c[4]) for c in P), max(float(c[4]) for c in P), "lon", min(float(c[5]) for c in P), max(float(c[5]) for c in P))
# spelling: OSM spelling (typed by a user) -> does GeoNames find it?
names = sorted({c[2] for c in P})
low = [n.lower() for n in names]
pairs = [("Soriyampatti", "Soviriyampatti"), ("Kidarakulam", "Kidarangulam"), ("Valavettikuppam", "Valavettikkuppamtattanur"),
         ("Muruganpalayam", "Murugampalaiyam"), ("Thoothukudi", "Thoothukkudi"), ("Sivagangai", "Sivaganga"),
         ("Tiruttani", "Thiruthani"), ("Rajagoundanpatti", "Rajakavundanpatti"), ("Kanyakumari", "Kanniyakumari"),
         ("Tuticorin", "Thoothukkudi"), ("Nagapattinam", "Nagapattinam"), ("Palayamkottai", "Palayankottai")]
print("\n== spelling probe: typed (OSM / common spelling) -> what each method returns")
for typed, target in pairs:
    t = typed.lower()
    prefix = [n for n, l in zip(names, low) if l.startswith(t)]
    alt = [c[2] for c in P if t in [a.strip().lower() for a in c[3].split(",")]]
    close = difflib.get_close_matches(t, low, n=5, cutoff=0.8)
    print(f"   {typed:18s} target {target:24s} start-of-name: {prefix[:3]}  alt-names: {sorted(set(alt))[:3]}  close(0.8): {close}  target-in-close: {target.lower() in close}")
