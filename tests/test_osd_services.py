"""Tests for the OSD message, input label and input restart services.

These check the HA-side wiring — schema defaults, argument plumbing, and that
each service reaches the right client method. The wire encodings those methods
produce are covered upstream in aiolumagen.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from aiolumagen import LumagenState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lumagen.const import (
    ATTR_BLOCK_CHAR,
    ATTR_CENTER,
    ATTR_DURATION,
    ATTR_INPUT,
    ATTR_LABEL,
    ATTR_LINE1,
    ATTR_LINE2,
    ATTR_MEMORY,
    ATTR_MESSAGE,
    CONF_URL,
    DOMAIN,
    SERVICE_RESTART_INPUT,
    SERVICE_SEND_OSD_MESSAGE,
    SERVICE_SET_INPUT_LABEL,
)

FAKE_URL = "esphome://10.0.0.42:6053/?port_name=Lumagen&key=abc"
CLIENT_FACTORY = "custom_components.lumagen.coordinator.create_lumagen_client"


def _make_client_mock() -> MagicMock:
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()
    client.send_command = AsyncMock()
    for name in (
        "query_sharpness",
        "query_game_mode",
        "query_auto_aspect",
        "query_display_rec2020",
        "query_source_hdr_status",
        "query_input_labels",
        "show_message",
        "clear_message",
        "set_osd_block_char",
        "set_input_label",
        "restart_input",
    ):
        setattr(client, name, AsyncMock())
    client.connected = True
    client.subscribe = MagicMock(return_value=lambda: None)
    client.state = LumagenState(model="RadiancePro", firmware="030225")
    return client


async def _setup_entry(hass: HomeAssistant, client: MagicMock) -> None:
    with patch(CLIENT_FACTORY, new=AsyncMock(return_value=client)):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_URL: FAKE_URL},
            unique_id="test_lumagen",
            title="Lumagen RadiancePro",
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture
async def client(hass: HomeAssistant) -> MagicMock:
    mock = _make_client_mock()
    await _setup_entry(hass, mock)
    return mock


# ---------- Registration ----------


async def test_all_services_are_registered(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_SEND_OSD_MESSAGE,
        SERVICE_SET_INPUT_LABEL,
        SERVICE_RESTART_INPUT,
    ):
        assert not hass.services.has_service(DOMAIN, service)
    await _setup_entry(hass, _make_client_mock())
    for service in (
        SERVICE_SEND_OSD_MESSAGE,
        SERVICE_SET_INPUT_LABEL,
        SERVICE_RESTART_INPUT,
    ):
        assert hass.services.has_service(DOMAIN, service)


# ---------- send_osd_message ----------


async def test_send_osd_message_passes_text_and_defaults(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """Duration defaults to 3 and centering to off, matching the schema."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_OSD_MESSAGE,
        {ATTR_MESSAGE: "Front door motion"},
        blocking=True,
    )
    client.show_message.assert_awaited_once_with(
        "Front door motion", line1=None, line2=None, duration=3, center=False
    )


async def test_send_osd_message_passes_explicit_rows(
    hass: HomeAssistant, client: MagicMock
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_OSD_MESSAGE,
        {
            ATTR_LINE1: "Front door",
            ATTR_LINE2: "Motion detected",
            ATTR_DURATION: 9,
            ATTR_CENTER: True,
        },
        blocking=True,
    )
    client.show_message.assert_awaited_once_with(
        None,
        line1="Front door",
        line2="Motion detected",
        duration=9,
        center=True,
    )


async def test_send_osd_message_sets_the_bar_character_first(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """Ordering matters: the block character has to be nominated before the
    message that uses it, or the first bar renders as literal text.

    Folding it into this service makes a volume bar one call instead of two.
    """
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_OSD_MESSAGE,
        {ATTR_MESSAGE: "Volume ####", ATTR_BLOCK_CHAR: "#"},
        blocking=True,
    )
    client.set_osd_block_char.assert_awaited_once_with("#")
    assert client.set_osd_block_char.await_count == 1
    client.show_message.assert_awaited_once()
    # Both went out, and the block char first.
    assert client.mock_calls.index(
        next(c for c in client.mock_calls if c[0] == "set_osd_block_char")
    ) < client.mock_calls.index(next(c for c in client.mock_calls if c[0] == "show_message"))


async def test_send_osd_message_skips_block_char_when_absent(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """The setting is sticky on the device, so it must not be touched
    unasked — doing so would silently change how later messages render."""
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_OSD_MESSAGE, {ATTR_MESSAGE: "hi"}, blocking=True
    )
    client.set_osd_block_char.assert_not_awaited()


@pytest.mark.parametrize("duration", [-1, 10, 99])
async def test_send_osd_message_rejects_bad_duration(
    hass: HomeAssistant, client: MagicMock, duration: int
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_OSD_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_DURATION: duration},
            blocking=True,
        )
    client.show_message.assert_not_awaited()


async def test_send_osd_message_rejects_multi_character_bar(
    hass: HomeAssistant, client: MagicMock
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_OSD_MESSAGE,
            {ATTR_MESSAGE: "hi", ATTR_BLOCK_CHAR: "##"},
            blocking=True,
        )


# ---------- set_input_label ----------


async def test_set_input_label_defaults_to_all_memory_banks(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """Writing one bank only would leave the other three showing the old name,
    which reads as the service having half-worked."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_INPUT_LABEL,
        {ATTR_INPUT: 2, ATTR_LABEL: "Apple TV"},
        blocking=True,
    )
    client.set_input_label.assert_awaited_once_with(2, "Apple TV", memory="ALL")


async def test_set_input_label_honours_a_specific_bank(
    hass: HomeAssistant, client: MagicMock
) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_INPUT_LABEL,
        {ATTR_INPUT: 3, ATTR_LABEL: "Roku", ATTR_MEMORY: "B"},
        blocking=True,
    )
    client.set_input_label.assert_awaited_once_with(3, "Roku", memory="B")


@pytest.mark.parametrize("number", [0, 9, 19])
async def test_set_input_label_rejects_inputs_outside_1_8(
    hass: HomeAssistant, client: MagicMock, number: int
) -> None:
    """Narrower than input selection, which goes to 19 — the device only
    defines labelling for the first eight."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_INPUT_LABEL,
            {ATTR_INPUT: number, ATTR_LABEL: "X"},
            blocking=True,
        )
    client.set_input_label.assert_not_awaited()


async def test_set_input_label_rejects_an_overlong_label(
    hass: HomeAssistant, client: MagicMock
) -> None:
    """Caught by the schema so the UI can enforce it, as well as by the library."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_INPUT_LABEL,
            {ATTR_INPUT: 1, ATTR_LABEL: "x" * 11},
            blocking=True,
        )
    client.set_input_label.assert_not_awaited()


async def test_set_input_label_rejects_an_unknown_bank(
    hass: HomeAssistant, client: MagicMock
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_INPUT_LABEL,
            {ATTR_INPUT: 1, ATTR_LABEL: "X", ATTR_MEMORY: "Z"},
            blocking=True,
        )


# ---------- restart_input ----------


async def test_restart_input_defaults_to_all(hass: HomeAssistant, client: MagicMock) -> None:
    """Omitting the input restarts everything, matching the client default."""
    await hass.services.async_call(DOMAIN, SERVICE_RESTART_INPUT, {}, blocking=True)
    client.restart_input.assert_awaited_once_with("all")


async def test_restart_input_targets_one_input(hass: HomeAssistant, client: MagicMock) -> None:
    await hass.services.async_call(DOMAIN, SERVICE_RESTART_INPUT, {ATTR_INPUT: 3}, blocking=True)
    client.restart_input.assert_awaited_once_with(3)


@pytest.mark.parametrize("number", [0, 9])
async def test_restart_input_rejects_out_of_range(
    hass: HomeAssistant, client: MagicMock, number: int
) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, SERVICE_RESTART_INPUT, {ATTR_INPUT: number}, blocking=True
        )
    client.restart_input.assert_not_awaited()
