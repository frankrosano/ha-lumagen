"""Service gating during a firmware update, and the qualification service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiolumagen.firmware import UpdatePlan, UpdateResult
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized

from custom_components.lumagen.const import (
    ATTR_COMMAND,
    DOMAIN,
    SERVICE_QUALIFY_FIRMWARE_TRANSFER,
    SERVICE_SEND_RAW_COMMAND,
)

from .firmware_helpers import make_client, notification_messages, setup_entry

INSTALL_PATH = "custom_components.lumagen.firmware.async_install_firmware"
STAGED = UpdateResult(
    plan=UpdatePlan(),
    written=("section0",),
    flush_calls=112,
    flush_retries=0,
    notes=("synthetic note",),
)


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


async def test_qualify_service_registered(hass: HomeAssistant) -> None:
    await setup_entry(hass, make_client())
    assert hass.services.has_service(DOMAIN, SERVICE_QUALIFY_FIRMWARE_TRANSFER)


async def test_qualify_runs_scratch_only_and_notifies(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_client())
    install = AsyncMock(return_value=(STAGED, "firmware_power_unchanged"))
    with patch(INSTALL_PATH, install):
        await hass.services.async_call(DOMAIN, SERVICE_QUALIFY_FIRMWARE_TRANSFER, {}, blocking=True)
    install.assert_awaited_once()
    args, kwargs = install.await_args
    assert args[1] is entry.runtime_data
    assert args[2].revision.mmddyy == "030326"
    assert kwargs["promote"] is False
    assert kwargs["only"] == ["section0"]
    (message,) = notification_messages(hass)
    assert "section0" in message
    assert "112" in message
    assert "synthetic note" in message


async def test_qualify_is_admin_only(hass: HomeAssistant, hass_read_only_user: User) -> None:
    await setup_entry(hass, make_client())
    install = AsyncMock()
    with patch(INSTALL_PATH, install), pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_QUALIFY_FIRMWARE_TRANSFER,
            {},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    install.assert_not_awaited()


async def test_qualify_refused_during_update(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_client())
    entry.runtime_data.async_set_firmware_update_active(True)
    install = AsyncMock()
    with patch(INSTALL_PATH, install), pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, SERVICE_QUALIFY_FIRMWARE_TRANSFER, {}, blocking=True)
    install.assert_not_awaited()


async def test_qualify_service_removed_with_last_entry(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_client())
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_QUALIFY_FIRMWARE_TRANSFER)
