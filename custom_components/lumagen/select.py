"""Select dropdowns for the Lumagen Radiance Pro."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import LumagenClient, LumagenState

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSelectDescription(SelectEntityDescription):
    """Bidirectional select description.

    ``current_fn`` reads the current option label from coordinator state.
    Returning ``None`` means "fall back to the entity's optimistic value"
    (used for write-only knobs like subtitle shift that have no query).

    ``select_fn`` is given the client AND a snapshot of state at write
    time. State access is needed by compound-write commands like
    ``set_sharpness`` that must preserve other components' values.
    """

    current_fn: Callable[[LumagenState], str | None]
    select_fn: Callable[[LumagenClient, LumagenState, str], Awaitable[None]]


# --- Aspect ratio (existing) ---
# Aspect labels match the Lumagen manual. Order matches the old ESPHome YAML
# so existing dashboards/automations don't need re-labeling.
_ASPECT_COMMANDS: dict[str, str] = {
    "4:3": "n",
    "Letterbox": "l",
    "16:9": "w",
    "16:9 NZ": "*",
    "1.85": "j",
    "2.35": "W",
    "2.40": "G",
}


# Best-effort mapping from the Lumagen's !I24 content_aspect value to the
# closest preset label. The Lumagen does not report which preset is
# actually active — only detected content aspect — so when the user
# selects a mismatched preset (e.g. 4:3 on 16:9 content) the display will
# be wrong until they pick another preset. Protocol limitation, not a bug.
_CONTENT_ASPECT_TO_LABEL: tuple[tuple[int, str], ...] = (
    (133, "4:3"),
    (178, "16:9"),
    (185, "1.85"),
    (235, "2.35"),
    (240, "2.40"),
)


# --- Sharpness sensitivity (compound-write — preserves enabled + level) ---
_SHARPNESS_SENSITIVITY_OPTIONS = ("Normal", "High")
_SHARPNESS_SENSITIVITY_TO_WIRE = {"Normal": "N", "High": "H"}
_SHARPNESS_WIRE_TO_LABEL = {v: k for k, v in _SHARPNESS_SENSITIVITY_TO_WIRE.items()}


# --- Subtitle shift (write-only optimistic) ---
_SUBTITLE_SHIFT_OPTIONS = ("Off", "Small", "Large")
_SUBTITLE_SHIFT_TO_LEVEL = {"Off": 0, "Small": 1, "Large": 2}


# --- HDR gamma mode (compound-write — pairs with hdr_mapping_max_nits) ---
# The Lumagen has no documented query for the active mapping values, so
# both halves of the ZY417 compound are tracked optimistically on the
# coordinator. The entity handles read/write directly against that state
# rather than going through select_fn.
_HDR_GAMMA_MODE_OPTIONS = ("Auto", "HDR", "SDR")
_HDR_GAMMA_LABEL_TO_WIRE = {"Auto": "A", "HDR": "H", "SDR": "S"}
_HDR_GAMMA_WIRE_TO_LABEL = {v: k for k, v in _HDR_GAMMA_LABEL_TO_WIRE.items()}


# --- select_fn implementations ---


async def _select_aspect(
    client: LumagenClient, _state: LumagenState, value: str
) -> None:
    cmd = _ASPECT_COMMANDS.get(value)
    if cmd is not None:
        await client.send_command(cmd)


async def _select_memory(
    client: LumagenClient, _state: LumagenState, value: str
) -> None:
    if value in ("A", "B", "C", "D"):
        await client.send_command(value.lower())


async def _select_sharpness_sensitivity(
    client: LumagenClient, state: LumagenState, value: str
) -> None:
    """Compound write: preserve current enabled + level when changing sensitivity."""
    wire = _SHARPNESS_SENSITIVITY_TO_WIRE.get(value)
    if wire is None:
        return
    enabled = state.sharpness_enabled if state.sharpness_enabled is not None else False
    level = state.sharpness_level if state.sharpness_level is not None else 4
    await client.set_sharpness(enabled=enabled, level=level, sensitivity=wire)


async def _select_subtitle_shift(
    client: LumagenClient, _state: LumagenState, value: str
) -> None:
    level = _SUBTITLE_SHIFT_TO_LEVEL.get(value)
    if level is not None:
        await client.set_subtitle_shift(level)


# --- current_fn helpers ---


def _closest_aspect_label(raw: str | None) -> str | None:
    """Return the dropdown label whose target is closest to ``raw``.

    ``raw`` is the Lumagen's !I24 SSS field — zero-padded integer of
    ``aspect * 100`` (e.g. ``178`` for 16:9). Snap to the nearest entry;
    if ``raw`` can't be parsed return ``None`` so the UI shows no selection.
    """
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return min(
        _CONTENT_ASPECT_TO_LABEL,
        key=lambda entry: abs(entry[0] - value),
    )[1]


def _current_sharpness_sensitivity(state: LumagenState) -> str | None:
    if state.sharpness_sensitivity is None:
        return None
    return _SHARPNESS_WIRE_TO_LABEL.get(state.sharpness_sensitivity.value)


# --- Entity descriptors ---


SELECTS: tuple[LumagenSelectDescription, ...] = (
    LumagenSelectDescription(
        key="aspect_select",
        translation_key="aspect_select",
        options=list(_ASPECT_COMMANDS),
        current_fn=lambda s: _closest_aspect_label(s.content_aspect),
        select_fn=_select_aspect,
    ),
    LumagenSelectDescription(
        key="memory_select",
        translation_key="memory_select",
        options=["A", "B", "C", "D"],
        current_fn=lambda s: s.input_memory,
        select_fn=_select_memory,
    ),
    LumagenSelectDescription(
        key="sharpness_sensitivity",
        translation_key="sharpness_sensitivity",
        options=list(_SHARPNESS_SENSITIVITY_OPTIONS),
        entity_category=EntityCategory.CONFIG,
        current_fn=_current_sharpness_sensitivity,
        select_fn=_select_sharpness_sensitivity,
    ),
    LumagenSelectDescription(
        key="subtitle_shift",
        translation_key="subtitle_shift",
        options=list(_SUBTITLE_SHIFT_OPTIONS),
        entity_category=EntityCategory.CONFIG,
        # No query exists; current_fn always returns None and the entity
        # shows the locally-tracked optimistic value instead.
        current_fn=lambda _s: None,
        select_fn=_select_subtitle_shift,
    ),
    LumagenSelectDescription(
        key="hdr_gamma_mode",
        translation_key="hdr_gamma_mode",
        options=list(_HDR_GAMMA_MODE_OPTIONS),
        entity_category=EntityCategory.CONFIG,
        # Read/write goes through coordinator.hdr_mapping_gamma_mode —
        # the entity overrides the dispatch. current_fn / select_fn here
        # are unused for this entry but must be set to satisfy the
        # dataclass contract.
        current_fn=lambda _s: None,
        select_fn=_select_subtitle_shift,  # placeholder; entity overrides
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        LumagenSelect(coordinator, description) for description in SELECTS
    )


class LumagenSelect(LumagenBaseEntity, SelectEntity):
    """Bidirectional Lumagen dropdown.

    Falls back to a locally-tracked optimistic value when ``current_fn``
    returns ``None`` (used for write-only selects like subtitle shift).

    The HDR gamma-mode entry is a special case: the underlying ZY417
    command pairs the gamma byte with a numeric max-nits value. Both
    halves live as optimistic state on the coordinator; this entity
    reads/writes through that shared state.
    """

    entity_description: LumagenSelectDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSelectDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description
        self._optimistic_option: str | None = None

    @property
    def current_option(self) -> str | None:
        if self.entity_description.key == "hdr_gamma_mode":
            wire = self.coordinator.hdr_mapping_gamma_mode
            label = _HDR_GAMMA_WIRE_TO_LABEL.get(wire)
            return label if label in (self.entity_description.options or []) else None
        current = self.entity_description.current_fn(self.coordinator.data)
        options = self.entity_description.options or []
        if current is None:
            return self._optimistic_option if self._optimistic_option in options else None
        return current if current in options else None

    async def async_select_option(self, option: str) -> None:
        if self.entity_description.key == "hdr_gamma_mode":
            wire = _HDR_GAMMA_LABEL_TO_WIRE.get(option)
            if wire is None:
                return
            await self.coordinator.client.set_hdr_intensity_mapping(
                display_max_nits=self.coordinator.hdr_mapping_max_nits,
                gamma_mode=wire,
            )
            self.coordinator.hdr_mapping_gamma_mode = wire
            self.async_write_ha_state()
            return
        await self.entity_description.select_fn(
            self.coordinator.client, self.coordinator.data, option
        )
        self._optimistic_option = option
        self.async_write_ha_state()
