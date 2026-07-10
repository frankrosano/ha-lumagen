"""Tests for the media_player entity.

The Lumagen media_player models power (on/off) and input selection
(source / source_list). Unlike aspect — which the device never reports as an
active preset — the current input *is* reported, so ``source`` reflects real
device state. These tests pin the state/source mapping and verify that
turn_on / turn_off / select_source dispatch to the right client calls.

Entities are built with ``__new__`` to bypass ``CoordinatorEntity.__init__``
(no real HASS needed) — same approach as test_switch_number_select.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.media_player import MediaPlayerState
from pylumagen import Colorspace, HdrStatus, LumagenState

from custom_components.lumagen.media_player import _SOURCE_LIST, LumagenMediaPlayer


def _media_player(state: LumagenState) -> tuple[LumagenMediaPlayer, MagicMock]:
    """Build a LumagenMediaPlayer wired to a stub coordinator + AsyncMock client."""
    client = MagicMock()
    client.power_on = AsyncMock()
    client.standby = AsyncMock()
    client.set_input = AsyncMock()

    coordinator = MagicMock()
    coordinator.data = state
    coordinator.client = client

    entity = LumagenMediaPlayer.__new__(LumagenMediaPlayer)
    entity.coordinator = coordinator
    return entity, client


# ---------- state ----------


@pytest.mark.parametrize(
    ("power_on", "expected"),
    [
        (True, MediaPlayerState.ON),
        (False, MediaPlayerState.OFF),
        (None, None),  # unobserved -> unknown, never fabricated
    ],
)
def test_state_from_power(
    power_on: bool | None, expected: MediaPlayerState | None
) -> None:
    entity, _ = _media_player(LumagenState(power_on=power_on))
    assert entity.state == expected


# ---------- source mapping ----------


@pytest.mark.parametrize(
    ("current_input", "expected"),
    [
        ("1", "Input 1"),
        ("03", "Input 3"),  # Lumagen zero-pads; int() strips it
        ("8", "Input 8"),
        ("9", None),  # outside the 1-8 surfaced list
        ("0", None),  # no input
        (None, None),  # unobserved
        ("abc", None),  # unparseable
    ],
)
def test_source_from_current_input(
    current_input: str | None, expected: str | None
) -> None:
    entity, _ = _media_player(LumagenState(current_input=current_input))
    assert entity.source == expected


def test_source_list_is_inputs_1_to_8() -> None:
    assert len(_SOURCE_LIST) == 8
    assert _SOURCE_LIST[0] == "Input 1"
    assert _SOURCE_LIST[-1] == "Input 8"


# ---------- command dispatch ----------


async def test_turn_on_dispatches_power_on() -> None:
    entity, client = _media_player(LumagenState())
    await entity.async_turn_on()
    client.power_on.assert_awaited_once_with()


async def test_turn_off_dispatches_standby() -> None:
    entity, client = _media_player(LumagenState())
    await entity.async_turn_off()
    client.standby.assert_awaited_once_with()


async def test_select_source_dispatches_set_input() -> None:
    entity, client = _media_player(LumagenState())
    await entity.async_select_source("Input 5")
    client.set_input.assert_awaited_once_with(5)


async def test_select_source_unknown_label_is_no_op() -> None:
    """A label outside the source_list must not write anything."""
    entity, client = _media_player(LumagenState())
    await entity.async_select_source("Input 99")
    client.set_input.assert_not_called()


# ---------- extra state attributes (signal summary) ----------


def test_extra_state_attributes_signal_summary() -> None:
    state = LumagenState(
        source_resolution="1080p",
        source_vrate="060",
        output_resolution="2160p",
        output_vrate="060",
        hdr_status=HdrStatus.HDR,
        colorspace=Colorspace.REC_2020,
    )
    entity, _ = _media_player(state)
    assert entity.extra_state_attributes == {
        "source_resolution": "1080p",
        "source_refresh_rate": "060",
        "output_resolution": "2160p",
        "output_refresh_rate": "060",
        "hdr_status": "HDR",
        "colorspace": "Rec.2020",
    }


def test_extra_state_attributes_none_when_unobserved() -> None:
    """A fresh state exposes a stable key set with None values, not zeros."""
    entity, _ = _media_player(LumagenState())
    assert entity.extra_state_attributes == {
        "source_resolution": None,
        "source_refresh_rate": None,
        "output_resolution": None,
        "output_refresh_rate": None,
        "hdr_status": None,
        "colorspace": None,
    }
