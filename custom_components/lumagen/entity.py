"""Base entity for the Lumagen integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LumagenCoordinator


class LumagenBaseEntity(CoordinatorEntity[LumagenCoordinator]):
    """Shared parent for all Lumagen entities.

    Device identity is keyed off the config-entry unique_id (a hash of the
    serialx URL — see :mod:`.config_flow`). Model and firmware are filled
    in as soon as the Lumagen reports them via ``!S01``; until then they
    show as ``None`` in the device registry, which HA handles gracefully.

    ``configuration_url`` is intentionally not set. The URL we'd have to
    offer is the serialx/ESPHome port URL (e.g.
    ``esphome-hass://esphome/<entry>?port_name=Lumagen``), which HA's
    device registry rejects as an invalid URL scheme. The user's gateway
    to this device is the ESPHome integration itself, which is already
    linked via the device registry's ``via_device`` conventions.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: LumagenCoordinator, *, key: str) -> None:
        super().__init__(coordinator)
        unique_base = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{unique_base}_{key}"

        state = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_base)},
            manufacturer=MANUFACTURER,
            model=state.model if state else None,
            sw_version=state.firmware if state else None,
            name=coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        """Mark entities unavailable when the Lumagen stops responding.

        Checks both the coordinator's own availability (transport connected)
        and the client's staleness detection (no response in stale_timeout).
        """
        return super().available and self.coordinator.client.available
