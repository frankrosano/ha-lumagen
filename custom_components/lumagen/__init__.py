"""The Lumagen Radiance Pro integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.const import ATTR_AREA_ID, ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import coordinator as _coordinator
from .const import (
    ATTR_COMMAND,
    ATTR_CR,
    CONF_POLL_INTERVAL,
    CONF_URL,
    DEFAULT_POLL_INTERVAL,
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
        # Optional routing for the rare multi-Lumagen setup. These must be
        # declared even though they're optional: a plain vol.Schema rejects
        # undeclared keys, so without them any call carrying a target would
        # fail validation before reaching the handler.
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_AREA_ID): vol.All(cv.ensure_list, [cv.string]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: LumagenConfigEntry) -> bool:
    """Set up a Lumagen from a config entry."""
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    client = await _coordinator.create_lumagen_client(
        entry.data[CONF_URL], poll_interval=poll_interval
    )
    lumagen_coordinator = LumagenCoordinator(hass, entry, client)
    await lumagen_coordinator.async_config_entry_first_refresh()
    entry.runtime_data = lumagen_coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    # The poll interval is baked into the client at construction, so a change
    # to it only takes effect on reload.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: LumagenConfigEntry
) -> None:
    """Reload the entry so a new poll interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


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

    Targeting is optional — with a single Lumagen (the overwhelmingly
    common case) the call needs no target at all and lands on the only
    loaded entry. ``device_id`` and ``entity_id`` are both honored for
    multi-Lumagen setups; an entity is resolved to its device first.

    Raises if a device/entity target is given that doesn't match any
    loaded Lumagen entry, so a misrouted automation fails loudly instead
    of quietly commanding the wrong unit. An ``area_id``-only target
    isn't resolved (there's no sensible per-area routing for a single
    piece of AV gear) and falls back to the first loaded entry.
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    device_ids: list[str] = list(call.data.get(ATTR_DEVICE_ID) or [])
    entity_ids: list[str] = list(call.data.get(ATTR_ENTITY_ID) or [])

    # Resolve any entity targets to their owning device.
    if entity_ids:
        ent_reg = er.async_get(hass)
        for entity_id in entity_ids:
            entity = ent_reg.async_get(entity_id)
            if entity is not None and entity.device_id is not None:
                device_ids.append(entity.device_id)

    if not device_ids:
        return loaded_entries[0]

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
