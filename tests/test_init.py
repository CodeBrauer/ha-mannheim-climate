"""Tests for setting up, unloading and removing a location."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.mannheim_climate.api import ApiConnectionError
from custom_components.mannheim_climate.const import (
    CONF_TEMPERATURE_SENSORS,
    CONF_WIND_SENSOR,
    DOMAIN,
    Field,
)
from custom_components.mannheim_climate.coordinator import issue_id

from .common import (
    NEAREST_SENSOR,
    NEAREST_WIND_SENSOR,
    SECOND_SENSOR,
    add_home_entry,
    respond,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

VALUES = {
    NEAREST_SENSOR: {Field.TEMPERATURE: 12.0},
    SECOND_SENSOR: {Field.TEMPERATURE: 13.0},
    NEAREST_WIND_SENSOR: {Field.WIND_SPEED: 3.0},
}


@pytest.fixture
def entry(hass: HomeAssistant, api: MagicMock) -> MockConfigEntry:
    """Return a location using two stations and a wind sensor."""
    api.async_get_measurements.side_effect = respond(VALUES)
    return add_home_entry(
        hass,
        **{
            CONF_TEMPERATURE_SENSORS: [NEAREST_SENSOR, SECOND_SENSOR],
            CONF_WIND_SENSOR: NEAREST_WIND_SENSOR,
        },
    )


async def test_setup_and_unload(
    hass: HomeAssistant, entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Setup fetches all sensors and creates the entities with values."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED

    temperature = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_temperature"
    )
    assert hass.states.get(temperature).state == "12.5"
    assert hass.states.get("weather.seckenheim") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retried_without_station_list(
    hass: HomeAssistant, entry: MockConfigEntry, api: MagicMock
) -> None:
    """No station list (and no stored copy): try again later."""
    api.async_get_sensors_payload.side_effect = ApiConnectionError("timeout")
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_when_no_selected_station_exists(
    hass: HomeAssistant, api: MagicMock
) -> None:
    """Stations removed from the API need a new selection, retrying won't help."""
    entry = add_home_entry(hass, **{CONF_TEMPERATURE_SENSORS: ["removed"]})
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    api.async_get_measurements.assert_not_awaited()


async def test_setup_retried_without_recent_data(
    hass: HomeAssistant, entry: MockConfigEntry, api: MagicMock
) -> None:
    """The first refresh must deliver values."""
    api.async_get_measurements.side_effect = ApiConnectionError("timeout")
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_remove_deletes_repair_issues(
    hass: HomeAssistant, entry: MockConfigEntry, issue_registry: ir.IssueRegistry
) -> None:
    """Repair issues of a removed location go away; others stay."""
    own = issue_id(entry.entry_id, "station_offline", NEAREST_SENSOR)
    other = issue_id("other_entry", "station_offline", NEAREST_SENSOR)
    for issue in (own, other):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="station_offline",
        )
    await hass.config_entries.async_remove(entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, own) is None
    assert issue_registry.async_get_issue(DOMAIN, other) is not None
