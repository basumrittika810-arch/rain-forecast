"""Website (Step 4, decision D-028): served at "/", plain HTML + JS + CSS, required texts, no advice, light page,
and the nearest-place endpoint used by "Use my location" (so the page shows a place name, never coordinates).

The JavaScript itself cannot be unit-tested here (no Node.js); its rain text comes from the API, which is tested
(test_messages.py, test_api.py). These tests check what the page is built from.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from pipeline.places import Place, PlaceIndex, load_places, write_places

WEB = Path(__file__).resolve().parent.parent / "web"
FILES = ["index.html", "app.js", "style.css", "tn-outline.svg"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("web")
    return TestClient(create_app(latest_path=tmp / "missing.json"))


def text(name):
    return (WEB / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- served

def test_page_served_at_main_address(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<title>Vaanam: Rain Forecast for Tamil Nadu</title>" in r.text


@pytest.mark.parametrize("path, ctype", [("/app.js", "javascript"), ("/style.css", "text/css"),
                                         ("/tn-outline.svg", "image/svg+xml")])
def test_assets_served(client, path, ctype):
    r = client.get(path)
    assert r.status_code == 200 and ctype in r.headers["content-type"]


def test_api_and_docs_not_hidden_by_the_page(client):
    assert client.get("/api/status").json()["forecast_available"] is False
    assert client.get("/api/places", params={"q": "madurai"}).status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/no-such-page").status_code == 404


# ---------------------------------------------------------------- required texts (owner's design list)

@pytest.mark.parametrize("phrase", [
    "Vaanam",
    "Rain Forecast for Tamil Nadu",
    "Use my location",
    "Waking up the server, this can take up to a minute",
    "No place found. Try a nearby town or check the spelling",
    "Did you mean",
    "No forecast available for this day",
    "Forecast made:",
    "23:30 to 23:30 IST",
    "(18 hours)",
    "Rain at your exact spot may be heavier or lighter",
    "~27 km",
    "ECMWF",
    "GeoNames",
    "CC BY 4.0",
    "India Meteorological Department",
])
def test_required_text_present(phrase):
    assert phrase in text("index.html") + text("app.js")


def test_location_failure_messages_point_to_search():
    js = text("app.js")
    for case in ("denied", "unavailable", "outside Tamil Nadu"):
        assert case in js
    assert js.count("search box") >= 3


def test_stale_warning_after_36_hours():
    assert re.search(r"STALE_HOURS\s*=\s*36\b", text("app.js"))


def test_place_shown_as_name_and_district():
    assert "district" in text("app.js") and ", ${" in text("app.js")


def test_every_category_has_colour_and_word():
    css, js = text("style.css"), text("app.js")
    for key in ("no_rain", "very_light", "light", "moderate", "heavy", "very_heavy", "extremely_heavy", "unavailable"):
        assert f".cat-{key}" in css, key
        assert key in js, key


RAIN_ORDER = ("very_light", "light", "moderate", "heavy", "very_heavy", "extremely_heavy")


def _css_var(name):
    m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})\s*;", text("style.css"))
    assert m, name
    return m.group(1)


def _rgb(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def _luminance(h):   # WCAG 2 relative luminance
    return sum(w * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
               for w, c in zip((0.2126, 0.7152, 0.0722), _rgb(h)))


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_rain_colours_go_from_yellow_to_red_and_darken():
    """Owner (D-029): warm colours, orange to red as rain increases; most rain is red."""
    import colorsys
    cols = [_css_var(f"c-{k.replace('_', '-')}") for k in RAIN_ORDER]
    hues = [colorsys.rgb_to_hls(*_rgb(c))[0] * 360 for c in cols]
    hues = [h - 360 if h > 300 else h for h in hues]          # deep red just below 0 deg
    lums = [_luminance(c) for c in cols]
    assert all(a > b for a, b in zip(hues, hues[1:])), hues   # yellow -> orange -> red
    assert all(a > b for a, b in zip(lums, lums[1:])), lums   # lighter -> darker
    assert 35 <= hues[0] <= 60 and -10 <= hues[-1] <= 10, hues
    r, g, b = _rgb(cols[-1])
    assert r > 2 * g and r > 2 * b                             # the most rain is clearly red


def test_category_word_readable_on_its_colour():
    """The word printed on each colour chip reaches WCAG AA contrast (4.5:1)."""
    css = text("style.css")
    for key in ("no_rain", *RAIN_ORDER):
        rule = re.search(rf"\.cat-{key}\s*\{{([^}}]*)\}}", css).group(1)
        bg = _css_var(re.search(r"background:\s*var\(--([\w-]+)\)", rule).group(1))
        fg = re.search(r"[^-]color:\s*(#[0-9a-fA-F]{6})", rule).group(1)
        assert _contrast(bg, fg) >= 4.5, (key, bg, fg, round(_contrast(bg, fg), 2))


def test_three_hour_blocks_do_not_use_a_category_colour():
    """IMD categories are 24-hour terms (D-028): 3-hour blocks use one neutral colour, not a category's."""
    js = text("app.js")
    block = js[js.index("function drawBlocks"):]
    assert not re.search(r"--c-(very-light|light|moderate|heavy|very-heavy|extremely-heavy)\b", block)


# ---------------------------------------------------------------- rules

def test_no_farming_advice_words():
    all_text = " ".join(text(f) for f in FILES).lower()
    for word in ("sow", "spray", "irrigat", "harvest", "fertili", "pesticide", "you should"):
        assert not re.search(rf"\b{word}", all_text), word


def test_no_frameworks_or_outside_files():
    html = text("index.html")
    assert not re.search(r"""(src|href)\s*=\s*["']https?://""", html)       # nothing loaded from other sites
    assert "@import" not in text("style.css")
    assert not re.search(r"\bimport\s.*\bfrom\b", text("app.js"))


def test_light_page_weight():
    total = sum((WEB / f).stat().st_size for f in FILES)
    assert total < 60_000, total


def test_phone_ready():
    html = text("index.html")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert 'lang="en"' in html
    assert "prefers-reduced-motion" in text("style.css")


# ---------------------------------------------------------------- nearest place (for "Use my location")

IDX = PlaceIndex([
    Place(1, "Melur", "Madurai", 10.03241, 78.3393, 40017, ()),
    Place(2, "Kottampatti", "Madurai", 10.1626, 78.3266, 0, ()),
    Place(3, "Madurai", "Madurai", 9.919, 78.11953, 1465625, ()),
])


def test_nearest_place():
    near = IDX.nearest(10.05, 78.34)
    assert (near["name"], near["district"]) == ("Melur", "Madurai")
    assert 1.5 < near["distance_km"] < 2.5          # 0.0176 deg lat ~ 1.96 km, 0.0007 deg lon ~ 0.08 km


def test_nearest_place_exact_point_is_zero_km():
    assert IDX.nearest(9.919, 78.11953)["distance_km"] == 0.0


def test_nearest_endpoint(tmp_path):
    path = tmp_path / "places.csv"
    write_places(IDX.places, path)
    c = TestClient(create_app(latest_path=tmp_path / "missing.json", places_path=path))
    r = c.get("/api/places/nearest", params={"lat": 10.05, "lon": 78.34})
    assert r.status_code == 200 and r.json()["name"] == "Melur" and "GeoNames" in r.json()["attribution"]
    assert c.get("/api/places/nearest", params={"lat": "abc", "lon": 78}).status_code == 422
    assert c.get("/api/places/nearest", params={"lat": 95, "lon": 78}).status_code == 422


def test_nearest_real_chennai():
    near = PlaceIndex(load_places()).nearest(13.08784, 80.27847)
    assert (near["name"], near["district"], near["distance_km"]) == ("Chennai", "Chennai", 0.0)
