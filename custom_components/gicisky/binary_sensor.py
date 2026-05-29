"""Support for Gicisky binary sensors."""

from __future__ import annotations
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from propcache.api import cached_property
from .types import GiciskyConfigEntry
from .const import (
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiciskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Gicisky BLE binary sensors."""
    connectivity_coordinator = hass.data[DOMAIN][entry.entry_id]["connectivity_coordinator"]
    image_coordinator = hass.data[DOMAIN][entry.entry_id]["image_coordinator"]
    preview_coordinator = hass.data[DOMAIN][entry.entry_id]["preview_coordinator"]
    async_add_entities([
        GiciskyBluetoothConnectivitySensorEntity(hass, entry, connectivity_coordinator),
        GiciskyDisplayInSyncBinarySensor(hass, entry, image_coordinator, preview_coordinator),
    ])

class GiciskyBluetoothConnectivitySensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[bool]],
    BinarySensorEntity,
):
    _attr_has_entity_name = True
    _attr_translation_key = "connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: DataUpdateCoordinator[bool]):
        CoordinatorEntity.__init__(self, coordinator)
        # self.hass = hass
        address = hass.data[DOMAIN][entry.entry_id]['address']
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_unique_id = f"gicisky_{self._identifier}_connectivity"
        self._is_on = False

    """Representation of a Gicisky binary sensor."""
    @property
    def is_on(self) -> bool | None:
        """Return the native value."""
        return self._is_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo (
            connections = {
                (
                    CONNECTION_BLUETOOTH,
                    self._address,
                )
            },
            name = f"Gicisky {self._identifier}",
            manufacturer = "Gicisky",
        )
    
    @cached_property
    def available(self) -> bool:
        """Entity always either data or empty."""
        return True
    
    @property
    def data(self) -> bytes:
        """Return coordinator data for this entity."""
        return self.coordinator.data
            

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Updated binary data")
        self._is_on = self.data
        super()._handle_coordinator_update()


class GiciskyDisplayInSyncBinarySensor(
    CoordinatorEntity[DataUpdateCoordinator[bytes | None]],
    BinarySensorEntity,
):
    _attr_has_entity_name = True
    _attr_translation_key = "display_in_sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        image_coordinator: DataUpdateCoordinator[bytes | None],
        preview_coordinator: DataUpdateCoordinator[bytes | None],
    ):
        CoordinatorEntity.__init__(self, image_coordinator)
        self._preview_coordinator = preview_coordinator
        address = hass.data[DOMAIN][entry.entry_id]["address"]
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_unique_id = f"gicisky_{self._identifier}_display_in_sync"

    @property
    def is_on(self) -> bool | None:
        img = self.coordinator.data
        pre = self._preview_coordinator.data
        if img is None or pre is None:
            return None
        return img == pre

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=f"Gicisky {self._identifier}",
            manufacturer="Gicisky",
        )

    @cached_property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._preview_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )