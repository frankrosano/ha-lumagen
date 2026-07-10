"""Switches for the Lumagen Radiance Pro.

Three switches today:

* **Sharpness enabled** — toggles the Lumagen's edge-enhancement on/off.
  The underlying ``ZY521ELS`` command is compound (enabled + level +
  sensitivity), so flipping this switch reads the *current* level and
  sensitivity from coordinator state and writes them back unchanged
  alongside the new enabled bit. If level/sensitivity haven't been
  observed yet (e.g. first boot before ``ZQI30`` lands), we fall back to
  ``level=4`` and ``sensitivity="N"`` — sensible defaults that won't
  surprise the user.
* **Game mode** — single-bit ``ZY551X`` toggle, no compound write needed.
* **Auto aspect detection** — toggles the Lumagen's automatic aspect-ratio
  detection (``~`` on / ``V`` off). Unlike game mode it has no dedicated
  ``set_*`` wrapper on the client, so the write goes through
  ``send_command`` followed by a ``ZQI54`` re-query — auto-aspect isn't
  part of the Full v5 push stream, so state has to be pulled back. This
  replaces the old on/off buttons + read-only binary sensor with a single
  stateful control.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import Aspect, LumagenClient, LumagenState

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSwitchDescription(SwitchEntityDescription):
    """Switch description with a value-from-state and an on/off writer."""

    value_fn: Callable[[LumagenState], bool | None]
    set_fn: Callable[[LumagenClient, LumagenState, bool], Awaitable[None]]


async def _set_sharpness_enabled(
    client: LumagenClient, state: LumagenState, enabled: bool
) -> None:
    """Toggle sharpness while preserving level and sensitivity."""
    level = state.sharpness_level if state.sharpness_level is not None else 4
    sensitivity = (
        state.sharpness_sensitivity.value
        if state.sharpness_sensitivity is not None
        else "N"
    )
    await client.set_sharpness(enabled=enabled, level=level, sensitivity=sensitivity)


async def _set_game_mode(
    client: LumagenClient, _state: LumagenState, enabled: bool
) -> None:
    await client.set_game_mode(enabled)


async def _set_auto_aspect(
    client: LumagenClient, _state: LumagenState, enabled: bool
) -> None:
    """Toggle automatic aspect detection, then re-query to confirm.

    There's no ``client.set_auto_aspect`` wrapper (the on/off commands are
    the same ``~``/``V`` aspect commands the client exposes generically),
    so this sends the raw command and follows with ``ZQI54`` to pull the
    result back into ``state.auto_aspect`` — auto-aspect isn't part of the
    Full v5 push stream. Mirrors the write-then-query shape of
    ``client.set_game_mode``. ``refresh=False`` because the ``ZQI54`` below
    is the deliberate refresh.
    """
    await client.send_command(
        Aspect.AUTO_ENABLE.value if enabled else Aspect.AUTO_DISABLE.value,
        refresh=False,
    )
    await client.query_auto_aspect()


SWITCHES: tuple[LumagenSwitchDescription, ...] = (
    LumagenSwitchDescription(
        key="sharpness_enabled",
        translation_key="sharpness_enabled",
        value_fn=lambda s: s.sharpness_enabled,
        set_fn=_set_sharpness_enabled,
    ),
    LumagenSwitchDescription(
        key="game_mode",
        translation_key="game_mode",
        value_fn=lambda s: s.game_mode,
        set_fn=_set_game_mode,
    ),
    LumagenSwitchDescription(
        key="auto_aspect",
        translation_key="auto_aspect",
        value_fn=lambda s: s.auto_aspect,
        set_fn=_set_auto_aspect,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenSwitch(coordinator, description) for description in SWITCHES
    )


class LumagenSwitch(LumagenBaseEntity, SwitchEntity):
    """Bidirectional switch backed by a pylumagen state field + setter."""

    entity_description: LumagenSwitchDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSwitchDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.entity_description.set_fn(
            self.coordinator.client, self.coordinator.data, True
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.entity_description.set_fn(
            self.coordinator.client, self.coordinator.data, False
        )
