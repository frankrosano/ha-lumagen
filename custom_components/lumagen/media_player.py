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

The Lumagen isn't "playing media" itself, but it *does* report live
statistics about the signal passing through it. We surface that on the media
card the way any player surfaces "now playing": the source->output signal
path is mapped onto ``media_title`` (the card's bold primary line) and the
HDR/colorspace summary onto ``app_name`` (which the frontend's
``computeMediaDescription`` renders as the secondary line when
``media_content_type`` is left unset). Both are gated on power so a stale
signal path never lingers on the card when the device is in standby.

The same fields also ride along as extra state attributes — that's the
full, unformatted mirror shown in the more-info dialog. The authoritative
per-field entities remain the individual sensors; the card fields and
attributes here are a convenience view.
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


def _fmt_rate(rate: str | None) -> str | None:
    """Normalize a Lumagen vertical-rate string (``060``) to a bare Hz number.

    Mirrors the sensor's parsing intent: strip the zero-padding but do not
    divide by ten (the tenths-of-a-hertz firmware variant is rare — see
    ``sensor._as_float``). Returns ``None`` for missing/unparseable input.
    """
    if not rate:
        return None
    try:
        return str(int(rate))
    except (TypeError, ValueError):
        return rate


def _format_signal(resolution: str | None, rate: str | None) -> str | None:
    """Combine a resolution + refresh rate into one label, e.g. ``1080p60``.

    Degrades gracefully: resolution alone -> ``1080p``; rate alone ->
    ``60Hz``; neither -> ``None``.
    """
    rate_fmt = _fmt_rate(rate)
    if resolution and rate_fmt:
        return f"{resolution}{rate_fmt}"
    if resolution:
        return resolution
    if rate_fmt:
        return f"{rate_fmt}Hz"
    return None


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

    # --- Card-facing "now playing" view -------------------------------------
    # These map the live signal path onto the media card's own text lines so
    # it shows on the card face, not just the more-info attributes. Gated on
    # power: in standby we report nothing rather than a stale path. We
    # deliberately leave media_content_type unset so the frontend's
    # computeMediaDescription renders app_name as the secondary line.

    @property
    def media_title(self) -> str | None:
        """Primary card line: the source -> output signal path."""
        state = self.coordinator.data
        if not state.power_on:
            return None
        source = _format_signal(state.source_resolution, state.source_vrate)
        output = _format_signal(state.output_resolution, state.output_vrate)
        if source and output:
            return f"{source} → {output}"
        return source or output

    @property
    def app_name(self) -> str | None:
        """Secondary card line: dynamic range + colorspace, e.g. ``HDR · Rec.2020``."""
        state = self.coordinator.data
        if not state.power_on:
            return None
        parts = [value.value for value in (state.hdr_status, state.colorspace) if value is not None]
        return " · ".join(parts) if parts else None

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
