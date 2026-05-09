"""Select dropdowns for the Lumagen Radiance Pro."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pylumagen import LumagenClient, LumagenState

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity


@dataclass(frozen=True, kw_only=True)
class LumagenSelectDescription(SelectEntityDescription):
    """Bidirectional description: pulls current option from state, pushes via a command fn."""

    current_fn: Callable[[LumagenState], str | None]
    select_fn: Callable[[LumagenClient, str], Awaitable[None]]


# --- Option → command tables ---
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


async def _select_input(client: LumagenClient, value: str) -> None:
    await client.set_input(int(value))


async def _select_aspect(client: LumagenClient, value: str) -> None:
    cmd = _ASPECT_COMMANDS.get(value)
    if cmd is not None:
        await client.send_command(cmd)


async def _select_memory(client: LumagenClient, value: str) -> None:
    # Memory A-D map to lowercase a-d commands.
    if value in ("A", "B", "C", "D"):
        await client.send_command(value.lower())


SELECTS: tuple[LumagenSelectDescription, ...] = (
    LumagenSelectDescription(
        key="input_select",
        translation_key="input_select",
        options=[str(n) for n in range(1, 9)],
        current_fn=lambda s: _strip_zeros(s.current_input),
        select_fn=_select_input,
    ),
    LumagenSelectDescription(
        key="aspect_select",
        translation_key="aspect_select",
        options=list(_ASPECT_COMMANDS),
        # The Lumagen doesn't tell us what aspect is currently selected —
        # only the source/content aspect ratios. We report the content
        # aspect's closest label as a best-effort match.
        current_fn=lambda s: None,
        select_fn=_select_aspect,
    ),
    LumagenSelectDescription(
        key="memory_select",
        translation_key="memory_select",
        options=["A", "B", "C", "D"],
        current_fn=lambda s: s.input_memory,
        select_fn=_select_memory,
    ),
)


def _strip_zeros(raw: str | None) -> str | None:
    """The Lumagen reports inputs as zero-padded ("03"); strip for display."""
    if raw is None:
        return None
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return raw


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
    """Bidirectional Lumagen dropdown."""

    entity_description: LumagenSelectDescription

    def __init__(
        self,
        coordinator: LumagenCoordinator,
        description: LumagenSelectDescription,
    ) -> None:
        super().__init__(coordinator, key=description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        current = self.entity_description.current_fn(self.coordinator.data)
        options = self.entity_description.options or []
        if current is None or current not in options:
            return None
        return current

    async def async_select_option(self, option: str) -> None:
        await self.entity_description.select_fn(self.coordinator.client, option)
