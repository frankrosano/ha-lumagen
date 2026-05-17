"""Tests for the new switch / number / select entities (Phase 1).

These exercise the wiring between HA entity callbacks and the pylumagen
client. We build a minimal fake LumagenState + AsyncMock client and call
the dispatch functions directly — entity-platform integration is exercised
via test_full_setup below, but per-feature behavior is easier to pin by
calling the helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pylumagen import LumagenState
from pylumagen.state import SharpnessSensitivity

from custom_components.lumagen.number import (
    _set_fan_speed,
    _set_sharpness_level,
)
from custom_components.lumagen.select import (
    _closest_aspect_label,
    _current_sharpness_sensitivity,
    _select_sharpness_sensitivity,
    _select_subtitle_shift,
)
from custom_components.lumagen.switch import (
    _set_game_mode,
    _set_sharpness_enabled,
)

# ---------- Switch wiring ----------


async def test_switch_set_sharpness_enabled_preserves_other_components() -> None:
    """Toggling enabled must keep the existing level + sensitivity values."""
    client = MagicMock()
    client.set_sharpness = AsyncMock()
    state = LumagenState(
        sharpness_enabled=False,
        sharpness_level=5,
        sharpness_sensitivity=SharpnessSensitivity.HIGH,
    )

    await _set_sharpness_enabled(client, state, True)

    client.set_sharpness.assert_awaited_once_with(
        enabled=True, level=5, sensitivity="H"
    )


async def test_switch_set_sharpness_enabled_uses_defaults_when_state_unobserved() -> None:
    """Before ZQI30 lands, level/sensitivity are None — fall back to sane defaults."""
    client = MagicMock()
    client.set_sharpness = AsyncMock()
    state = LumagenState()  # all None

    await _set_sharpness_enabled(client, state, True)

    client.set_sharpness.assert_awaited_once_with(
        enabled=True, level=4, sensitivity="N"
    )


async def test_switch_set_game_mode_dispatches_to_client() -> None:
    client = MagicMock()
    client.set_game_mode = AsyncMock()
    await _set_game_mode(client, LumagenState(), True)
    client.set_game_mode.assert_awaited_once_with(True)


# ---------- Number wiring ----------


async def test_number_set_sharpness_level_preserves_enabled_and_sensitivity() -> None:
    client = MagicMock()
    client.set_sharpness = AsyncMock()
    state = LumagenState(
        sharpness_enabled=True,
        sharpness_level=2,
        sharpness_sensitivity=SharpnessSensitivity.NORMAL,
    )

    await _set_sharpness_level(client, state, 7)

    client.set_sharpness.assert_awaited_once_with(
        enabled=True, level=7, sensitivity="N"
    )


async def test_number_set_sharpness_level_defaults_when_state_unobserved() -> None:
    """Setting only the level on a fresh state must not silently turn sharpening on."""
    client = MagicMock()
    client.set_sharpness = AsyncMock()

    await _set_sharpness_level(client, LumagenState(), 3)

    client.set_sharpness.assert_awaited_once_with(
        enabled=False,  # default — moving the slider doesn't imply enabling
        level=3,
        sensitivity="N",
    )


async def test_number_set_fan_speed_dispatches_to_client() -> None:
    client = MagicMock()
    client.set_fan_speed = AsyncMock()
    await _set_fan_speed(client, LumagenState(), 4)
    client.set_fan_speed.assert_awaited_once_with(4)


# ---------- Select wiring ----------


async def test_select_sharpness_sensitivity_normal_to_high_preserves_other_components() -> None:
    client = MagicMock()
    client.set_sharpness = AsyncMock()
    state = LumagenState(
        sharpness_enabled=True,
        sharpness_level=6,
        sharpness_sensitivity=SharpnessSensitivity.NORMAL,
    )

    await _select_sharpness_sensitivity(client, state, "High")

    client.set_sharpness.assert_awaited_once_with(
        enabled=True, level=6, sensitivity="H"
    )


async def test_select_sharpness_sensitivity_unknown_label_is_no_op() -> None:
    """A label outside the documented list shouldn't write anything."""
    client = MagicMock()
    client.set_sharpness = AsyncMock()
    await _select_sharpness_sensitivity(client, LumagenState(), "Bogus")
    client.set_sharpness.assert_not_called()


async def test_select_subtitle_shift_off_small_large_dispatch() -> None:
    client = MagicMock()
    client.set_subtitle_shift = AsyncMock()

    await _select_subtitle_shift(client, LumagenState(), "Off")
    await _select_subtitle_shift(client, LumagenState(), "Small")
    await _select_subtitle_shift(client, LumagenState(), "Large")

    assert [c.args for c in client.set_subtitle_shift.await_args_list] == [
        (0,), (1,), (2,)
    ]


async def test_select_subtitle_shift_unknown_label_is_no_op() -> None:
    client = MagicMock()
    client.set_subtitle_shift = AsyncMock()
    await _select_subtitle_shift(client, LumagenState(), "Bogus")
    client.set_subtitle_shift.assert_not_called()


@pytest.mark.parametrize(
    ("sensitivity", "expected"),
    [
        (SharpnessSensitivity.NORMAL, "Normal"),
        (SharpnessSensitivity.HIGH, "High"),
        (None, None),
    ],
)
def test_current_sharpness_sensitivity_label(
    sensitivity: SharpnessSensitivity | None, expected: str | None
) -> None:
    assert _current_sharpness_sensitivity(
        LumagenState(sharpness_sensitivity=sensitivity)
    ) == expected


# Sanity that the existing aspect helper still passes (regression after edits).
def test_closest_aspect_label_still_works() -> None:
    assert _closest_aspect_label("178") == "16:9"
    assert _closest_aspect_label("240") == "2.40"
