"""Tests for polling, catch-up refreshes and repair issues of a location."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.mannheim_climate.api import (
    ApiConnectionError,
    ApiRateLimitError,
    SensorNotFoundError,
)
from custom_components.mannheim_climate.const import (
    CATCH_UP_MARGIN_S,
    CONF_SCAN_INTERVAL,
    CONF_TEMPERATURE_SENSORS,
    CONF_WIND_SENSOR,
    DOMAIN,
    Field,
)
from custom_components.mannheim_climate.coordinator import issue_id

from .common import (
    CATALOG_SENSOR,
    MEASUREMENT_AGE,
    NEAREST_SENSOR,
    NEAREST_WIND_SENSOR,
    SECOND_SENSOR,
    add_home_entry,
    respond,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import issue_registry as ir

    from custom_components.mannheim_climate.coordinator import ClimateCoordinator

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

THIRD_SENSOR = "0004A30B010A4684"  # 2306LH075, 878 m
VALUES = {
    NEAREST_SENSOR: {Field.TEMPERATURE: 12.0},
    SECOND_SENSOR: {Field.TEMPERATURE: 13.0},
    THIRD_SENSOR: {Field.TEMPERATURE: 14.0},
    CATALOG_SENSOR: {Field.TEMPERATURE: 15.0},
    NEAREST_WIND_SENSOR: {Field.WIND_SPEED: 3.0},
}
CACHE_EXPIRED = timedelta(minutes=10)


async def set_up(
    hass: HomeAssistant, api: MagicMock, sensors: list[str], interval: int = 15
) -> ClimateCoordinator:
    """Set up a location with these temperature sensors and the wind sensor."""
    api.async_get_measurements.side_effect = respond(VALUES)
    entry = add_home_entry(
        hass,
        **{
            CONF_TEMPERATURE_SENSORS: sensors,
            CONF_WIND_SENSOR: NEAREST_WIND_SENSOR,
            CONF_SCAN_INTERVAL: interval,
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry.runtime_data


async def refresh_after(
    hass: HomeAssistant,
    coordinator: ClimateCoordinator,
    freezer: FrozenDateTimeFactory,
    delay: timedelta,
) -> None:
    """Let time pass and refresh (the measurement cache expires after 9 min)."""
    freezer.tick(delay)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_values_of_all_stations_are_combined(
    hass: HomeAssistant, api: MagicMock
) -> None:
    """Median of the stations, wind from the wind sensor."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR, SECOND_SENSOR])
    assert coordinator.data.temperature == 12.5
    assert coordinator.data.wind_speed == 3.0
    assert api.async_get_measurements.await_count == 3


async def test_deferred_sensors_are_fetched_later(
    hass: HomeAssistant, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """4 requests per 2 min: the 5th sensor is fetched once the budget allows."""
    coordinator = await set_up(
        hass, api, [NEAREST_SENSOR, SECOND_SENSOR, THIRD_SENSOR, CATALOG_SENSOR]
    )
    assert coordinator.data.temperature == 13.5
    assert coordinator.data.wind_speed is None, "wind deferred"
    assert api.async_get_measurements.await_count == 4

    freezer.tick(timedelta(seconds=120 + CATCH_UP_MARGIN_S))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api.async_get_measurements.await_count == 5, "only the deferred sensor"
    assert coordinator.data.wind_speed == 3.0


async def test_waiting_for_budget_without_any_values(
    hass: HomeAssistant, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Rate limited, last values too old: fail with retry hint, catch up later."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR])
    api.async_get_measurements.side_effect = ApiRateLimitError(60)
    await refresh_after(hass, coordinator, freezer, timedelta(hours=1))
    assert not coordinator.last_update_success
    error = coordinator.last_exception
    assert error.translation_key == "waiting_for_budget"
    assert error.retry_after == 60 + CATCH_UP_MARGIN_S

    api.async_get_measurements.side_effect = respond(VALUES)
    freezer.tick(timedelta(seconds=60 + CATCH_UP_MARGIN_S))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.last_update_success


async def test_last_values_kept_while_waiting_for_budget(
    hass: HomeAssistant, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Rate limited with outdated cache: keep the last values, catch up later."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR])
    api.async_get_measurements.side_effect = ApiRateLimitError(60)
    await refresh_after(hass, coordinator, freezer, timedelta(minutes=35))
    assert coordinator.last_update_success
    assert coordinator.data.temperature == 12.0

    api.async_get_measurements.side_effect = respond(
        {**VALUES, NEAREST_SENSOR: {Field.TEMPERATURE: 11.0}}
    )
    freezer.tick(timedelta(seconds=60 + CATCH_UP_MARGIN_S))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.data.temperature == 11.0


async def test_cached_values_used_while_rate_limited(
    hass: HomeAssistant, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Values younger than 40 minutes are still good enough during a 429."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR])
    api.async_get_measurements.side_effect = ApiRateLimitError(60)
    await refresh_after(hass, coordinator, freezer, CACHE_EXPIRED)
    assert coordinator.last_update_success
    assert coordinator.data.temperature == 12.0


@pytest.mark.parametrize(
    ("interval", "kept_for"),
    [(15, timedelta(minutes=60)), (30, timedelta(minutes=90))],
)
async def test_last_values_kept_without_recent_data(
    hass: HomeAssistant,
    api: MagicMock,
    freezer: FrozenDateTimeFactory,
    interval: int,
    kept_for: timedelta,
) -> None:
    """Values stay until they are max(60 min, 3 intervals) old, then unavailable."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR], interval)
    last_measurement = coordinator.data.last_measurement
    api.async_get_measurements.side_effect = ApiConnectionError("timeout")

    await refresh_after(hass, coordinator, freezer, kept_for - MEASUREMENT_AGE)
    assert coordinator.last_update_success
    assert coordinator.data.temperature == 12.0
    assert coordinator.data.wind_speed == 3.0
    assert coordinator.data.last_measurement == last_measurement

    await refresh_after(hass, coordinator, freezer, timedelta(seconds=1))
    assert not coordinator.last_update_success
    assert coordinator.last_exception.translation_key == "no_recent_data"


async def test_removed_station_creates_repair_issue(
    hass: HomeAssistant,
    api: MagicMock,
    freezer: FrozenDateTimeFactory,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A 404 raises a repair issue; the other station is still used."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR, SECOND_SENSOR])
    issue = issue_id(
        coordinator.config_entry.entry_id, "station_removed", SECOND_SENSOR
    )

    api.async_get_measurements.side_effect = respond(
        {**VALUES, SECOND_SENSOR: SensorNotFoundError("gone")}
    )
    await refresh_after(hass, coordinator, freezer, CACHE_EXPIRED)
    assert coordinator.data.temperature == 12.0
    assert issue_registry.async_get_issue(DOMAIN, issue) is not None

    api.async_get_measurements.side_effect = respond(VALUES)
    await refresh_after(hass, coordinator, freezer, CACHE_EXPIRED)
    assert issue_registry.async_get_issue(DOMAIN, issue) is None


async def test_offline_station_creates_repair_issue_after_a_day(
    hass: HomeAssistant,
    api: MagicMock,
    freezer: FrozenDateTimeFactory,
    issue_registry: ir.IssueRegistry,
) -> None:
    """No valid values for 24 hours raise a repair issue until data is back."""
    coordinator = await set_up(hass, api, [NEAREST_SENSOR, SECOND_SENSOR])
    issue = issue_id(
        coordinator.config_entry.entry_id, "station_offline", SECOND_SENSOR
    )
    silent = respond({**VALUES, SECOND_SENSOR: {}})

    api.async_get_measurements.side_effect = silent
    await refresh_after(hass, coordinator, freezer, timedelta(hours=23, minutes=50))
    assert issue_registry.async_get_issue(DOMAIN, issue) is None
    await refresh_after(
        hass, coordinator, freezer, CACHE_EXPIRED + timedelta(seconds=1)
    )
    assert issue_registry.async_get_issue(DOMAIN, issue) is not None

    api.async_get_measurements.side_effect = respond(VALUES)
    await refresh_after(hass, coordinator, freezer, CACHE_EXPIRED)
    assert issue_registry.async_get_issue(DOMAIN, issue) is None


async def test_unload_cancels_catch_up(
    hass: HomeAssistant, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """No requests for a location that was removed in the meantime."""
    coordinator = await set_up(
        hass, api, [NEAREST_SENSOR, SECOND_SENSOR, THIRD_SENSOR, CATALOG_SENSOR]
    )
    assert await hass.config_entries.async_unload(coordinator.config_entry.entry_id)
    freezer.tick(timedelta(seconds=120 + CATCH_UP_MARGIN_S))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert api.async_get_measurements.await_count == 4
