"""Media player for the Lumagen Radiance Pro.

The Lumagen is a video processor between sources and a display — no media
transport, no volume. But its defining control *is* input switching, which is
exactly what a media_player's ``source`` / ``source_list`` model expresses.
Modelling it this way puts power + input on one media card and enables voice
control ("turn on the Lumagen", "set Lumagen source to Input 3").

Only ``TURN_ON`` / ``TURN_OFF`` / ``SELECT_SOURCE`` are advertised, so cards
don't render volume sliders or transport buttons the device can't honor.

Source selection is genuinely bidirectional: unlike aspect (which the Lumagen
never reports as an active preset), the current input *is* reported via
``!I24`` / ``!I25``, so ``source`` reflects real device state rather than an
optimistic guess.

A compact signal-path summary (resolution in/out, refresh rates, HDR,
colorspace) rides along as extra state attributes for an at-a-glance "what's
playing" view on the media card. The authoritative per-field entities remain
the individual sensors; these attributes are a convenience mirror.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity

# This integration surfaces inputs 1-8 (parity with the prior input_select).
# The client accepts 1-19 for models with more physical inputs; an input the
# device reports outside 1-8 simply shows as no current selection.
_INPUT_COUNT = 8
_SOURCE_LIST = [f"Input {n}" for n in range(1, _INPUT_COUNT + 1)]
_SOURCE_TO_NUM = {label: n for n, label in enumerate(_SOURCE_LIST, start=1)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([LumagenMediaPlayer(coordinator)])


class LumagenMediaPlayer(LumagenBaseEntity, MediaPlayerEntity):
    """The Lumagen as an AV source-switcher: power + input selection."""

    # Primary entity for the device, so it takes the device name rather than
    # a "<device> Media player" suffix.
    _attr_name = None
    _attr_source_list = _SOURCE_LIST
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator, key="media_player")

    @property
    def state(self) -> MediaPlayerState | None:
        power_on = self.coordinator.data.power_on
        if power_on is None:
            return None
        # The Lumagen's "off" is really standby (it stays reachable over
        # RS-232), but ON/OFF gives the cleanest power-toggle UX on the media
        # card and maps directly to the % / $ commands.
        return MediaPlayerState.ON if power_on else MediaPlayerState.OFF

    @property
    def source(self) -> str | None:
        raw = self.coordinator.data.current_input
        if raw is None:
            return None
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None
        # Snap to the known label; an input outside 1-8 shows as no selection
        # rather than an out-of-list value the frontend would reject.
        label = f"Input {number}"
        return label if label in _SOURCE_TO_NUM else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        return {
            "source_resolution": state.source_resolution,
            "source_refresh_rate": state.source_vrate,
            "output_resolution": state.output_resolution,
            "output_refresh_rate": state.output_vrate,
            "hdr_status": state.hdr_status.value if state.hdr_status else None,
            "colorspace": state.colorspace.value if state.colorspace else None,
        }

    async def async_turn_on(self) -> None:
        await self.coordinator.client.power_on()

    async def async_turn_off(self) -> None:
        await self.coordinator.client.standby()

    async def async_select_source(self, source: str) -> None:
        number = _SOURCE_TO_NUM.get(source)
        if number is None:
            return
        await self.coordinator.client.set_input(number)
