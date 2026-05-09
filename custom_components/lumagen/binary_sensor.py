"""Binary sensors for the Lumagen Radiance Pro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import LumagenState

from .coordinator import LumagenConfigEntry
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenBinarySensorDescription(BinarySensorEntityDescription):
    """Entity description that picks its bool off ``LumagenState``."""

    value_fn: Callable[[LumagenState], bool | None]


BINARY_SENSORS: tuple[LumagenBinarySensorDescription, ...] = (
    LumagenBinarySensorDescription(
        key="power",
        translation_key="power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda s: s.power_on,
    ),
    LumagenBinarySensorDescription(
        key="is_hdr",
        translation_key="is_hdr",
        value_fn=lambda s: s.is_hdr,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
    )


class LumagenBinarySensor(LumagenBaseEntity, BinarySensorEntity):
    """Push-driven Lumagen binary sensor."""

    entity_description: LumagenBinarySensorDescription

    def __init__(
        self,
        coordinator,  # type: ignore[no-untyped-def]
        description: LumagenBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
