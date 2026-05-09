"""Config flow for the Lumagen Radiance Pro integration.

The flow is intentionally one step: the user picks a serial port from a
dropdown populated by ``usb.async_scan_serial_ports``. That list includes
real ``/dev/tty*`` ports and ``esphome://...`` URLs for any ESPHome
``serial_proxy`` entities in adopted devices, so users never need to type
a host, port, or pre-shared key.

Validation opens the selected port, waits briefly for ``!S01`` (device
info) to confirm there's actually a Lumagen on the other end, then
closes. The final config entry stores only the URL; reconfiguration is a
matter of re-picking from the dropdown.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import usb
from homeassistant.components.usb import USBDevice
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from pylumagen import LumagenConnectionError, LumagenError

from . import coordinator as _coordinator
from .const import CONF_URL, DOMAIN, VALIDATION_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class LumagenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Lumagen config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Single-step selection of a serial port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL]
            await self.async_set_unique_id(_unique_id_for(url))
            self._abort_if_unique_id_configured()
            error_code, title = await _validate_url(url)
            if error_code is None:
                return self.async_create_entry(
                    title=title or _default_title(url),
                    data={CONF_URL: url},
                )
            errors["base"] = error_code

        ports = await usb.async_scan_serial_ports(self.hass)
        options = [_option_for_port(p) for p in ports if isinstance(p, USBDevice)]
        if not options:
            errors.setdefault("base", "no_ports")

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=True,  # allow manual URL entry
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


def _unique_id_for(url: str) -> str:
    """Stable per-URL unique ID.

    A SHA-1 prefix is plenty of uniqueness (~2^64 for 16 hex chars) and
    keeps the ID opaque in the UI. If the user moves the Lumagen to a new
    bridge, the URL changes and they re-add the integration; we don't try
    to track the device across relocations in v0.1.
    """
    return hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _default_title(url: str) -> str:
    """Fallback title if we couldn't extract a model during validation."""
    return f"Lumagen ({url})"


def _option_for_port(port: USBDevice) -> SelectOptionDict:
    """Build a dropdown entry from a scanned serial port."""
    label = usb.human_readable_device_name(
        port.device,
        port.serial_number,
        port.manufacturer,
        port.description,
        getattr(port, "vid", None),
        getattr(port, "pid", None),
    )
    return SelectOptionDict(value=port.device, label=label)


async def _validate_url(url: str) -> tuple[str | None, str | None]:
    """Open the URL, wait for device info, close. Return (error, title).

    On success returns ``(None, "Lumagen Radiance Pro <firmware>")`` or
    similar, so the created entry gets a human-friendly title. On failure
    returns an error code from ``strings.json`` and ``None`` for title.
    """
    client = await _coordinator.create_lumagen_client(url)
    try:
        try:
            await client.start()
        except LumagenConnectionError as err:
            _LOGGER.debug("Lumagen URL %s failed to open: %s", url, err)
            return "cannot_connect", None
        except LumagenError as err:
            _LOGGER.debug("Lumagen URL %s reported an error: %s", url, err)
            return "unknown", None

        # Wait up to VALIDATION_TIMEOUT for at least !S01 (model/firmware).
        # The library's startup sequence fires ZQS01 for us.
        try:
            async with asyncio.timeout(VALIDATION_TIMEOUT):
                while client.state.model is None:
                    await asyncio.sleep(0.1)
        except TimeoutError:
            _LOGGER.debug("Lumagen at %s did not answer ZQS01 within %.1fs",
                          url, VALIDATION_TIMEOUT)
            return "no_response", None

        state = client.state
        title = f"Lumagen {state.model}"
        if state.firmware:
            title += f" ({state.firmware})"
        return None, title
    finally:
        await client.stop()
