"""The Lumagen Radiance Pro integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import coordinator as _coordinator
from .const import (
    ATTR_COMMAND,
    ATTR_CR,
    CONF_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_RAW_COMMAND,
)
from .coordinator import LumagenConfigEntry, LumagenCoordinator

_LOGGER = logging.getLogger(__name__)


_SEND_RAW_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): vol.All(cv.string, vol.Length(min=1, max=64)),
        vol.Optional(ATTR_CR, default=False): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Set up a Lumagen from a config entry."""
    client = await _coordinator.create_lumagen_client(entry.data[CONF_URL])
    lumagen_coordinator = LumagenCoordinator(hass, entry, client)
    await lumagen_coordinator.async_config_entry_first_refresh()
    entry.runtime_data = lumagen_coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Unload a config entry — stop the client and drop the platforms."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_shutdown()
    # Tear down the service when the last config entry goes away. HA's
    # service registry doesn't support per-entry services natively, so we
    # use a single domain-level service that dispatches to whichever
    # config entry is loaded.
    if not hass.config_entries.async_loaded_entries(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)
    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Idempotently register the domain-level send_raw_command service.

    The service is keyed off the integration domain and routes to the
    first loaded Lumagen config entry. If you have multiple Lumagens
    (rare), call the service with a target's device_id so it can be
    routed; otherwise it picks whatever entry is loaded.
    """
    if hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND):
        return

    async def _handle_send_raw_command(call: ServiceCall) -> None:
        command: str = call.data[ATTR_COMMAND]
        cr: bool = call.data[ATTR_CR]
        loaded_entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not loaded_entries:
            raise ServiceValidationError(
                "No Lumagen config entries are loaded; cannot send command."
            )
        # If the user specified a target device, prefer the matching
        # entry. Otherwise fall back to the first loaded entry.
        target_entry = _resolve_target_entry(hass, call, loaded_entries)
        coordinator: LumagenCoordinator = target_entry.runtime_data
        _LOGGER.debug(
            "send_raw_command -> entry=%s command=%r cr=%s",
            target_entry.entry_id, command, cr,
        )
        # refresh=False — the caller is doing protocol-level work and
        # almost certainly doesn't want a follow-up status query muddying
        # the response stream they're watching.
        await coordinator.client.send_command(command, cr=cr, refresh=False)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        _handle_send_raw_command,
        schema=_SEND_RAW_COMMAND_SCHEMA,
    )


def _resolve_target_entry(
    hass: HomeAssistant,
    call: ServiceCall,
    loaded_entries: list[LumagenConfigEntry],
) -> LumagenConfigEntry:
    """Pick the config entry the service call should route to.

    Honors ``device_id`` targets via the device registry. Falls back to
    the first loaded entry when no target is given (the common single-
    Lumagen case). Raises if a target is given that doesn't match any
    loaded Lumagen entry, so misrouted automations fail loudly.
    """
    device_ids: list[str] = call.data.get("device_id", []) or []
    if not device_ids:
        return loaded_entries[0]

    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        for entry in loaded_entries:
            if entry.entry_id in device.config_entries:
                return entry
    raise ServiceValidationError(
        f"None of the targeted devices are linked to a loaded Lumagen "
        f"config entry: {device_ids!r}"
    )
