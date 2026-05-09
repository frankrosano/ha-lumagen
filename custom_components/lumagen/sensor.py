"""Sensors for the Lumagen Radiance Pro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from pylumagen import Colorspace, HdrStatus, InputStatus, LumagenState, SourceMode

from .coordinator import LumagenConfigEntry
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSensorDescription(SensorEntityDescription):
    """Sensor description with a pull-from-state function."""

    value_fn: Callable[[LumagenState], StateType]


SENSORS: tuple[LumagenSensorDescription, ...] = (
    # --- Diagnostic: always-on identity + firmware ---
    LumagenSensorDescription(
        key="model",
        translation_key="model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.model,
    ),
    LumagenSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.firmware,
    ),
    # --- Primary: what's playing right now ---
    LumagenSensorDescription(
        key="current_input",
        translation_key="current_input",
        value_fn=lambda s: s.current_input,
    ),
    LumagenSensorDescription(
        key="input_memory",
        translation_key="input_memory",
        value_fn=lambda s: s.input_memory,
    ),
    # --- Source characteristics ---
    LumagenSensorDescription(
        key="source_resolution",
        translation_key="source_resolution",
        value_fn=lambda s: s.source_resolution,
    ),
    LumagenSensorDescription(
        key="source_vrate",
        translation_key="source_vrate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: _as_float(s.source_vrate),
    ),
    LumagenSensorDescription(
        key="source_aspect",
        translation_key="source_aspect",
        value_fn=lambda s: s.source_aspect,
    ),
    LumagenSensorDescription(
        key="content_aspect",
        translation_key="content_aspect",
        value_fn=lambda s: s.content_aspect,
    ),
    # --- Output characteristics ---
    LumagenSensorDescription(
        key="output_resolution",
        translation_key="output_resolution",
        value_fn=lambda s: s.output_resolution,
    ),
    LumagenSensorDescription(
        key="output_vrate",
        translation_key="output_vrate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: _as_float(s.output_vrate),
    ),
    # --- Enum-backed status sensors ---
    LumagenSensorDescription(
        key="colorspace",
        translation_key="colorspace",
        device_class=SensorDeviceClass.ENUM,
        options=[cs.value for cs in Colorspace],
        value_fn=lambda s: s.colorspace.value if s.colorspace else None,
    ),
    LumagenSensorDescription(
        key="hdr_status",
        translation_key="hdr_status",
        device_class=SensorDeviceClass.ENUM,
        options=[hs.value for hs in HdrStatus],
        value_fn=lambda s: s.hdr_status.value if s.hdr_status else None,
    ),
    LumagenSensorDescription(
        key="input_status",
        translation_key="input_status",
        device_class=SensorDeviceClass.ENUM,
        options=[ist.value for ist in InputStatus],
        value_fn=lambda s: s.input_status.value if s.input_status else None,
    ),
    LumagenSensorDescription(
        key="source_mode",
        translation_key="source_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[sm.value for sm in SourceMode],
        value_fn=lambda s: s.source_mode.value if s.source_mode else None,
    ),
)


def _as_float(raw: str | None) -> float | None:
    """Parse the Lumagen's vertical-rate strings (``060``, ``1200``) to Hz.

    The Lumagen's ``RRR``/``PPP`` fields are 3-digit right-padded integers
    representing tenths of a hertz on some firmwares and whole hertz on
    others. We pass them through as-is (no tenths division) because the
    tenths form is rare and mixing the two would create false history
    glitches. If it bites us later we'll pin per-firmware.
    """
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenSensor(coordinator, description) for description in SENSORS
    )


class LumagenSensor(LumagenBaseEntity, SensorEntity):
    """Push-driven Lumagen sensor."""

    entity_description: LumagenSensorDescription

    def __init__(
        self,
        coordinator,  # type: ignore[no-untyped-def]
        description: LumagenSensorDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)
