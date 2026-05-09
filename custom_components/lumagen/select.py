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


# Best-effort mapping from the Lumagen's `!I24` content_aspect value
# (a zero-padded integer representing aspect * 100, e.g. 178, 235) to
# the closest preset label in the dropdown. The Lumagen does not
# report which preset is actually active — only the detected content
# aspect — so when the user selects a preset that doesn't match the
# source (e.g. 4:3 on 16:9 content) the display will be wrong until
# they pick another preset. That's a protocol limitation, not a bug.
_CONTENT_ASPECT_TO_LABEL: tuple[tuple[int, str], ...] = (
    (133, "4:3"),       # 1.33
    (178, "16:9"),      # 1.78
    (185, "1.85"),      # 1.85
    (235, "2.35"),      # 2.35
    (240, "2.40"),      # 2.40
)


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
        # The Lumagen doesn't report which aspect *preset* is selected,
        # only the detected content aspect. Map the content aspect to the
        # nearest preset label as a best-effort display. Will be wrong
        # when the user intentionally picks a mismatched preset (e.g. 4:3
        # on 16:9 content) until they pick another preset.
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
)


def _strip_zeros(raw: str | None) -> str | None:
    """The Lumagen reports inputs as zero-padded ("03"); strip for display."""
    if raw is None:
        return None
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return raw


def _closest_aspect_label(raw: str | None) -> str | None:
    """Return the dropdown label whose target is closest to ``raw``.

    ``raw`` is the Lumagen's `!I24` ``SSS`` field — a zero-padded integer
    representing ``aspect * 100`` (e.g. ``178`` for 16:9). We snap to the
    nearest entry in ``_CONTENT_ASPECT_TO_LABEL``; if ``raw`` can't be
    parsed we return ``None`` so the UI shows no selection.
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
