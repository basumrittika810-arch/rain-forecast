"""Load and validate the central configuration (config/settings.toml).

Only the region is configured so far. Invalid values raise ConfigError immediately,
rather than letting bad coordinates reach the processing code.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.toml"


class ConfigError(ValueError):
    """Raised when the configuration file is missing values or contains invalid ones."""


@dataclass(frozen=True)
class Region:
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float

    def contains(self, lat: float, lon: float) -> bool:
        """True if (lat, lon) lies inside the box, edges included."""
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


def _number(section: dict, key: str) -> float:
    if key not in section:
        raise ConfigError(f"region.{key} is missing")
    value = section[key]
    # bool is a subclass of int in Python; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"region.{key} must be a number, got {value!r}")
    return float(value)


def load_region(path: Path = DEFAULT_CONFIG_PATH) -> Region:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if "region" not in data:
        raise ConfigError("[region] section is missing")
    sec = data["region"]
    name = sec.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("region.name must be a non-empty string")

    lat_min, lat_max = _number(sec, "lat_min"), _number(sec, "lat_max")
    lon_min, lon_max = _number(sec, "lon_min"), _number(sec, "lon_max")

    for key, v in (("lat_min", lat_min), ("lat_max", lat_max)):
        if not -90 <= v <= 90:
            raise ConfigError(f"region.{key}={v} is outside -90..90")
    for key, v in (("lon_min", lon_min), ("lon_max", lon_max)):
        if not -180 <= v <= 180:
            raise ConfigError(f"region.{key}={v} is outside -180..180 (data uses -180..180)")
    if lat_min >= lat_max:
        raise ConfigError(f"region.lat_min ({lat_min}) must be less than lat_max ({lat_max})")
    if lon_min >= lon_max:
        raise ConfigError(f"region.lon_min ({lon_min}) must be less than lon_max ({lon_max}); "
                          "boxes crossing the 180° meridian are not supported")
    return Region(name.strip(), lat_min, lat_max, lon_min, lon_max)
