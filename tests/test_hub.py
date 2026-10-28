"""Tests for the shared request budget and measurement cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from custom_components.mannheim_climate.api import ApiRateLimitError, Measurement
from custom_components.mannheim_climate.const import MEASUREMENT_LIMITS, Field
from custom_components.mannheim_climate.hub import (
    ClimateHub,
    RateLimiter,
    RequestDeferredError,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

MEASUREMENTS = [
    Measurement(datetime(2026, 10, 26, 12, 0, tzinfo=UTC), {Field.TEMPERATURE: 12.3})
]
RATE_LIMIT_WARNING = "rate limit was hit"


# RateLimiter (4 requests per 2 minutes, 30 per hour)


def test_rate_limiter_allows_four_requests_per_two_minutes(
    freezer: FrozenDateTimeFactory,
) -> None:
    """The 5th request has to wait until the oldest one leaves the window."""
    limiter = RateLimiter(MEASUREMENT_LIMITS)
    for _ in range(4):
        assert limiter.wait_time() == 0
        limiter.acquire()
        freezer.tick(10)
    # Requests at 0, 10, 20, 30 s; now 40 s: the first one expires at 120 s.
    assert limiter.wait_time() == pytest.approx(80)
    freezer.tick(80)
    assert limiter.wait_time() == 0


def test_rate_limiter_allows_thirty_requests_per_hour(
    freezer: FrozenDateTimeFactory,
) -> None:
    """Spread-out requests are limited by the hourly window."""
    limiter = RateLimiter(MEASUREMENT_LIMITS)
    for _ in range(30):
        assert limiter.wait_time() == 0, "40 s apart never hits the 2-minute limit"
        limiter.acquire()
        freezer.tick(40)
    # 30 requests from 0 to 1160 s; now 1200 s: the first one expires at 3600 s.
    assert limiter.wait_time() == pytest.approx(2400)
    freezer.tick(2400)
    assert limiter.wait_time() == 0


def test_rate_limiter_blocks_after_rate_limit(freezer: FrozenDateTimeFactory) -> None:
    """After a 429 the limiter waits for Retry-After, even with budget left."""
    limiter = RateLimiter(MEASUREMENT_LIMITS)
    limiter.block_for(60)
    assert limiter.blocked
    assert limiter.wait_time() == pytest.approx(60)
    freezer.tick(60)
    assert not limiter.blocked
    assert limiter.wait_time() == 0


# ClimateHub


@pytest.fixture
def api() -> Generator[MagicMock]:
    """Replace the API client created by the hub."""
    with patch(
        "custom_components.mannheim_climate.hub.MannheimClimateApi", autospec=True
    ) as api_class:
        client = api_class.return_value
        client.async_get_measurements.return_value = MEASUREMENTS
        yield client


@pytest.fixture
async def hub(hass: HomeAssistant, api: MagicMock) -> ClimateHub:  # noqa: ARG001
    """Return a hub using the mocked API (reference data and store are unused)."""
    return ClimateHub(hass, MagicMock(), MagicMock())


async def test_measurements_are_cached_for_nine_minutes(
    hub: ClimateHub, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Locations sharing a station and repeated refreshes reuse the response."""
    assert await hub.async_get_measurements("s1") == MEASUREMENTS
    freezer.tick(timedelta(minutes=8, seconds=59))
    assert await hub.async_get_measurements("s1") == MEASUREMENTS
    assert api.async_get_measurements.await_count == 1
    freezer.tick(timedelta(seconds=1))
    await hub.async_get_measurements("s1")
    assert api.async_get_measurements.await_count == 2


async def test_request_deferred_when_budget_is_used(
    hub: ClimateHub, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """The 5th sensor within 2 minutes is deferred without calling the API."""
    for sensor in ("s1", "s2", "s3", "s4"):
        await hub.async_get_measurements(sensor)
    with pytest.raises(RequestDeferredError) as deferred:
        await hub.async_get_measurements("s5")
    assert deferred.value.wait == pytest.approx(120)
    assert api.async_get_measurements.await_count == 4
    freezer.tick(120)
    assert await hub.async_get_measurements("s5") == MEASUREMENTS


async def test_rate_limit_defers_and_blocks_requests(
    hub: ClimateHub, api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """A 429 defers the request and pauses all requests for Retry-After."""
    api.async_get_measurements.side_effect = ApiRateLimitError(60)
    with pytest.raises(RequestDeferredError) as deferred:
        await hub.async_get_measurements("s1")
    assert deferred.value.wait == 60
    assert hub.diagnostics()["rate_limited"]

    with pytest.raises(RequestDeferredError):
        await hub.async_get_measurements("s2")
    assert api.async_get_measurements.await_count == 1, "blocked: no request sent"

    freezer.tick(60)
    assert not hub.diagnostics()["rate_limited"]


async def test_rate_limit_warning_once_per_streak(
    hub: ClimateHub,
    api: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated 429s warn once; a success in between starts a new streak."""
    api.async_get_measurements.side_effect = [
        ApiRateLimitError(60),
        ApiRateLimitError(60),
        MEASUREMENTS,
        ApiRateLimitError(60),
    ]

    def warnings() -> int:
        return sum(
            record.levelno == logging.WARNING
            and RATE_LIMIT_WARNING in record.getMessage()
            for record in caplog.records
        )

    for sensor in ("s1", "s2"):
        with pytest.raises(RequestDeferredError):
            await hub.async_get_measurements(sensor)
        freezer.tick(60)
    assert warnings() == 1

    await hub.async_get_measurements("s3")
    freezer.tick(60)
    with pytest.raises(RequestDeferredError):
        await hub.async_get_measurements("s4")
    assert warnings() == 2


async def test_concurrent_requests_for_one_sensor_share_the_response(
    hub: ClimateHub, api: MagicMock
) -> None:
    """Two locations refreshing at once cause only one API request."""

    async def slow_response(_sensor_id: str) -> list[Measurement]:
        await asyncio.sleep(0)
        return MEASUREMENTS

    api.async_get_measurements.side_effect = slow_response
    results = await asyncio.gather(
        hub.async_get_measurements("s1"), hub.async_get_measurements("s1")
    )
    assert results == [MEASUREMENTS, MEASUREMENTS]
    assert api.async_get_measurements.await_count == 1
