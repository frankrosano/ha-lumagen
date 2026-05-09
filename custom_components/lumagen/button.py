"""Buttons for the Lumagen Radiance Pro — direct command shortcuts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import LumagenClient

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenButtonDescription(ButtonEntityDescription):
    """A button that turns a press into a command on the client."""

    press_fn: Callable[[LumagenClient], Awaitable[None]]


def _cmd(raw: str) -> Callable[[LumagenClient], Awaitable[None]]:
    """Build a press-fn that sends a raw command string (no CR)."""

    async def _send(client: LumagenClient) -> None:
        await client.send_command(raw)

    return _send


async def _save_sequence(client: LumagenClient) -> None:
    """'Save' is a two-byte sequence — S then OK — per the Lumagen RS-232 doc."""
    await client.send_command("S")
    await client.send_command("k")


BUTTONS: tuple[LumagenButtonDescription, ...] = (
    # --- Power ---
    LumagenButtonDescription(key="power_on", translation_key="power_on", press_fn=_cmd("%")),
    LumagenButtonDescription(key="standby", translation_key="standby", press_fn=_cmd("$")),

    # --- OSD navigation ---
    LumagenButtonDescription(key="menu", translation_key="menu", press_fn=_cmd("M")),
    LumagenButtonDescription(key="exit", translation_key="exit", press_fn=_cmd("X")),
    LumagenButtonDescription(key="ok", translation_key="ok", press_fn=_cmd("k")),
    LumagenButtonDescription(key="menu_off", translation_key="menu_off", press_fn=_cmd("!")),
    LumagenButtonDescription(key="up", translation_key="up", press_fn=_cmd("^")),
    LumagenButtonDescription(key="down", translation_key="down", press_fn=_cmd("v")),
    LumagenButtonDescription(key="left", translation_key="left", press_fn=_cmd("<")),
    LumagenButtonDescription(key="right", translation_key="right", press_fn=_cmd(">")),

    # --- Direct inputs 1-8 (+ previous) ---
    LumagenButtonDescription(key="input_1", translation_key="input_1", press_fn=_cmd("i1")),
    LumagenButtonDescription(key="input_2", translation_key="input_2", press_fn=_cmd("i2")),
    LumagenButtonDescription(key="input_3", translation_key="input_3", press_fn=_cmd("i3")),
    LumagenButtonDescription(key="input_4", translation_key="input_4", press_fn=_cmd("i4")),
    LumagenButtonDescription(key="input_5", translation_key="input_5", press_fn=_cmd("i5")),
    LumagenButtonDescription(key="input_6", translation_key="input_6", press_fn=_cmd("i6")),
    LumagenButtonDescription(key="input_7", translation_key="input_7", press_fn=_cmd("i7")),
    LumagenButtonDescription(key="input_8", translation_key="input_8", press_fn=_cmd("i8")),
    LumagenButtonDescription(key="previous_input", translation_key="previous_input",
                             press_fn=_cmd("P")),

    # --- Aspect presets ---
    LumagenButtonDescription(key="aspect_4_3", translation_key="aspect_4_3", press_fn=_cmd("n")),
    LumagenButtonDescription(key="aspect_letterbox", translation_key="aspect_letterbox",
                             press_fn=_cmd("l")),
    LumagenButtonDescription(key="aspect_16_9", translation_key="aspect_16_9", press_fn=_cmd("w")),
    LumagenButtonDescription(key="aspect_16_9_nz", translation_key="aspect_16_9_nz",
                             press_fn=_cmd("*")),
    LumagenButtonDescription(key="aspect_1_85", translation_key="aspect_1_85", press_fn=_cmd("j")),
    LumagenButtonDescription(key="aspect_2_35", translation_key="aspect_2_35", press_fn=_cmd("W")),
    LumagenButtonDescription(key="aspect_2_40", translation_key="aspect_2_40", press_fn=_cmd("G")),
    LumagenButtonDescription(key="auto_aspect_on", translation_key="auto_aspect_on",
                             press_fn=_cmd("~")),
    LumagenButtonDescription(key="auto_aspect_off", translation_key="auto_aspect_off",
                             press_fn=_cmd("V")),

    # --- Memory slots ---
    LumagenButtonDescription(key="memory_a", translation_key="memory_a", press_fn=_cmd("a")),
    LumagenButtonDescription(key="memory_b", translation_key="memory_b", press_fn=_cmd("b")),
    LumagenButtonDescription(key="memory_c", translation_key="memory_c", press_fn=_cmd("c")),
    LumagenButtonDescription(key="memory_d", translation_key="memory_d", press_fn=_cmd("d")),

    # --- Misc ---
    LumagenButtonDescription(key="hdr_setup", translation_key="hdr_setup", press_fn=_cmd("Y")),
    LumagenButtonDescription(key="test_pattern", translation_key="test_pattern",
                             press_fn=_cmd("H")),
    LumagenButtonDescription(key="osd_on", translation_key="osd_on", press_fn=_cmd("g")),
    LumagenButtonDescription(key="osd_off", translation_key="osd_off", press_fn=_cmd("s")),
    LumagenButtonDescription(
        key="save",
        translation_key="save",
        entity_category=EntityCategory.CONFIG,
        press_fn=_save_sequence,
    ),
    LumagenButtonDescription(
        key="query_status",
        translation_key="query_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=lambda c: c.query_full_status(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenButton(coordinator, description) for description in BUTTONS
    )


class LumagenButton(LumagenBaseEntity, ButtonEntity):
    """Fire-and-forget Lumagen remote button."""

    entity_description: LumagenButtonDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenButtonDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator.client)
