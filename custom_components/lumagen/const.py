"""Constants for the Lumagen Radiance Pro integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "lumagen"
MANUFACTURER: Final = "Lumagen, Inc."

CONF_URL: Final = "url"

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
