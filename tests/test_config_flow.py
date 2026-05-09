"""Config-flow tests for the Lumagen integration.

These run against an in-memory HA via ``pytest-homeassistant-custom-component``
with every pylumagen touchpoint mocked. They confirm the wiring between
the dropdown, unique-ID generation, validation, and entry creation —
not the library itself (that's covered in pylumagen's own tests).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.components.usb import SerialDevice, USBDevice
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pylumagen import LumagenConnectionError, LumagenState

from custom_components.lumagen.const import CONF_URL, DOMAIN

FAKE_URL = "esphome://10.0.0.42:6053/?port_name=Lumagen&key=abc"
# Both the config flow validator and __init__ fetch the client via this
# single symbol; patching there covers both paths.
CLIENT_FACTORY = "custom_components.lumagen.coordinator.create_lumagen_client"


def _fake_usb_device(url: str = FAKE_URL, description: str = "Lumagen") -> USBDevice:
    return USBDevice(
        device=url,
        vid="0000",
        pid="0000",
        serial_number=None,
        manufacturer="ESPHome",
        description=description,
    )


def _patch_scan(ports: list[USBDevice]) -> patch:
    """Mock the USB port scan used by the config flow's dropdown."""
    return patch(
        "custom_components.lumagen.config_flow.usb.async_scan_serial_ports",
        return_value=ports,
    )


def _make_client_mock(*, model: str = "RadiancePro", firmware: str = "030225") -> MagicMock:
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.connected = True
    client.subscribe = MagicMock(return_value=lambda: None)
    client.state = LumagenState(model=model, firmware=firmware)
    return client


async def test_form_shows_dropdown(hass: HomeAssistant) -> None:
    """First invocation renders the dropdown with scanned ports."""
    with _patch_scan([_fake_usb_device()]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] in (None, {})


async def test_dropdown_includes_esphome_serial_proxy_ports(hass: HomeAssistant) -> None:
    """SerialDevice entries (e.g. ESPHome serial_proxy URLs) must appear.

    Regression for the day-one bug where ``isinstance(p, USBDevice)``
    filtered out every ESPHome-proxied port because those come back as
    plain ``SerialDevice``, not ``USBDevice``. The dropdown must accept
    both shapes.
    """
    esphome_proxy = SerialDevice(
        device="esphome://10.0.0.42:6053/?port_name=Lumagen&key=abc",
        serial_number=None,
        manufacturer="ESPHome",
        description="Lumagen",
    )
    with _patch_scan([esphome_proxy]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] in (None, {})
    schema_options = result["data_schema"].schema[CONF_URL].config["options"]
    assert any(opt["value"] == esphome_proxy.device for opt in schema_options)


async def test_happy_path_creates_entry(hass: HomeAssistant) -> None:
    """User picks a port, validation succeeds, entry is created with model title."""
    client = _make_client_mock()
    with (
        _patch_scan([_fake_usb_device()]),
        patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"], {CONF_URL: FAKE_URL}
        )
        # Let HA run the entry-setup chain while the patch is still active.
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: FAKE_URL}
    # Title is "Lumagen <model>" — firmware must NOT appear here because
    # it changes over OTA updates; it lives in DeviceInfo.sw_version instead.
    assert result["title"] == "Lumagen RadiancePro"


async def test_cannot_connect_surfaces_error(hass: HomeAssistant) -> None:
    """A connection error on validation shows the cannot_connect error string."""
    client = _make_client_mock()
    client.start = AsyncMock(side_effect=LumagenConnectionError("boom"))
    with (
        _patch_scan([_fake_usb_device()]),
        patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"], {CONF_URL: FAKE_URL}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_response_when_device_info_stays_empty(hass: HomeAssistant) -> None:
    """If ZQS01 never lands, validation times out with no_response."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.state = LumagenState()  # model=None forever
    with (
        _patch_scan([_fake_usb_device()]),
        patch("custom_components.lumagen.config_flow.VALIDATION_TIMEOUT", 0.1),
        patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"], {CONF_URL: FAKE_URL}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_response"}


async def test_already_configured_aborts(hass: HomeAssistant) -> None:
    """A second flow for the same URL aborts rather than creating a duplicate."""
    # Prime a first config entry via the happy path.
    client = _make_client_mock()
    with (
        _patch_scan([_fake_usb_device()]),
        patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)),
    ):
        init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            init["flow_id"], {CONF_URL: FAKE_URL}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Now try again with the same URL — the validator doesn't even run.
    with _patch_scan([_fake_usb_device()]):
        second_init = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        second_result = await hass.config_entries.flow.async_configure(
            second_init["flow_id"], {CONF_URL: FAKE_URL}
        )
    assert second_result["type"] is FlowResultType.ABORT
    assert second_result["reason"] == "already_configured"
