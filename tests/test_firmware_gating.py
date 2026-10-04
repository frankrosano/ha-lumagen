"""Service gating during a firmware update."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.lumagen.const import (
    ATTR_COMMAND,
    DOMAIN,
    SERVICE_SEND_RAW_COMMAND,
)

from .firmware_helpers import make_client, setup_entry


async def test_domain_services_refuse_during_update(hass: HomeAssistant) -> None:
    client = make_client()
    entry = await setup_entry(hass, client)
    entry.runtime_data.async_set_firmware_update_active(True)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_SEND_RAW_COMMAND, {ATTR_COMMAND: "ZQS01"}, blocking=True
        )
    assert err.value.translation_key == "firmware_update_active"
    assert not [c for c in client.send_command.await_args_list if c.args == ("ZQS01",)]


async def test_options_change_mid_update_defers_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_client())
    coordinator = entry.runtime_data
    coordinator.async_set_firmware_update_active(True)

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        hass.config_entries.async_update_entry(entry, options={"firmware_channel": "production"})
        await hass.async_block_till_done()
    reload.assert_not_awaited()
    assert coordinator.reload_pending is True


async def test_options_change_otherwise_reloads(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_client())
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        hass.config_entries.async_update_entry(entry, options={"firmware_channel": "production"})
        await hass.async_block_till_done()
    reload.assert_awaited_once_with(entry.entry_id)
