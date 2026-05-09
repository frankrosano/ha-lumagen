"""DataUpdateCoordinator wrapping pylumagen's LumagenClient.

pylumagen owns its own poll loop and pushes state via a subscribe callback.
This coordinator is push-first — ``update_interval`` is ``None`` — so the
only job of :meth:`_async_update_data` is to seed the initial state during
``async_config_entry_first_refresh``. Everything after that lands via
:meth:`_on_state_update`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pylumagen import (
    LumagenClient,
    LumagenConnectionError,
    LumagenError,
    LumagenState,
    LumagenTransport,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

type LumagenConfigEntry = ConfigEntry[LumagenCoordinator]


class LumagenCoordinator(DataUpdateCoordinator[LumagenState]):
    """Owns the LumagenClient and forwards state pushes into HA."""

    config_entry: LumagenConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: LumagenConfigEntry,
        client: LumagenClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            always_update=False,
        )
        self.client = client
        self._unsubscribe: Callable[[], None] | None = None

    async def _async_setup(self) -> None:
        """Start the pylumagen client; called once by the coordinator.

        Errors here become ``ConfigEntryNotReady`` automatically — HA will
        retry setup on an exponential backoff. The subscription is wired
        before ``start()`` so the startup handshake's own responses feed
        straight into HA state. We raise without ``from err`` so HA logs
        a clean retry notice rather than the full stack trace — reconnect
        loops are expected, not bugs.
        """
        self._unsubscribe = self.client.subscribe(self._on_state_update)
        try:
            await self.client.start()
        except LumagenConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from None
        except LumagenError as err:
            # Anything else from the library is unexpected at setup; surface
            # it with full context so it's debuggable.
            raise ConfigEntryNotReady(f"Unexpected Lumagen error: {err}") from err

    async def _async_update_data(self) -> LumagenState:
        """Seed the initial data after ``start()``.

        pylumagen fires the callback each time anything changes, so by the
        time this method runs after ``_async_setup`` we already have a
        populated snapshot. The client's own poll loop handles ongoing
        freshness — ``update_interval`` is ``None`` here so this function
        is only hit via ``async_config_entry_first_refresh``.
        """
        if not self.client.connected:
            raise UpdateFailed("Lumagen client is not connected")
        return self.client.state

    async def async_shutdown(self) -> None:
        """Clean up the subscription and stop the client."""
        await super().async_shutdown()
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        await self.client.stop()

    @callback
    def _on_state_update(
        self, state: LumagenState, _codes: tuple[str, ...]
    ) -> None:
        """Push-side path: pylumagen -> coordinator -> entities."""
        self.async_set_updated_data(state)


async def create_lumagen_client(url: str) -> LumagenClient:
    """Factory used by both config-flow validation and entry setup."""
    transport = LumagenTransport(url)
    return LumagenClient(transport)
