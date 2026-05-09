"""Constants for the Lumagen Radiance Pro integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "lumagen"
MANUFACTURER: Final = "Lumagen, Inc."

CONF_URL: Final = "url"

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
)

# How long to wait for a device-info response during config-flow validation.
VALIDATION_TIMEOUT: Final = 5.0
