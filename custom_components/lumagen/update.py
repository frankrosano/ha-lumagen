"""Firmware update entity for the Lumagen Radiance Pro.

Availability of an update comes from comparing revisions — the device's
``!S01`` firmware against the newest listing on lumagen.com for the chosen
channel — not from :func:`aiolumagen.firmware.plan_update`, which needs a
live session and always writes section 0. The plan is still computed, inside
the install, where it decides whether section 1 is written.
"""

from __future__ import annotations

import logging
from typing import Any

from aiolumagen.firmware import (
    RELEASES_URL,
    FirmwareRevision,
    ReleaseListing,
    UpdatePhase,
    UpdateProgress,
)
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import firmware as _firmware
from .const import DOMAIN
from .coordinator import LumagenConfigEntry, LumagenCoordinator
from .entity import LumagenBaseEntity
from .release_coordinator import LumagenReleaseCoordinator, channel_for

_LOGGER = logging.getLogger(__name__)

# Phases whose byte counts are meaningful as a percentage. The fraction covers
# one phase of one section, so the bar restarts per section — the library has
# no overall total, and inferring one would duplicate its flash map here.
_PERCENT_PHASES = frozenset({UpdatePhase.ERASING, UpdatePhase.WRITING})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LumagenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LumagenFirmwareUpdateEntity(entry.runtime_data)])


class LumagenFirmwareUpdateEntity(LumagenBaseEntity, UpdateEntity):
    """Offers and installs Radiance Pro firmware from lumagen.com."""

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    # Set explicitly: HA derives CONFIG vs DIAGNOSTIC from whether INSTALL is
    # supported, and a derived category would flip if that ever changed.
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_release_url = RELEASES_URL

    def __init__(self, coordinator: LumagenCoordinator) -> None:
        super().__init__(coordinator, key="firmware_update")
        self._channel = channel_for(coordinator.config_entry)
        self._last_firmware: str | None = coordinator.data.firmware if coordinator.data else None
        self._progress_key: tuple[UpdatePhase, int | None] | None = None

    @property
    def _releases(self) -> LumagenReleaseCoordinator:
        releases = self.coordinator.release_coordinator
        assert releases is not None  # assigned in async_setup_entry before platforms load
        return releases

    @property
    def _listing(self) -> ReleaseListing | None:
        return self._releases.latest_for(self._channel)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        releases = self._releases
        self.async_on_remove(releases.async_add_listener(self._handle_release_update))
        # The first check happens here, not at entry setup: the website must
        # never delay setup, and a disabled entity never gets this far.
        if not releases.has_data:
            self.hass.async_create_background_task(
                releases.async_request_refresh(),
                name=f"{DOMAIN} firmware release check",
            )

    @callback
    def _handle_release_update(self) -> None:
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        # The device page's sw_version is only set when entities are built,
        # so keep it current across a firmware update ourselves.
        firmware = self.coordinator.data.firmware if self.coordinator.data else None
        if firmware is not None and firmware != self._last_firmware:
            self._last_firmware = firmware
            if self.device_entry is not None:
                dr.async_get(self.hass).async_update_device(
                    self.device_entry.id, sw_version=firmware
                )
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Stay visible through an install, and through a failed release check.

        During an install every other entity is gated off, but this one carries
        the progress. A failed release check keeps the last known version rather
        than hiding the entity, so ``last_update_success`` is ignored.
        """
        if self.coordinator.firmware_update_active:
            return True
        return super().available

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.firmware if self.coordinator.data else None

    @property
    def latest_version(self) -> str | None:
        listing = self._listing
        return listing.revision.mmddyy if listing else None

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        """Compare MMDDYY revisions chronologically.

        HA's default reads them as numbers, which puts 120325 after 030326. If
        either side doesn't parse, say "not newer" rather than nag.
        """
        latest = FirmwareRevision.parse(latest_version)
        installed = FirmwareRevision.parse(installed_version)
        if latest is None or installed is None:
            return False
        return latest > installed

    @property
    def release_summary(self) -> str | None:
        listing = self._listing
        if listing is None or not listing.notes:
            return None
        return listing.notes[:255]

    async def async_release_notes(self) -> str | None:
        listing = self._listing
        if listing is None:
            return None
        heading = " ".join(part for part in (listing.label, listing.revision.mmddyy) if part)
        lines = [f"**{heading}**"]
        if listing.posted is not None:
            lines.append(f"Posted {listing.posted.isoformat()}")
        if listing.notes:
            lines.extend(("", listing.notes))
        if listing.est_minutes is not None:
            lines.extend(("", f"Update time ~{listing.est_minutes} minutes at 230k."))
        return "\n".join(lines)

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        if version is not None:
            # Without SPECIFIC_VERSION HA never passes one; refuse rather than
            # quietly install something else.
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="firmware_no_release"
            )
        listing = self._listing
        if listing is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="firmware_no_release"
            )
        installed = self.installed_version
        # HA's install service only refuses latest == installed; it would
        # happily "update" to an older production release. Guard downgrades.
        if installed is None or not self.version_is_newer(listing.revision.mmddyy, installed):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="firmware_not_newer"
            )

        self._attr_in_progress = True
        self._attr_update_percentage = None
        self._progress_key = None
        self.async_write_ha_state()
        try:
            result, power = await _firmware.async_install_firmware(
                self.hass, self.coordinator, listing, progress=self._on_progress
            )
            await _firmware.async_notify_install_complete(
                self.hass, self.coordinator, listing.revision.mmddyy, result, power
            )
        finally:
            self._attr_update_percentage = None
            self._progress_key = None

    @callback
    def _on_progress(self, progress: UpdateProgress) -> None:
        """Library progress callback; runs on the event loop inside the session."""
        fraction = progress.fraction
        pct = (
            round(fraction * 100)
            if progress.phase in _PERCENT_PHASES and fraction is not None
            else None
        )
        _LOGGER.debug("Firmware %s: %s", progress.phase, progress.message)
        key = (progress.phase, pct)
        if key == self._progress_key:
            return
        self._progress_key = key
        self._attr_update_percentage = pct
        self.async_write_ha_state()
