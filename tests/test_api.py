"""Tests for the API client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.mannheim_climate.api import (
    ApiRateLimitError,
    MannheimClimateApi,
)
from custom_components.mannheim_climate.const import (
    API_BASE_URL,
    DEFAULT_RETRY_AFTER_S,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "60"}, 60.0),
        ({"Retry-After": "0"}, 1.0),
        ({}, DEFAULT_RETRY_AFTER_S),
        ({"Retry-After": "soon"}, DEFAULT_RETRY_AFTER_S),
    ],
    ids=["seconds", "at_least_one_second", "missing", "unreadable"],
)
async def test_rate_limit_retry_after(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    headers: dict[str, str],
    expected: float,
) -> None:
    """A 429 reports how long to wait, with a default for missing/odd headers."""
    aioclient_mock.get(f"{API_BASE_URL}/measurements/s1", status=429, headers=headers)
    api = MannheimClimateApi(async_get_clientsession(hass))
    with pytest.raises(ApiRateLimitError) as rate_limited:
        await api.async_get_measurements("s1")
    assert rate_limited.value.retry_after == expected
