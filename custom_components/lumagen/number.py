"""Number entities for the Lumagen Radiance Pro.

* **Sharpness level** (0-7) — read from ``state.sharpness_level``,
  written via ``set_sharpness`` which preserves the current ``enabled``
  and ``sensitivity`` values. Defaults to ``enabled=False, sensitivity="N"``
  if those haven't been observed yet (the slider on its own doesn't
  imply sharpening should be on).
* **Fan speed** (0-9) — write-only. The Lumagen has no documented query
  for fan speed, so the slider tracks the last value we sent rather
  than the device's authoritative state. Optimistic UX: user sets 3,
  slider stays at 3, even though we can't independently verify.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import LumagenClient, LumagenState

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenNumberDescription(NumberEntityDescription):
    """Number description with a value-from-state and a writer.

    ``value_fn`` may return None for write-only knobs that have no
    corresponding query; the entity falls back to a locally-tracked
    "last set" value in that case.
    """

    value_fn: Callable[[LumagenState], int | None]
    set_fn: Callable[[LumagenClient, LumagenState, int], Awaitable[None]]


async def _set_sharpness_level(
    client: LumagenClient, state: LumagenState, level: int
) -> None:
    """Set the sharpness level, preserving the current enabled + sensitivity."""
    enabled = state.sharpness_enabled if state.sharpness_enabled is not None else False
    sensitivity = (
        state.sharpness_sensitivity.value
        if state.sharpness_sensitivity is not None
        else "N"
    )
    await client.set_sharpness(enabled=enabled, level=level, sensitivity=sensitivity)


async def _set_fan_speed(
    client: LumagenClient, _state: LumagenState, level: int
) -> None:
    await client.set_fan_speed(level)


NUMBERS: tuple[LumagenNumberDescription, ...] = (
    LumagenNumberDescription(
        key="sharpness_level",
        translation_key="sharpness_level",
        native_min_value=0,
        native_max_value=7,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda s: s.sharpness_level,
        set_fn=_set_sharpness_level,
    ),
    LumagenNumberDescription(
        key="fan_speed",
        translation_key="fan_speed",
        native_min_value=0,
        native_max_value=9,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        # No query for fan speed — value_fn always returns None and we
        # fall back to the locally-tracked last-set value in the entity.
        value_fn=lambda _s: None,
        set_fn=_set_fan_speed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenNumber(coordinator, description) for description in NUMBERS
    )


class LumagenNumber(LumagenBaseEntity, NumberEntity):
    """Bidirectional number backed by pylumagen state + setter."""

    entity_description: LumagenNumberDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenNumberDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description
        # Local fallback for write-only knobs (fan speed). Stays None
        # until the user changes it, at which point we display what they set.
        self._optimistic_value: int | None = None

    @property
    def native_value(self) -> int | None:
        from_state = self.entity_description.value_fn(self.coordinator.data)
        if from_state is not None:
            return from_state
        return self._optimistic_value

    async def async_set_native_value(self, value: float) -> None:
        level = int(value)
        await self.entity_description.set_fn(
            self.coordinator.client, self.coordinator.data, level
        )
        # Track locally so the slider doesn't snap back when value_fn returns None.
        self._optimistic_value = level
        self.async_write_ha_state()
