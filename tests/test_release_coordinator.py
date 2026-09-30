"""Tests for the lumagen.com release-index coordinator."""

from __future__ import annotations

import pytest
from aiolumagen.firmware import RELEASES_URL, ReleaseChannel
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.lumagen import release_coordinator as rc
from custom_components.lumagen.const import CONF_URL, DOMAIN, FIRMWARE_USER_AGENT

from .firmware_helpers import DEFAULT_PAGE


def _coordinator(hass: HomeAssistant) -> rc.LumagenReleaseCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_URL: "socket://x:1"}, unique_id="rel")
    entry.add_to_hass(hass)
    return rc.LumagenReleaseCoordinator(hass, entry)


async def test_success_parses_and_sends_user_agent(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    coordinator = _coordinator(hass)
    listings = await coordinator._async_update_data()

    assert [lst.revision.mmddyy for lst in listings] == ["030225", "030326"]
    _method, url, _data, headers = aioclient_mock.mock_calls[-1]
    assert str(url) == RELEASES_URL
    assert headers["User-Agent"] == FIRMWARE_USER_AGENT


async def test_latest_for_channel(hass: HomeAssistant) -> None:
    coordinator = _coordinator(hass)
    assert coordinator.latest_for(ReleaseChannel.BETA) is None
    assert not coordinator.has_data
    await coordinator.async_refresh()
    assert coordinator.has_data
    beta = coordinator.latest_for(ReleaseChannel.BETA)
    production = coordinator.latest_for(ReleaseChannel.PRODUCTION)
    assert beta is not None and beta.revision.mmddyy == "030326"
    assert production is not None and production.revision.mmddyy == "030225"


async def test_http_error_raises_update_failed_and_keeps_data(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    coordinator = _coordinator(hass)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    before = coordinator.data

    aioclient_mock.clear_requests()
    aioclient_mock.get(RELEASES_URL, status=500)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    # A failed check keeps the last known listings.
    assert coordinator.data == before
    assert coordinator.latest_for(ReleaseChannel.BETA) is not None


async def test_unrecognised_page_fails_closed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(RELEASES_URL, text="<html><body><p>Site redesigned.</p></body></html>")
    coordinator = _coordinator(hass)
    with pytest.raises(UpdateFailed, match="not understood"):
        await coordinator._async_update_data()


async def test_oversize_page_rejected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rc, "MAX_RELEASE_INDEX_BYTES", 64)
    assert len(DEFAULT_PAGE) > 64
    coordinator = _coordinator(hass)
    with pytest.raises(UpdateFailed, match="exceeds"):
        await coordinator._async_update_data()


async def test_timeout_raises_update_failed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(RELEASES_URL, exc=TimeoutError())
    coordinator = _coordinator(hass)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


def test_channel_for_defaults_and_tolerates_junk() -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    assert rc.channel_for(entry) is ReleaseChannel.BETA
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"firmware_channel": "production"})
    assert rc.channel_for(entry) is ReleaseChannel.PRODUCTION
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"firmware_channel": "nightly"})
    assert rc.channel_for(entry) is ReleaseChannel.BETA
