"""Place-list inspection (D-024): counts, feature codes, districts, Tamil names for GeoNames Tamil Nadu.
Usage: python scripts/inspect_places.py data/geonames_raw   (folder with IN.zip extracted to extracted/, admin2Codes.txt)"""
import collections, re, sys
raw = sys.argv[1]
adm2 = {}
for line in open(f"{raw}/admin2Codes.txt", encoding="utf-8"):
    code, name, ascii_, gid = line.rstrip("\n").split("\t")
    if code.startswith("IN.25."):
        adm2[code.split(".")[2]] = ascii_
rows = []
for line in open(f"{raw}/extracted/IN.txt", encoding="utf-8"):
    c = line.rstrip("\n").split("\t")
    if c[10] == "25":
        rows.append(c)
print("all Tamil Nadu (admin1=25) records:", len(rows))
cls = collections.Counter(r[6] for r in rows)
print("by feature class:", dict(cls.most_common()))
P = [r for r in rows if r[6] == "P"]
print("\npopulated places (class P):", len(P))
print("by feature code:", dict(collections.Counter(r[7] for r in P).most_common()))
print("with population > 0:", sum(int(r[14] or 0) > 0 for r in P))
for lim in (1000, 5000, 15000):
    print(f"  population >= {lim}:", sum(int(r[14] or 0) >= lim for r in P))
print("with admin2 (district) code:", sum(bool(r[11]) for r in P), "; code known in admin2Codes:", sum(r[11] in adm2 for r in P))
print("district names in admin2Codes for TN:", len(adm2))
print(sorted(adm2.values()))
cnt = collections.Counter(adm2.get(r[11], "<none>") for r in P)
print("places per district:", dict(cnt.most_common()))
tamil = re.compile("[஀-௿]")
print("\nwith any alternate name:", sum(bool(r[3]) for r in P), "; with Tamil-script alternate name:", sum(bool(tamil.search(r[3])) for r in P))
box = (8.083333, 13.583333, 76.25, 80.333333)
inbox = [r for r in P if box[0] <= float(r[4]) <= box[1] and box[2] <= float(r[5]) <= box[3]]
print("inside forecast box:", len(inbox), "; outside:", len(P) - len(inbox))
for r in P:
    if r not in inbox: print("   outside:", r[2], r[4], r[5], adm2.get(r[11]))
names = collections.defaultdict(set)
for r in P: names[r[2].lower()].add(adm2.get(r[11], "?"))
dup = {k: v for k, v in names.items() if len(v) > 1}
print("\nnames shared by >1 district:", len(dup), "of", len(names), "distinct names; e.g.", [(k, sorted(v)) for k, v in list(dup.items())[:5]])
print("\nmodification dates: min", min(r[18] for r in P), "max", max(r[18] for r in P))
for q in ["Chennai", "Madurai", "Coimbatore", "Thanjavur", "Tiruchirappalli", "Trichy", "Tirunelveli", "Salem", "Kanniyakumari", "Melur", "Vellore", "Nagappattinam", "Ooty", "Udhagamandalam", "Kumbakonam", "Mayiladuthurai"]:
    hits = [r for r in P if r[2].lower() == q.lower() or q.lower() in [a.lower() for a in r[3].split(",")]]
    print(f"{q:16s}", [(r[2], r[4], r[5], adm2.get(r[11]), r[7], r[14]) for r in hits][:4])
