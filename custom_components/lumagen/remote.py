"""Remote for the Lumagen Radiance Pro.

Exposes the Lumagen's command surface as a Home Assistant ``remote`` entity —
the idiomatic home for OSD navigation (Menu / OK / arrows / Exit) and any
one-shot command, driven from automations via ``remote.send_command``.

``send_command`` accepts friendly command names (see ``_COMMANDS``) and, for
anything not in that map, falls through to sending the token as a raw wire
command. So ``remote.send_command(command="menu")`` and
``remote.send_command(command=["down", "down", "ok"])`` both work, as does a
raw ``remote.send_command(command="i3")``. ``num_repeats`` and ``delay_secs``
are honored, so "press down three times" is a single call.

This mirrors the media_player + remote dual-entity pattern used by Apple TV /
Android TV: the media_player owns power + source, the remote owns command
sending. Power is exposed on both (turn_on/turn_off here map to the same
``%`` / ``$`` commands) so either entity can wake the device.

Raw pass-through sends *without* a carriage return. Commands that require a CR
(most ``ZY…`` calibration commands) should use the ``send_raw_command``
service, which takes an explicit ``cr`` flag — the remote deliberately doesn't
guess at CR handling.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity

# Friendly command name -> Lumagen wire command (no CR). Mirrors the command
# tables in pylumagen's commands.py / Tip0011. Anything not listed here is
# sent verbatim, so the remote doubles as an escape hatch for one-shot
# commands the integration doesn't name (CR-terminated commands excepted —
# use the send_raw_command service for those).
_COMMANDS: dict[str, str] = {
    # Power
    "power_on": "%",
    "standby": "$",
    # OSD navigation
    "menu": "M",
    "exit": "X",
    "ok": "k",
    "menu_off": "!",
    "up": "^",
    "down": "v",
    "left": "<",
    "right": ">",
    # Direct inputs
    "input_1": "i1",
    "input_2": "i2",
    "input_3": "i3",
    "input_4": "i4",
    "input_5": "i5",
    "input_6": "i6",
    "input_7": "i7",
    "input_8": "i8",
    "previous_input": "P",
    # Aspect ratio
    "aspect_4_3": "n",
    "aspect_letterbox": "l",
    "aspect_16_9": "w",
    "aspect_16_9_nz": "*",
    "aspect_1_85": "j",
    "aspect_2_35": "W",
    "aspect_2_40": "G",
    "auto_aspect_on": "~",
    "auto_aspect_off": "V",
    # Memory
    "memory_a": "a",
    "memory_b": "b",
    "memory_c": "c",
    "memory_d": "d",
    # Misc
    "hdr_setup": "Y",
    "test_pattern": "H",
    "osd_on": "g",
    "osd_off": "s",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([LumagenRemote(coordinator)])


class LumagenRemote(LumagenBaseEntity, RemoteEntity):
    """Lumagen command sender: OSD navigation + arbitrary command passthrough."""

    # Like media_player, this represents the device itself (dual-entity
    # pattern), so it takes the device name rather than a suffix.
    _attr_name = None

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator, key="remote")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.standby()

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        num_repeats: int = kwargs.get(ATTR_NUM_REPEATS, DEFAULT_NUM_REPEATS)
        delay: float = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        # Resolve friendly names once; unknown tokens pass through as raw
        # wire commands.
        wire_commands = [_COMMANDS.get(token, token) for token in command]
        for repeat in range(num_repeats):
            for index, wire in enumerate(wire_commands):
                await self.coordinator.client.send_command(wire)
                is_last = (
                    repeat == num_repeats - 1 and index == len(wire_commands) - 1
                )
                if delay and not is_last:
                    await asyncio.sleep(delay)
