"""The Lumagen Radiance Pro integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from . import coordinator as _coordinator
from .const import CONF_URL, PLATFORMS
from .coordinator import LumagenConfigEntry, LumagenCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Set up a Lumagen from a config entry."""
    client = await _coordinator.create_lumagen_client(entry.data[CONF_URL])
    lumagen_coordinator = LumagenCoordinator(hass, entry, client)
    await lumagen_coordinator.async_config_entry_first_refresh()
    entry.runtime_data = lumagen_coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Unload a config entry — stop the client and drop the platforms."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_shutdown()
    return True
