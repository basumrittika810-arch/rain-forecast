"""Place-name search (decision D-024): building the list from GeoNames, loading it, searching it, and the API endpoint.

Builder tests use tiny hand-made GeoNames files (same 19 tab-separated columns as the real IN.txt).
Real-list tests check the committed config/places_tamil_nadu.csv against numbers counted by hand in the D-024 inspection.
"""

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from pipeline.config import Region, load_region
from pipeline.grid import region_grid_points, snap_to_grid
from pipeline.places import (DEFAULT_PLACES_PATH, DEFAULT_SOURCE_PATH, Place, PlaceDataError, PlaceIndex,
                             build_places, clean_district, load_places, normalise, write_places)

BOX = Region("Test TN", 8.0, 13.6, 76.2, 80.4)


def geonames_line(gid, name, lat, lon, fclass="P", fcode="PPL", admin1="25", admin2="583", pop=0, alt="", ascii_name=None):
    cols = [str(gid), name, ascii_name or name, alt, str(lat), str(lon), fclass, fcode, "IN", "", admin1, admin2,
            "", "", str(pop), "", "100", "Asia/Kolkata", "2026-01-01"]
    assert len(cols) == 19
    return "\t".join(cols)


ADMIN2 = "\n".join([
    "IN.25.583\tMadurai\tMadurai\t1",
    "IN.25.600\tTiruvannamalai\tTiruvannamalai\t2",
    "IN.25.603\tChennai\tChennai\t3",
    "IN.25.614\tTirunelveli Kattabo\tTirunelveli Kattabo\t4",
    "IN.25.650\tRanipet district\tRanipet district\t5",
    "IN.13.583\tErnakulam\tErnakulam\t6",          # same district code, other state: must not leak
]) + "\n"


@pytest.fixture
def raw(tmp_path):
    rows = [
        geonames_line(1, "Madurai", 9.919, 78.11953, fcode="PPLA2", pop=1465625, alt="Madura,Maturai,மதுரை,madurai"),
        geonames_line(2, "Madurai", 12.64275, 79.47669, admin2="600"),
        geonames_line(3, "Oldvillage", 10.0, 78.0, fcode="PPLQ"),                 # abandoned -> dropped
        geonames_line(4, "Nodistrict", 11.0, 79.0, admin2=""),                    # no district -> dropped
        geonames_line(5, "Badcode", 11.0, 79.0, admin2="999"),                    # unknown district code -> dropped
        geonames_line(6, "Keralatown", 10.0, 76.3, admin1="13"),                  # other state -> dropped
        geonames_line(7, "Some River", 10.5, 78.5, fclass="H", fcode="STM"),      # not a populated place -> dropped
        geonames_line(8, "Thyagaraya Nagar", 13.03944, 80.24, fcode="PPLX", admin2="603"),   # section -> kept
        geonames_line(9, "Palai", 8.7, 77.7, admin2="614"),
        geonames_line(10, "Ranivillage", 12.9, 79.3, admin2="650"),
        geonames_line(11, "Bahūr", 11.8, 79.7, admin2="603", ascii_name="Bahur"),
    ]
    g = tmp_path / "IN.txt"
    g.write_text("\n".join(rows) + "\n", encoding="utf-8")
    a = tmp_path / "admin2Codes.txt"
    a.write_text(ADMIN2, encoding="utf-8")
    return g, a


# ---------------------------------------------------------------- building the list

def test_builder_keeps_and_drops_the_right_places(raw):
    places = build_places(*raw, region=BOX)
    assert sorted(p.geonameid for p in places) == [1, 2, 8, 9, 10, 11]


def test_builder_district_names(raw):
    by_id = {p.geonameid: p for p in build_places(*raw, region=BOX)}
    assert by_id[1].district == "Madurai" and by_id[2].district == "Tiruvannamalai"
    assert by_id[9].district == "Tirunelveli"          # "Tirunelveli Kattabo" cleaned
    assert by_id[10].district == "Ranipet"             # " district" suffix removed
    assert by_id[8].district == "Chennai"


@pytest.mark.parametrize("raw_name, cleaned", [
    ("Tirunelveli Kattabo", "Tirunelveli"), ("Ranipet district", "Ranipet"), ("Chengalpattu district", "Chengalpattu"),
    ("Madurai", "Madurai"), ("Nilgiris", "Nilgiris"),
])
def test_clean_district(raw_name, cleaned):
    assert clean_district(raw_name) == cleaned


def test_builder_fields_and_alt_names(raw):
    by_id = {p.geonameid: p for p in build_places(*raw, region=BOX)}
    m = by_id[1]
    assert (m.name, m.lat, m.lon, m.population) == ("Madurai", 9.919, 78.11953, 1465625)
    assert m.alt_names == ("Madura", "Maturai")       # Tamil script dropped (English only, D-024); copy of name dropped
    assert by_id[11].name == "Bahur"                   # plain-ASCII name is used


def test_builder_refuses_place_outside_region(raw):
    small = Region("Too small", 9.0, 13.6, 76.2, 80.4)   # excludes Palai (8.7 N)
    with pytest.raises(PlaceDataError, match="Palai"):
        build_places(*raw, region=small)


def test_builder_output_is_sorted_and_round_trips(raw, tmp_path):
    places = build_places(*raw, region=BOX)
    assert places == sorted(places, key=lambda p: (p.name.lower(), p.district, p.geonameid))
    path = tmp_path / "places.csv"
    write_places(places, path)
    assert load_places(path) == places


# ---------------------------------------------------------------- searching

def P(gid, name, district, pop=0, alt=(), lat=10.0, lon=78.0):
    return Place(gid, name, district, lat, lon, pop, tuple(alt))


INDEX = PlaceIndex([
    P(1, "Madurai", "Madurai", 1465625, ("Madura",), 9.919, 78.11953),
    P(2, "Madurai", "Tiruvannamalai"),
    P(3, "Madurai", "Chengalpattu"),
    P(4, "Maduraipakkam", "Kancheepuram", 90000),
    P(5, "Melur", "Madurai", 40017),
    P(6, "Melur", "Dharmapuri"),
    P(7, "Melurpatti", "Salem", 50000),
    P(8, "Tiruchirappalli", "Tiruchirappalli", 1022518, ("Trichy", "Tiruchi")),
    P(9, "Kidarangulam", "Tenkasi"),
    P(10, "Kidarikulam", "Tirunelveli"),
    P(11, "Thyagaraya Nagar", "Chennai"),
])


def names(result):
    return [(r["name"], r["district"]) for r in result["results"]]


def test_exact_name_first_biggest_place_first_then_start_of_name():
    r = INDEX.search("madurai")
    assert r["kind"] == "matches"
    assert names(r) == [("Madurai", "Madurai"), ("Madurai", "Chengalpattu"), ("Madurai", "Tiruvannamalai"),
                        ("Maduraipakkam", "Kancheepuram")]


def test_result_fields():
    first = INDEX.search("madurai")["results"][0]
    assert first == {"geonameid": 1, "name": "Madurai", "district": "Madurai", "lat": 9.919, "lon": 78.11953,
                     "matched": "Madurai"}


@pytest.mark.parametrize("q", ["  MADURAI ", "Ma-durai", "madurai."])
def test_case_spaces_and_punctuation_ignored(q):
    assert names(INDEX.search(q))[0] == ("Madurai", "Madurai")


def test_same_name_in_several_districts_all_shown_with_district():
    assert names(INDEX.search("Melur"))[:2] == [("Melur", "Madurai"), ("Melur", "Dharmapuri")]


def test_exact_name_beats_bigger_start_of_name_match():
    assert names(INDEX.search("melur")) == [("Melur", "Madurai"), ("Melur", "Dharmapuri"), ("Melurpatti", "Salem")]


@pytest.mark.parametrize("q", ["trichy", "Tiruchi", "tiruchira"])
def test_alternative_names_and_start_of_name(q):
    r = INDEX.search(q)
    assert r["kind"] == "matches" and names(r)[0] == ("Tiruchirappalli", "Tiruchirappalli")


def test_alternative_name_match_says_what_matched():
    assert INDEX.search("trichy")["results"][0]["matched"] == "Trichy"


def test_spaces_inside_names_ignored():
    assert names(INDEX.search("thyagarayanagar")) == [("Thyagaraya Nagar", "Chennai")]


def test_did_you_mean_when_nothing_matches():
    r = INDEX.search("kidarakulam")
    assert r["kind"] == "suggestions"
    assert set(names(r)) == {("Kidarangulam", "Tenkasi"), ("Kidarikulam", "Tirunelveli")}


def test_nothing_found():
    assert INDEX.search("zzqqxxww") == {"query": "zzqqxxww", "kind": "none", "results": []}


def test_limit():
    assert names(INDEX.search("madurai", limit=2)) == [("Madurai", "Madurai"), ("Madurai", "Chengalpattu")]


@pytest.mark.parametrize("q", ["", "m", " - ", "1"])
def test_too_short_query_refused(q):
    with pytest.raises(ValueError):
        INDEX.search(q)


@pytest.mark.parametrize("s, expected", [("Thyagaraya Nagar", "thyagarayanagar"), ("Ko-Su-Mani Nagar", "kosumaninagar"),
                                         ("  Melur. ", "melur")])
def test_normalise(s, expected):
    assert normalise(s) == expected


# ---------------------------------------------------------------- API endpoint

@pytest.fixture
def client(tmp_path):
    path = tmp_path / "places.csv"
    write_places(INDEX.places, path)
    # no forecast published at this path: place search must still work
    return TestClient(create_app(latest_path=tmp_path / "missing.json", places_path=path))


def test_api_places(client):
    r = client.get("/api/places", params={"q": "melur"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "matches" and [x["district"] for x in body["results"]] == ["Madurai", "Dharmapuri", "Salem"]
    assert "GeoNames" in body["attribution"] and "CC BY 4.0" in body["attribution"]


def test_api_places_suggestions_and_none(client):
    assert client.get("/api/places", params={"q": "kidarakulam"}).json()["kind"] == "suggestions"
    assert client.get("/api/places", params={"q": "zzqqxxww"}).json()["results"] == []


def test_api_places_works_without_forecast(client):
    assert client.get("/api/forecast", params={"lat": 10, "lon": 78}).status_code == 503
    assert client.get("/api/places", params={"q": "madurai"}).status_code == 200


@pytest.mark.parametrize("params", [{}, {"q": "m"}, {"q": " - "}, {"q": "a" * 101}, {"q": "madurai", "limit": 0},
                                    {"q": "madurai", "limit": 51}])
def test_api_places_bad_requests_are_422(client, params):
    assert client.get("/api/places", params=params).status_code == 422


# ---------------------------------------------------------------- the committed real list

@pytest.fixture(scope="module")
def real():
    return load_places(DEFAULT_PLACES_PATH)


def test_real_list_count(real):
    # D-024 inspection: 40,444 populated places - 291 abandoned - 163 without district + 7 that are both = 39,997
    assert len(real) == 39_997
    assert len({p.geonameid for p in real}) == len(real)


def test_real_list_districts(real):
    assert {p.district for p in real} == {
        "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode",
        "Kallakurichi", "Kancheepuram", "Kanniyakumari", "Karur", "Krishnagiri", "Madurai", "Mayiladuthurai",
        "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem",
        "Sivaganga", "Tenkasi", "Thanjavur", "Theni", "Thiruvallur", "Thiruvarur", "Thoothukkudi", "Tiruchirappalli",
        "Tirunelveli", "Tirupattur", "Tiruppur", "Tiruvannamalai", "Vellore", "Villupuram", "Virudhunagar"}


def test_every_real_place_has_a_forecast_point(real):
    region = load_region()
    lats, lons = region_grid_points(region, np.arange(90.0, -90.25, -0.25), np.arange(-180.0, 180.0, 0.25))
    lat_set, lon_set = set(lats.tolist()), set(lons.tolist())
    outside = [p.name for p in real if not region.contains(p.lat, p.lon)]
    no_point = [p.name for p in real if snap_to_grid(p.lat) not in lat_set or snap_to_grid(p.lon) not in lon_set]
    assert outside == [] and no_point == []


def km(a, b, c, d):
    r = math.pi / 180
    return 6371 * 2 * math.asin(math.sqrt(math.sin((c - a) * r / 2) ** 2 +
                                          math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2))


@pytest.mark.parametrize("q, district, wiki", [
    ("Chennai", "Chennai", (13.0825, 80.275)), ("Coimbatore", "Coimbatore", (11.00083, 76.96333)),
    ("Madurai", "Madurai", (9.9252, 78.1198)),
])
def test_real_search_big_cities_first_and_near_wikipedia(real, q, district, wiki):
    top = PlaceIndex(real).search(q)["results"][0]
    assert (top["name"], top["district"]) == (q, district)
    assert km(top["lat"], top["lon"], *wiki) < 1.0


def test_real_search_nickname_and_did_you_mean(real):
    idx = PlaceIndex(real)
    # GeoNames has its own small "Trichy" entry (1.4 km from the city point); exact name ranks before the city's nickname.
    # Both are in Tiruchirappalli district and snap to the same forecast point.
    top2 = idx.search("trichy")["results"][:2]
    assert [(r["name"], r["district"], r["matched"]) for r in top2] == [
        ("Trichy", "Tiruchirappalli", "Trichy"), ("Tiruchirappalli", "Tiruchirappalli", "Trichy")]
    assert {(snap_to_grid(r["lat"]), snap_to_grid(r["lon"])) for r in top2} == {(10.75, 78.75)}
    sug = idx.search("kidarakulam")
    assert sug["kind"] == "suggestions" and ("Kidarangulam", "Tenkasi") in names(sug)


def test_real_list_source_record():
    src = json.loads(DEFAULT_SOURCE_PATH.read_text(encoding="utf-8"))
    assert src["sha256"] == "fa6d874bafba6600c56065fda4ed0977b95df237d0b6674097983d378327183d"
    assert src["licence"] == "CC BY 4.0" and src["places"] == 39_997
