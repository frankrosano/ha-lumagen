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

import hashlib
import logging
from typing import Any

import voluptuous as vol
from aiolumagen import LumagenConnectionError, LumagenError
from homeassistant.components import usb
from homeassistant.components.usb import SerialDevice, USBDevice
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import coordinator as _coordinator
from .const import (
    CONF_POLL_INTERVAL,
    CONF_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    VALIDATION_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class LumagenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Lumagen config flow."""

    # Still 1. The unique_id digest changed in 0.8.0 (SHA-1 -> SHA-256), which
    # is normally a migration, but this integration is pre-release with a
    # single known install — the entry gets removed and re-added instead. Don't
    # bump VERSION without adding async_migrate_entry: HA fails an entry whose
    # stored version is older than the flow's with no handler present.
    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Expose the poll-interval options flow."""
        return LumagenOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        options = [_option_for_port(p) for p in ports]
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
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class LumagenOptionsFlow(OptionsFlow):
    """Tune how often the integration polls the Lumagen.

    Only the fields the Lumagen never pushes (sharpness, game mode, auto
    aspect, display Rec.2020, source HDR metadata) are affected by this —
    everything in the Full v5 report still arrives in real time regardless.

    Saving reloads the config entry, because the interval is baked into the
    ``LumagenClient`` at construction time.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL])}
            )

        current = self.config_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_POLL_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _unique_id_for(url: str) -> str:
    """Stable per-URL unique ID.

    This is a deduplication key, not a signature: it exists so
    ``_abort_if_unique_id_configured`` can recognise a URL that is already
    set up, and so the device page shows something opaque rather than a URL
    containing a pre-shared key. Nothing verifies it and no attacker
    benefits from colliding with it.

    It is SHA-256 all the same. The digest was SHA-1 through v0.7 and was
    swapped because there is no reason to ship a primitive that every
    scanner flags on sight, and arguing the exception on each report costs
    more than the change did. ``usedforsecurity=False`` records the intent
    and keeps the call working on FIPS builds.

    Truncated to 16 hex chars — 64 bits, so birthday collisions arrive
    around 2^32 distinct URLs. A home has a handful.

    Note this is derived from the URL, so moving the Lumagen to a different
    bridge changes its identity. That is a deliberate v0.1 limitation, not
    a property of the digest: we don't try to track a unit across
    relocations.

    Because :mod:`.entity` builds every entity ``unique_id`` and the device
    registry identifiers on top of this value, changing the digest changes
    the identity of everything the integration owns. An entry created
    before 0.8.0 keeps its old SHA-1 id and keeps working, but a re-add of
    the same URL will no longer be recognised as a duplicate. The fix for
    an existing install is to remove and re-add the integration; there is
    deliberately no migration, as this is pre-release with one known
    install. Add one before that stops being true.
    """
    return hashlib.sha256(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _default_title(url: str) -> str:
    """Fallback title if we couldn't extract a model during validation."""
    return f"Lumagen ({url})"


def _option_for_port(port: USBDevice | SerialDevice) -> SelectOptionDict:
    """Build a dropdown entry from a scanned serial port.

    ``USBDevice`` (physical ports) has ``vid``/``pid``; ``SerialDevice``
    (ESPHome serial_proxy URLs and other virtual ports) does not. Use
    ``getattr`` so both work through the same formatter.
    """
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

        # Ask for device info and await the reply. This replaced a 0.1s poll
        # over client.state.model wrapped in asyncio.timeout — the library now
        # correlates a query to its response, so "did a Lumagen answer on this
        # port?" is a value we can await instead of a condition to spin on.
        # The wire code stays inside aiolumagen; this side never spells ZQS01.
        try:
            device_info = await client.query_device_info(timeout=VALIDATION_TIMEOUT)
        except TimeoutError:
            _LOGGER.debug(
                "Lumagen at %s did not answer the device-info query within %.1fs",
                url,
                VALIDATION_TIMEOUT,
            )
            return "no_response", None
        except LumagenConnectionError as err:
            # The port opened but dropped before answering.
            _LOGGER.debug("Lumagen URL %s disconnected during validation: %s", url, err)
            return "cannot_connect", None

        # A reply is not automatically proof of a Lumagen that can identify
        # itself: the device answers *any* syntactically valid query by
        # echoing the code with an empty payload. Requiring content keeps the
        # strictness the previous state-polling check had, which only accepted
        # a port once a model had actually been parsed.
        if not device_info:
            _LOGGER.debug("Lumagen at %s answered the device-info query empty", url)
            return "no_response", None

        state = client.state
        model = state.model or "Radiance Pro"
        return None, f"Lumagen {model}"
    finally:
        await client.stop()
