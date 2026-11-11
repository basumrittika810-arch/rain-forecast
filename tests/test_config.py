"""Tests for the region configuration (config/settings.toml + pipeline/config.py)."""

import pytest

from pipeline.config import ConfigError, Region, load_region

# City coordinates: Wikipedia infobox values (read 2026-11-12), decimal degrees.
CHENNAI = (13.0825, 80.275)
COIMBATORE = (11.00083, 76.96333)
MADURAI = (9.9252, 78.1198)
KOLKATA = (22.5675, 88.37)


# ---------- the real configuration file ----------

def test_real_config_matches_cited_source():
    r = load_region()
    # Expected values computed independently from the source's degrees + minutes.
    assert r.name == "Tamil Nadu"
    assert r.lat_min == pytest.approx(8 + 5 / 60, abs=1e-6)
    assert r.lat_max == pytest.approx(13 + 35 / 60, abs=1e-6)
    assert r.lon_min == pytest.approx(76 + 15 / 60, abs=1e-6)
    assert r.lon_max == pytest.approx(80 + 20 / 60, abs=1e-6)


@pytest.mark.parametrize("city", [CHENNAI, COIMBATORE, MADURAI], ids=["Chennai", "Coimbatore", "Madurai"])
def test_tamil_nadu_cities_inside(city):
    assert load_region().contains(*city)


def test_kolkata_outside():
    assert not load_region().contains(*KOLKATA)


# ---------- box edges ----------

def test_edges_are_inside_and_just_beyond_is_outside():
    r = Region("t", 10.0, 12.0, 77.0, 79.0)
    assert r.contains(10.0, 77.0) and r.contains(12.0, 79.0)
    assert not r.contains(9.999, 78.0) and not r.contains(12.001, 78.0)
    assert not r.contains(11.0, 76.999) and not r.contains(11.0, 79.001)


# ---------- invalid configuration files must be rejected ----------

VALID = 'name = "X"\nlat_min = 8.0\nlat_max = 13.0\nlon_min = 76.0\nlon_max = 80.0\n'


def write(tmp_path, body):
    p = tmp_path / "settings.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_minimal_config_loads(tmp_path):
    assert load_region(write(tmp_path, "[region]\n" + VALID)) == Region("X", 8.0, 13.0, 76.0, 80.0)


@pytest.mark.parametrize("body, message", [
    ("", "[region] section is missing"),
    ("[region]\n" + VALID.replace("lat_max = 13.0\n", ""), "lat_max is missing"),
    ("[region]\n" + VALID.replace("lat_min = 8.0", "lat_min = 14.0"), "must be less than lat_max"),
    ("[region]\n" + VALID.replace("lon_min = 76.0", "lon_min = 81.0"), "must be less than lon_max"),
    ("[region]\n" + VALID.replace("lat_max = 13.0", "lat_max = 95.0"), "outside -90..90"),
    ("[region]\n" + VALID.replace("lon_max = 80.0", "lon_max = 280.0"), "outside -180..180"),
    ("[region]\n" + VALID.replace("lat_min = 8.0", 'lat_min = "8.0"'), "must be a number"),
    ("[region]\n" + VALID.replace("lat_min = 8.0", "lat_min = true"), "must be a number"),
    ("[region]\n" + VALID.replace('name = "X"', 'name = ""'), "non-empty string"),
], ids=["no-section", "missing-key", "lat-swapped", "lon-swapped", "lat-range",
        "lon-0-360", "string-number", "bool-number", "empty-name"])
def test_invalid_configs_rejected(tmp_path, body, message):
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load_region(write(tmp_path, body))
