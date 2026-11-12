"""Tests for nearest-grid-point selection (pipeline/grid.py), decisions D-015.

Grid: 0.25 degree spacing. Ties (exactly halfway) go north / east. The stored grid points cover the
region box plus half a grid step (0.125 deg) so every location inside the box has its nearest point stored.
The application box itself is unchanged.
"""

import numpy as np
import pytest

from pipeline.config import load_region
from pipeline.grid import region_grid_points, snap_to_grid

# Same layout as the real GRIB (verified D-014): latitudes 90 -> -90, longitudes -180 -> 179.75.
LATS = np.arange(90.0, -90.25, -0.25)
LONS = np.arange(-180.0, 180.0, 0.25)


@pytest.mark.parametrize("x, expected", [
    (13.0825, 13.0),    # Chennai latitude
    (80.275, 80.25),    # Chennai longitude
    (11.00083, 11.0),   # Coimbatore
    (76.96333, 77.0),
    (9.9252, 10.0),     # Madurai
    (78.1198, 78.0),
    (12.874, 12.75),    # 12.874*4 = 51.496 -> nearest 51 -> 12.75
    (12.876, 13.0),     # 51.504 -> 52 -> 13.0
    (8.09, 8.0),
])
def test_snap_to_nearest(x, expected):
    assert snap_to_grid(x) == expected


@pytest.mark.parametrize("x, expected", [
    (13.125, 13.25),    # exactly halfway between 13.0 and 13.25 -> north
    (13.375, 13.5),
    (80.125, 80.25),    # halfway in longitude -> east
    (-0.125, 0.0),      # southern hemisphere tie still goes north
])
def test_ties_go_north_or_east(x, expected):
    assert snap_to_grid(x) == expected


def test_python_round_would_not_be_consistent():
    # Documents why we do not use round(): it rounds halves to the even neighbour.
    assert round(13.125 * 4) / 4 == 13.0 and round(13.375 * 4) / 4 == 13.5


def test_tamil_nadu_stored_points_391_with_margin():
    lat_sel, lon_sel = region_grid_points(load_region(), LATS, LONS)
    assert (lat_sel.min(), lat_sel.max(), lat_sel.size) == (8.0, 13.5, 23)
    assert (lon_sel.min(), lon_sel.max(), lon_sel.size) == (76.25, 80.25, 17)
    assert lat_sel.size * lon_sel.size == 391


def test_strict_box_would_be_374_and_miss_the_southern_row():
    lat_sel, lon_sel = region_grid_points(load_region(), LATS, LONS, margin=0.0)
    assert lat_sel.size * lon_sel.size == 374
    assert 8.0 not in lat_sel


def test_application_box_is_slightly_extended_tnau_box():
    r = load_region()   # D-024: TNAU box extended slightly; still 391 stored points (tests above)
    assert (r.lat_min, r.lat_max, r.lon_min, r.lon_max) == pytest.approx((8.08, 13 + 35 / 60, 76.24, 80.35))
    assert not r.contains(8.0, 78.0)    # the extra stored row lies outside the box users may query


def test_every_location_in_box_snaps_to_a_stored_point():
    r = load_region()
    lat_sel, lon_sel = region_grid_points(r, LATS, LONS)
    lat_set, lon_set = set(lat_sel.tolist()), set(lon_sel.tolist())
    # every 0.01 deg inside the box, plus the exact edges
    test_lats = np.append(np.arange(np.ceil(r.lat_min * 100) / 100, r.lat_max, 0.01), [r.lat_min, r.lat_max])
    test_lons = np.append(np.arange(np.ceil(r.lon_min * 100) / 100, r.lon_max, 0.01), [r.lon_min, r.lon_max])
    missing_lat = [x for x in test_lats if snap_to_grid(float(x)) not in lat_set]
    missing_lon = [x for x in test_lons if snap_to_grid(float(x)) not in lon_set]
    assert missing_lat == [] and missing_lon == []
