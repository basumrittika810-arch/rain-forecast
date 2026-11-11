"""Grid-point selection for the 0.25 degree forecast grid (decisions D-015).

* Nearest grid point; exact ties go north (latitude) / east (longitude): floor(x / spacing + 0.5) * spacing.
  Python's round() is NOT used: it rounds halves to the even neighbour, so ties would go either way.
* Stored grid points = those within the region box expanded by half a grid step, so every location
  inside the (unchanged) application box has its nearest grid point stored.
"""

import math

import numpy as np

from pipeline.config import Region

GRID_SPACING_DEG = 0.25  # verified: all GRIB coordinates are exact multiples of 0.25 (D-014)


def snap_to_grid(x: float, spacing: float = GRID_SPACING_DEG) -> float:
    """Nearest grid coordinate; exactly-halfway values go to the larger coordinate (north / east)."""
    return math.floor(x / spacing + 0.5) * spacing


def region_grid_points(region: Region, lats: np.ndarray, lons: np.ndarray,
                       spacing: float = GRID_SPACING_DEG, margin: float | None = None):
    """Grid latitudes and longitudes to store for the region (sorted ascending).

    margin defaults to half a grid step. margin=0.0 gives the strict box (for comparison only).
    """
    m = spacing / 2 if margin is None else margin
    lat_sel = lats[(lats >= region.lat_min - m) & (lats <= region.lat_max + m)]
    lon_sel = lons[(lons >= region.lon_min - m) & (lons <= region.lon_max + m)]
    if lat_sel.size == 0 or lon_sel.size == 0:
        raise ValueError(f"no grid points found for region {region.name}")
    return np.sort(lat_sel), np.sort(lon_sel)
