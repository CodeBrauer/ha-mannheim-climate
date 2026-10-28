"""Builders shared by the tests."""

from __future__ import annotations

import math

from custom_components.mannheim_climate.api import ApiSensor
from custom_components.mannheim_climate.const import Field, MountZone
from custom_components.mannheim_climate.stations import LczSource, Station

HOME = (49.472, 8.565)
METRES_PER_DEGREE_LATITUDE = 111_320
LCZ_OPEN_BUILT = 6

TEMPERATURE_PARAMETERS = frozenset({Field.TEMPERATURE, Field.HUMIDITY})
WIND_PARAMETERS = frozenset({Field.WIND_SPEED, Field.WIND_GUST, Field.WIND_DIRECTION})


def offset(distance_m: float, bearing_deg: float) -> tuple[float, float]:
    """Return the coordinate distance_m away from HOME (good enough for a few km)."""
    latitude, longitude = HOME
    bearing = math.radians(bearing_deg)
    metres_per_degree_longitude = METRES_PER_DEGREE_LATITUDE * math.cos(
        math.radians(latitude)
    )
    return (
        latitude + distance_m * math.cos(bearing) / METRES_PER_DEGREE_LATITUDE,
        longitude + distance_m * math.sin(bearing) / metres_per_degree_longitude,
    )


def make_station(  # noqa: PLR0913
    code: str,
    distance_m: float,
    *,
    bearing_deg: float = 0.0,
    lcz: int | None = LCZ_OPEN_BUILT,
    zone: MountZone | None = MountZone.STREET,
    height_above_ground: int | None = 0,
    temperature: bool = True,
    wind: bool = False,
) -> Station:
    """
    Return a station distance_m away from HOME.

    Sensor ids are "<code>-t" (temperature) and "<code>-w" (wind).
    """
    latitude, longitude = offset(distance_m, bearing_deg)

    def sensor(suffix: str, parameters: frozenset[str]) -> ApiSensor:
        return ApiSensor(
            id=f"{code}-{suffix}",
            name=code,
            latitude=latitude,
            longitude=longitude,
            parameters=parameters,
        )

    return Station(
        code=code,
        latitude=latitude,
        longitude=longitude,
        temperature_sensor=sensor("t", TEMPERATURE_PARAMETERS) if temperature else None,
        wind_sensor=sensor("w", WIND_PARAMETERS) if wind else None,
        district=None,
        lcz=lcz,
        lcz_source=LczSource.CATALOG if lcz else None,
        zone=zone,
        height_above_ground=height_above_ground,
        temperature_height=None,
    )
