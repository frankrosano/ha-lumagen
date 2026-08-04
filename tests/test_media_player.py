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
from aiolumagen import Colorspace, HdrStatus, LumagenState, SourceMode
from homeassistant.components.media_player import MediaPlayerState

from custom_components.lumagen.media_player import LumagenMediaPlayer


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
def test_state_from_power(power_on: bool | None, expected: MediaPlayerState | None) -> None:
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
def test_source_from_current_input(current_input: str | None, expected: str | None) -> None:
    entity, _ = _media_player(LumagenState(current_input=current_input))
    assert entity.source == expected


def test_source_list_falls_back_to_input_n_without_labels() -> None:
    entity, _ = _media_player(LumagenState())
    assert entity.source_list == [f"Input {n}" for n in range(1, 9)]


def test_source_list_uses_configured_labels_with_fallback() -> None:
    entity, _ = _media_player(LumagenState(input_labels={1: "Apple TV", 3: "Roku"}))
    assert entity.source_list == [
        "Apple TV",
        "Input 2",
        "Roku",
        "Input 4",
        "Input 5",
        "Input 6",
        "Input 7",
        "Input 8",
    ]


def test_source_uses_label_when_present() -> None:
    entity, _ = _media_player(LumagenState(current_input="03", input_labels={3: "Apple TV"}))
    assert entity.source == "Apple TV"


def test_source_empty_label_falls_back() -> None:
    """A cleared (empty-string) label must not render a blank source."""
    entity, _ = _media_player(LumagenState(current_input="2", input_labels={2: ""}))
    assert entity.source == "Input 2"


def test_duplicate_labels_fall_back_to_numbered() -> None:
    """Every input sharing one generic label must not collapse to one option.

    Regression: a device reporting all inputs as "Input" produced 8 identical
    dropdown entries; picking any of them resolved to input 1.
    """
    entity, _ = _media_player(
        LumagenState(input_labels=dict.fromkeys(range(1, 9), "Input"))
    )
    assert entity.source_list == [f"Input {n}" for n in range(1, 9)]


async def test_select_source_duplicate_labels_dispatches_correct_input() -> None:
    entity, client = _media_player(
        LumagenState(input_labels=dict.fromkeys(range(1, 9), "Input"))
    )
    await entity.async_select_source("Input 5")
    client.set_input.assert_awaited_once_with(5)


def test_source_current_with_duplicate_labels_is_numbered() -> None:
    entity, _ = _media_player(
        LumagenState(current_input="3", input_labels=dict.fromkeys(range(1, 9), "Input"))
    )
    assert entity.source == "Input 3"


def test_partial_duplicate_disambiguates_only_the_collision() -> None:
    """A unique custom label survives; only the colliding pair is numbered."""
    entity, _ = _media_player(
        LumagenState(input_labels={1: "TV", 2: "TV", 4: "Roku"})
    )
    assert entity.source_list == [
        "Input 1", "Input 2", "Input 3", "Roku",
        "Input 5", "Input 6", "Input 7", "Input 8",
    ]


async def test_select_disambiguated_label_dispatches_correct_input() -> None:
    entity, client = _media_player(
        LumagenState(input_labels={1: "TV", 2: "TV", 4: "Roku"})
    )
    await entity.async_select_source("Roku")
    client.set_input.assert_awaited_once_with(4)


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


async def test_select_source_by_configured_label_dispatches_set_input() -> None:
    """Selecting a configured label resolves to that input's number."""
    entity, client = _media_player(LumagenState(input_labels={2: "Roku"}))
    await entity.async_select_source("Roku")
    client.set_input.assert_awaited_once_with(2)


async def test_select_source_unknown_label_is_no_op() -> None:
    """A label matching no input (label or fallback) must not write anything."""
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


# ---------- card-facing now-playing fields ----------


def test_media_title_signal_path() -> None:
    """Scan letter comes from source_mode; zero-padding on the rate is stripped.

    Resolution fields are the bare line count (``2160``); the ``p``/``i`` is a
    separate field, so the letter is what keeps the digits from running
    together (``216059`` -> ``2160p59``).
    """
    entity, _ = _media_player(
        LumagenState(
            power_on=True,
            source_resolution="2160",
            source_vrate="059",
            source_mode=SourceMode.PROGRESSIVE,
            output_resolution="2160",
            output_vrate="059",
        )
    )
    assert entity.media_title == "2160p59 → 2160p59"


def test_media_title_interlaced_source_progressive_output() -> None:
    """Source scan comes from source_mode; the output is always labeled progressive."""
    entity, _ = _media_player(
        LumagenState(
            power_on=True,
            source_resolution="1080",
            source_vrate="060",
            source_mode=SourceMode.INTERLACED,
            output_resolution="2160",
            output_vrate="060",
        )
    )
    assert entity.media_title == "1080i60 → 2160p60"


def test_media_title_source_only() -> None:
    """Output unknown -> just the source side, no arrow."""
    entity, _ = _media_player(
        LumagenState(
            power_on=True,
            source_resolution="1080",
            source_vrate="024",
            source_mode=SourceMode.PROGRESSIVE,
        )
    )
    assert entity.media_title == "1080p24"


def test_media_title_source_scan_unknown_omits_letter() -> None:
    """Before source_mode is observed, no letter is inserted (digits run together)."""
    entity, _ = _media_player(
        LumagenState(power_on=True, source_resolution="2160", source_vrate="059")
    )
    assert entity.media_title == "216059"


def test_media_title_rate_only_gets_hz_suffix() -> None:
    entity, _ = _media_player(LumagenState(power_on=True, output_vrate="060"))
    assert entity.media_title == "60Hz"


def test_media_title_none_when_off() -> None:
    """Standby must not leave a stale signal path on the card."""
    entity, _ = _media_player(
        LumagenState(power_on=False, source_resolution="1080p", source_vrate="060")
    )
    assert entity.media_title is None


def test_media_title_none_when_powered_on_but_no_signal() -> None:
    entity, _ = _media_player(LumagenState(power_on=True))
    assert entity.media_title is None


def test_app_name_hdr_and_colorspace() -> None:
    entity, _ = _media_player(
        LumagenState(power_on=True, hdr_status=HdrStatus.HDR, colorspace=Colorspace.REC_2020)
    )
    assert entity.app_name == "HDR · Rec.2020"


def test_app_name_colorspace_only() -> None:
    entity, _ = _media_player(LumagenState(power_on=True, colorspace=Colorspace.REC_709))
    assert entity.app_name == "Rec.709"


def test_app_name_none_when_off() -> None:
    entity, _ = _media_player(LumagenState(power_on=False, hdr_status=HdrStatus.HDR))
    assert entity.app_name is None


def test_app_name_none_when_no_metadata() -> None:
    entity, _ = _media_player(LumagenState(power_on=True))
    assert entity.app_name is None
