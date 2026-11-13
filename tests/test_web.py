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
FILES = ["index.html", "app.js", "style.css", "icon.svg", "scene-rain.svg", "scene-fields.svg"]


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
                                         ("/icon.svg", "image/svg+xml"), ("/scene-rain.svg", "image/svg+xml"),
                                         ("/scene-fields.svg", "image/svg+xml")])
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


def test_colour_note_points_to_imd_warnings():
    """Owner (D-030): say colours are amounts, not warnings, and point to IMD.
    Moved by the owner (D-031): next to the colour key, in small text, so the search box is the first thing seen."""
    html = text("index.html")
    assert ("Colours show forecast rain amounts, not official warnings. "
            "For official weather warnings, see IMD") in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
    assert 'href="https://mausam.imd.gov.in/"' in html
    assert html.index('id="legend"') < html.index("colour-note") < html.index('class="fc-days"')
    size = re.search(r"\.colour-note\s*\{[^}]*font-size:\s*([\d.]+)rem", text("style.css")).group(1)
    assert float(size) <= 0.9


# ---------------------------------------------------------------- D-031: header, font, search, footer, background

def _rule(selector):
    m = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", text("style.css"))
    assert m, selector
    return m.group(1)


def test_tagline_under_title():
    html = text("index.html")
    header = html[html.index('<header class="top">'):html.index("</header>")]
    assert "Your village's rain, day by day" in header
    assert "Rain forecast for Tamil Nadu" in header


def test_day_hint_does_not_promise_3_hour_blocks():
    """Days 7-11 have 6-hour blocks, so the general hint must not say '3-hour'."""
    html = text("index.html")
    assert "Tap a day to see when the rain is expected." in html
    assert "3-hour" not in html


def test_header_band_gradient_with_white_text():
    top = _rule(".top")
    assert "linear-gradient" in top and re.search(r"color:\s*#fff(fff)?\b", top)
    # the map can never sit behind the title: the band's background is opaque (no rgba/transparent colours in it)
    background = re.search(r"background:\s*([^;]*);", top).group(1)
    assert "rgba" not in background and "transparent" not in background


def _font_faces():
    out = {}
    for face in re.findall(r"@font-face\s*\{([^}]*)\}", text("style.css")):
        fam = re.search(r"font-family:\s*\"([^\"]+)\"", face).group(1)
        out[fam] = (face, re.search(r"url\(\"?([^\")]+)\"?\)", face).group(1))
    return out


def test_fonts_stored_with_site_and_licensed():
    faces = _font_faces()
    assert set(faces) == {"Baloo 2", "Arima"}, faces
    for fam, (face, url) in faces.items():
        assert not url.startswith(("http:", "https:", "//")), url       # stored with the site, nothing from outside
        font = WEB / url
        assert font.read_bytes()[:4] == b"wOF2" and font.stat().st_size < 30_000
        licence = font.parent / f"OFL-{fam.replace(' ', '')}.txt"
        assert "SIL Open Font License" in licence.read_text(encoding="utf-8"), licence
        assert "swap" in face                                            # text shows at once in the phone's own font


def test_headings_baloo_title_arima():
    """D-031: headings in Baloo 2. D-032 (owner): only the title "Vaanam" changes, to Arima."""
    assert '"Baloo 2"' in _rule("h1, h2, h3")
    assert re.search(r'font-family:\s*"Arima"', _rule(".top h1"))
    # the title font holds only the letters of "Vaanam" (V, a, n, m), so it stays tiny
    assert (WEB / _font_faces()["Arima"][1]).stat().st_size < 5_000
    assert "unicode-range" in _font_faces()["Arima"][0]
    h1 = re.search(r"<h1>(.*?)</h1>", text("index.html")).group(1)
    assert re.sub(r"<[^>]+>", "", h1) == "Vaanam"


def test_title_larger():
    size = re.search(r"font-size:\s*([\d.]+)rem", _rule(".top h1")).group(1)
    assert float(size) >= 2.8


def test_search_box_bigger_with_icon():
    rule = _rule("input[type=search]")
    assert "data:image/svg+xml" in rule                                  # icon drawn inside the box, no extra file
    assert int(re.search(r"min-height:\s*(\d+)px", rule).group(1)) >= 56
    assert int(re.search(r"padding-left:\s*(\d+)px", rule).group(1)) >= 40   # text starts after the icon


def test_softer_cards():
    card = _rule(".card")
    assert int(re.search(r"border-radius:\s*(\d+)px", card).group(1)) >= 16
    assert "box-shadow" in card
    alpha = float(re.search(r"--card:\s*rgba\(255,\s*255,\s*255,\s*([\d.]+)\)", text("style.css")).group(1))
    assert alpha >= 0.95                                                 # readings stay clear over the map


def test_darker_page_background():
    body = _rule("body")
    cols = re.findall(r"#[0-9a-fA-F]{6}", body.split("background:")[1].split(";")[0])
    assert cols and all(_luminance(c) <= 0.55 for c in cols), cols      # old top colour #d9effb was 0.83
    assert all(_contrast(c, "#ffffff") >= 1.5 for c in cols)             # white cards clearly stand out


def test_footer_band_with_credits_and_small_maker_line():
    html, foot = text("index.html"), _rule(".foot")
    footer = html[html.index("<footer"):html.index("</footer>")]
    for credit in ("ECMWF", "GeoNames", "India Meteorological Department"):
        assert credit in footer
    assert "Made by Mrittika" in footer
    assert "background" in foot                                          # its own band: the map is never behind it
    size = re.search(r"font-size:\s*([\d.]+)rem", _rule(".made-by")).group(1)
    assert float(size) <= 0.75


def test_blue_is_darker():
    """Owner (D-030): darker blue. White button text on it reaches at least 6:1 (was 5.1:1 with #1f6fc0)."""
    assert _contrast(_css_var("blue"), "#ffffff") >= 6.0
    assert _contrast(_css_var("blue-dark"), "#ffffff") >= 9.0


def test_wide_screens_use_two_columns():
    """Owner (D-030): on a computer the forecast spreads out; phones keep one column."""
    css, html = text("style.css"), text("index.html")
    m = re.search(r"@media \(min-width:\s*(\d+)px\)\s*\{(.*?)\n\}", css, re.S)
    assert m and int(m.group(1)) >= 768, "a wide-screen rule is needed"
    assert "grid-template-columns" in m.group(2) and ".fc-body" in m.group(2)
    assert 'class="fc-body"' in html and 'class="fc-overview"' in html and 'class="fc-days"' in html


def test_background_is_rain_falling_on_fields():
    """D-032 (owner chose option F): the Tamil Nadu map is replaced by rain falling on green fields. The scene sits in
    the page between the content and the footer, so it is never behind any text; the footer continues the fields."""
    html, css = text("index.html"), text("style.css")
    assert html.index("</main>") < html.index('class="scene"') < html.index("<footer")
    scene = _rule(".scene")
    assert "scene-rain.svg" in css and "scene-fields.svg" in css and "flex" in scene
    rain, fields = text("scene-rain.svg"), text("scene-fields.svg")
    assert "<line" in rain or "<path" in rain
    front = re.search(r'id="front"[^>]*fill="(#[0-9a-fA-F]{6})"', fields).group(1)
    assert front.lower() in _rule(".foot").lower()                      # the footer is the same green as the front field
    assert "@keyframes fall" in css and "prefers-reduced-motion" in css  # rain moves gently, never for reduced motion
    for gone in ("tn-outline", "watermark", "Natural Earth"):
        assert gone not in html + css, gone
    assert not (WEB / "tn-outline.svg").exists()


def test_footer_text_readable_on_green():
    foot = _rule(".foot")
    bg = re.search(r"background:\s*(#[0-9a-fA-F]{6})", foot).group(1)
    fg = re.search(r"[^-]color:\s*(#[0-9a-fA-F]{6})", foot).group(1)
    assert _contrast(bg, fg) >= 7.0, round(_contrast(bg, fg), 2)


def test_favicon_is_raindrop():
    assert '<link rel="icon" href="icon.svg" type="image/svg+xml">' in text("index.html")
    assert "<path" in text("icon.svg")

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
    assert not re.search(r"""src\s*=\s*["']https?://""", html)              # nothing loaded from other sites
    assert not re.search(r"""<link[^>]*href\s*=\s*["']https?://""", html)
    # plain links the reader may tap are allowed only to the IMD site (D-030); they load nothing by themselves
    assert set(re.findall(r"""<a[^>]*href\s*=\s*["'](https?://[^"']+)""", html)) <= {"https://mausam.imd.gov.in/"}
    assert "@import" not in text("style.css")
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", text("style.css"))   # fonts and images from this site only
    assert not re.search(r"\bimport\s.*\bfrom\b", text("app.js"))


def test_light_page_weight():
    total = sum((WEB / f).stat().st_size for f in FILES)
    assert total < 60_000, total
    # D-031: with the heading font, the whole page a phone downloads stays under 90 KB
    fonts = sum(p.stat().st_size for p in (WEB / "fonts").glob("*.woff2"))
    assert total + fonts < 90_000, total + fonts


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
