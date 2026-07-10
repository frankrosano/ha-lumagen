"""Tests for the remote entity.

The remote is the Lumagen's command surface: friendly OSD-navigation names
(and any other named command) resolve to wire commands, and unknown tokens
pass through verbatim as raw commands. Power maps to the same %/$ commands as
the media_player (dual-entity pattern).

These pin the name->wire mapping, raw pass-through, repeat/delay handling, and
power dispatch. Entities are built with ``__new__`` (no real HASS), matching
test_media_player.py / test_switch_number_select.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pylumagen import LumagenState

from custom_components.lumagen.remote import _COMMANDS, LumagenRemote


def _remote(power_on: bool | None = None) -> tuple[LumagenRemote, MagicMock]:
    """Build a LumagenRemote wired to a stub coordinator + AsyncMock client."""
    client = MagicMock()
    client.power_on = AsyncMock()
    client.standby = AsyncMock()
    client.send_command = AsyncMock()

    coordinator = MagicMock()
    coordinator.data = LumagenState(power_on=power_on)
    coordinator.client = client

    entity = LumagenRemote.__new__(LumagenRemote)
    entity.coordinator = coordinator
    return entity, client


def _sent(client: MagicMock) -> list[str]:
    """Flatten the ordered list of wire commands sent to the client."""
    return [call.args[0] for call in client.send_command.await_args_list]


# ---------- power (is_on / turn_on / turn_off) ----------


@pytest.mark.parametrize(
    ("power_on", "expected"),
    [(True, True), (False, False), (None, None)],
)
def test_is_on_from_power(power_on: bool | None, expected: bool | None) -> None:
    entity, _ = _remote(power_on)
    assert entity.is_on == expected


async def test_turn_on_dispatches_power_on() -> None:
    entity, client = _remote()
    await entity.async_turn_on()
    client.power_on.assert_awaited_once_with()


async def test_turn_off_dispatches_standby() -> None:
    entity, client = _remote()
    await entity.async_turn_off()
    client.standby.assert_awaited_once_with()


# ---------- send_command mapping ----------


async def test_send_command_friendly_name_maps_to_wire() -> None:
    entity, client = _remote()
    await entity.async_send_command(["menu"], delay_secs=0)
    client.send_command.assert_awaited_once_with("M")


async def test_send_command_sequence_preserves_order() -> None:
    entity, client = _remote()
    await entity.async_send_command(["down", "down", "ok"], delay_secs=0)
    assert _sent(client) == ["v", "v", "k"]


async def test_send_command_raw_passthrough() -> None:
    """Tokens not in the map are sent verbatim (raw wire commands)."""
    entity, client = _remote()
    await entity.async_send_command(["i3", "ZY550"], delay_secs=0)
    assert _sent(client) == ["i3", "ZY550"]


async def test_send_command_num_repeats() -> None:
    entity, client = _remote()
    await entity.async_send_command(["ok"], num_repeats=3, delay_secs=0)
    assert _sent(client) == ["k", "k", "k"]


async def test_send_command_delays_between_but_not_after_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """delay_secs sleeps between sends, never after the final one."""
    entity, _ = _remote()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "custom_components.lumagen.remote.asyncio.sleep", sleep_mock
    )

    # 3 commands with the default delay -> 2 inter-command sleeps.
    await entity.async_send_command(["up", "down", "ok"])

    assert sleep_mock.await_count == 2
    sleep_mock.assert_awaited_with(0.4)


# ---------- command vocabulary sanity ----------


def test_osd_nav_commands_map_to_expected_wire() -> None:
    """The OSD-nav vocabulary (the remote's primary purpose) must be exact."""
    assert _COMMANDS["menu"] == "M"
    assert _COMMANDS["exit"] == "X"
    assert _COMMANDS["ok"] == "k"
    assert _COMMANDS["menu_off"] == "!"
    assert _COMMANDS["up"] == "^"
    assert _COMMANDS["down"] == "v"
    assert _COMMANDS["left"] == "<"
    assert _COMMANDS["right"] == ">"
