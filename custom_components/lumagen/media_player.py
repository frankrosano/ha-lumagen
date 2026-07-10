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

# This integration surfaces inputs 1-8. The client accepts 1-19 for models
# with more physical inputs; an input the device reports outside 1-8 simply
# shows as no current selection.
#
# Source names come from the Lumagen's configured input labels
# (state.input_labels, populated by pylumagen's query_input_labels). Until
# those land — or for any input the device didn't label — we fall back to
# "Input N". source_list and the reverse label->input lookup are derived from
# coordinator state on each read, so a relabel (or the first label arrival)
# shows up without recreating the entity.
_INPUT_COUNT = 8


def _fallback_label(number: int) -> str:
    """Default display name for input ``number`` when no configured label exists."""
    return f"Input {number}"


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

    def _label_for(self, number: int) -> str:
        """Configured label for input ``number``, or the ``Input N`` fallback.

        An empty configured label (user cleared it) is treated as "no label"
        so the source never renders blank.
        """
        return self.coordinator.data.input_labels.get(number) or _fallback_label(number)

    @property
    def source_list(self) -> list[str]:
        return [self._label_for(n) for n in range(1, _INPUT_COUNT + 1)]

    @property
    def source(self) -> str | None:
        raw = self.coordinator.data.current_input
        if raw is None:
            return None
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None
        if not 1 <= number <= _INPUT_COUNT:
            # Inputs outside the surfaced range show as no selection rather
            # than an out-of-list value the frontend would reject.
            return None
        return self._label_for(number)

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
        # Resolve against the same _label_for used to build source_list, so a
        # configured label and its "Input N" fallback both match. First match
        # wins if two inputs happen to share a label.
        for number in range(1, _INPUT_COUNT + 1):
            if self._label_for(number) == source:
                await self.coordinator.client.set_input(number)
                return
        # Unknown source label — no-op.
