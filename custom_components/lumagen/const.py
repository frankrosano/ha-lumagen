"""Constants for the Lumagen Radiance Pro integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "lumagen"
MANUFACTURER: Final = "Lumagen, Inc."

CONF_URL: Final = "url"

# How often pylumagen polls the device, in seconds. Most state arrives via
# the Lumagen's Full v5 push (`!I25`) in real time, but a handful of fields
# — sharpness, game mode, auto aspect, display Rec.2020 and source HDR
# metadata — are never pushed; the device only answers explicit queries for
# them. Those fields therefore lag by up to one poll interval when changed
# from the front-panel remote, which is why this is worth tuning.
#
# Lower = snappier, at the cost of more traffic on a 9600-baud link. The
# floor of 5s keeps a poll cycle comfortably shorter than the round trip
# for the five secondary queries plus their replies.
CONF_POLL_INTERVAL: Final = "poll_interval"
DEFAULT_POLL_INTERVAL: Final = 60
MIN_POLL_INTERVAL: Final = 5
MAX_POLL_INTERVAL: Final = 600

# Service for power-user / advanced workflows: send any RS-232 string at the
# Lumagen and let the protocol parser feed unsolicited responses back into
# state. Useful for commands the integration doesn't expose as entities
# (e.g. ZY540-548 HDR test-pattern info frames during calibration).
SERVICE_SEND_RAW_COMMAND: Final = "send_raw_command"
ATTR_COMMAND: Final = "command"
ATTR_CR: Final = "cr"

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
)

# How long to wait for a device-info response during config-flow validation.
VALIDATION_TIMEOUT: Final = 5.0
