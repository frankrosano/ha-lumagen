"""Coordinator that watches lumagen.com for new Radiance Pro firmware.

Separate from :class:`~.coordinator.LumagenCoordinator` because it has
nothing to do with the device: it fetches the vendor's release page once a
day and hands it to :func:`aiolumagen.firmware.parse_release_index`. The HTTP
lives here (the library never does I/O); the parsing lives in the library
(this integration never parses Lumagen-shaped text).

It only polls while something listens, and nothing refreshes it at entry
setup — the update entity triggers the first fetch when it's added. So the
website can never block or fail setup, and disabling the update entity stops
all traffic to lumagen.com.

A failed check raises :class:`UpdateFailed`, which leaves ``data`` at its last
good value; the update entity keeps offering what it last knew rather than
going unavailable.
"""

from __future__ import annotations

import logging

import aiohttp
from aiolumagen.firmware import (
    RELEASES_URL,
    LumagenReleaseIndexError,
    ReleaseChannel,
    ReleaseListing,
    latest_release,
    parse_release_index,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_CHANNEL,
    DOMAIN,
    FIRMWARE_USER_AGENT,
    MAX_RELEASE_INDEX_BYTES,
    RELEASE_CHECK_INTERVAL,
    RELEASE_FETCH_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_READ_CHUNK = 64 * 1024


async def async_read_capped(resp: aiohttp.ClientResponse, cap: int) -> bytes:
    """Read a response body, stopping one chunk past ``cap``.

    ``StreamReader.read(n)`` returns as soon as *any* data is buffered, so a
    single call can hand back a fraction of the body. This reads to EOF, but
    stops early once the body is known to exceed ``cap`` — the caller treats
    ``len(result) > cap`` as the error, without buffering a runaway response.
    """
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.content.iter_chunked(_READ_CHUNK):
        chunks.append(chunk)
        size += len(chunk)
        if size > cap:
            break
    return b"".join(chunks)


def channel_for(entry: ConfigEntry) -> ReleaseChannel:
    """The entry's configured release channel, defaulting to beta."""
    try:
        return ReleaseChannel(entry.options.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL))
    except ValueError:
        return ReleaseChannel(DEFAULT_FIRMWARE_CHANNEL)


class LumagenReleaseCoordinator(DataUpdateCoordinator[tuple[ReleaseListing, ...]]):
    """Fetches and parses the vendor's release index."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_releases",
            config_entry=entry,
            update_interval=RELEASE_CHECK_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> tuple[ReleaseListing, ...]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                RELEASES_URL,
                headers={"User-Agent": FIRMWARE_USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=RELEASE_FETCH_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                body = await async_read_capped(resp, MAX_RELEASE_INDEX_BYTES)
                charset = resp.charset or "utf-8"
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not fetch the Lumagen release page: {err}") from err
        if len(body) > MAX_RELEASE_INDEX_BYTES:
            raise UpdateFailed(
                f"Lumagen release page exceeds {MAX_RELEASE_INDEX_BYTES} bytes; not parsing it"
            )
        try:
            text = body.decode(charset, errors="replace")
        except (UnicodeError, LookupError) as err:
            raise UpdateFailed(f"Could not decode the Lumagen release page: {err}") from err
        try:
            return await self.hass.async_add_executor_job(parse_release_index, text, RELEASES_URL)
        except LumagenReleaseIndexError as err:
            # Fail closed: the page changed shape, so offer nothing new.
            raise UpdateFailed(f"Lumagen release page not understood: {err}") from err

    @property
    def has_data(self) -> bool:
        """Whether any check has ever succeeded.

        ``data`` is typed non-optional by HA but starts as None; spelling the
        test out here keeps that one wart in one place.
        """
        data: tuple[ReleaseListing, ...] | None = self.data
        return data is not None

    def latest_for(self, channel: ReleaseChannel) -> ReleaseListing | None:
        """Newest known listing on ``channel``, or None if none is known."""
        return latest_release(self.data or (), channel)
