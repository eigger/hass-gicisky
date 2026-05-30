"""Support for Gicisky sensors."""

from __future__ import annotations
from datetime import datetime
from typing import cast
import logging
from .gicisky_ble import SensorDeviceClass as GiciskySensorDeviceClass, SensorUpdate, Units
from homeassistant.util.dt import parse_datetime
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_SW_VERSION,
    ATTR_HW_VERSION,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.sensor import sensor_device_info_to_hass_device_info
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from propcache.api import cached_property

from .coordinator import GiciskyPassiveBluetoothDataProcessor
from .device import device_key_to_bluetooth_entity_key
from .types import GiciskyConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = {
    # Battery (percent)
    (GiciskySensorDeviceClass.BATTERY, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.BATTERY}_{Units.PERCENTAGE}",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Voltage (volt)
    (
        GiciskySensorDeviceClass.VOLTAGE,
        Units.ELECTRIC_POTENTIAL_VOLT,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.VOLTAGE}_{Units.ELECTRIC_POTENTIAL_VOLT}",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Signal Strength (RSSI) (dBm) — added automatically by the bluetooth framework
    (
        GiciskySensorDeviceClass.SIGNAL_STRENGTH,
        Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.SIGNAL_STRENGTH}_{Units.SIGNAL_STRENGTH_DECIBELS_MILLIWATT}",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}

def hass_device_info(sensor_device_info):
    device_info = sensor_device_info_to_hass_device_info(sensor_device_info)
    if sensor_device_info.sw_version is not None:
        device_info[ATTR_SW_VERSION] = sensor_device_info.sw_version
    if sensor_device_info.hw_version is not None:
        device_info[ATTR_HW_VERSION] = sensor_device_info.hw_version
    return device_info
    
def sensor_update_to_bluetooth_data_update(
    sensor_update: SensorUpdate,
) -> PassiveBluetoothDataUpdate[float | None]:
    """Convert a sensor update to a bluetooth data update."""
    return PassiveBluetoothDataUpdate(
        devices={
            device_id: hass_device_info(device_info)
            for device_id, device_info in sensor_update.devices.items()
        },
        entity_descriptions={
            device_key_to_bluetooth_entity_key(device_key): SENSOR_DESCRIPTIONS[
                (description.device_class, description.native_unit_of_measurement)
            ]
            for device_key, description in sensor_update.entity_descriptions.items()
            if description.device_class
        },
        entity_data={
            device_key_to_bluetooth_entity_key(device_key): cast(
                float | None, sensor_values.native_value
            )
            for device_key, sensor_values in sensor_update.entity_values.items()
        },
        entity_names={
            device_key_to_bluetooth_entity_key(device_key): sensor_values.name
            for device_key, sensor_values in sensor_update.entity_values.items()
        },
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiciskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Gicisky BLE sensors."""
    coordinator = entry.runtime_data
    processor = GiciskyPassiveBluetoothDataProcessor(
        sensor_update_to_bluetooth_data_update
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(
            GiciskyBluetoothSensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(
        coordinator.async_register_processor(processor, SensorEntityDescription)
    )

    # Add Duration sensor
    duration_coordinator = hass.data[DOMAIN][entry.entry_id]["duration_coordinator"]
    failure_coordinator = hass.data[DOMAIN][entry.entry_id]["failure_coordinator"]
    last_failure_coordinator = hass.data[DOMAIN][entry.entry_id]["last_failure_coordinator"]
    async_add_entities([
        GiciskyDurationSensorEntity(hass, entry, duration_coordinator),
        GiciskyFailureCountSensorEntity(hass, entry, failure_coordinator),
        GiciskyLastFailureTimeSensorEntity(hass, entry, last_failure_coordinator),
    ])


class GiciskyBluetoothSensorEntity(
    PassiveBluetoothProcessorEntity[GiciskyPassiveBluetoothDataProcessor[float | None]],
    SensorEntity,
):
    """Representation of a Gicisky BLE sensor."""

    @property
    def native_value(self) -> int | float | datetime | None:
        """Return the native value."""
        value = self.processor.entity_data.get(self.entity_key)
        if isinstance(value, str) and parse_datetime(value):
            value = parse_datetime(value)
        return value

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available


class GiciskyDurationSensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[float]],
    SensorEntity,
):
    """Representation of a Gicisky BLE write duration sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "write_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator[float],
    ) -> None:
        """Initialize the duration sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        address = hass.data[DOMAIN][entry.entry_id]["address"]
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_unique_id = f"gicisky_{self._identifier}_write_duration"
        self._native_value: float = 0.0

    @property
    def native_value(self) -> float | None:
        """Return the native value."""
        return self._native_value

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=f"Gicisky {self._identifier}",
            manufacturer="Gicisky",
        )

    @cached_property
    def available(self) -> bool:
        """Entity always available."""
        return True

    @property
    def data(self) -> float:
        """Return coordinator data for this entity."""
        return self.coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Updated duration data: %s", self.data)
        self._native_value = self.data
        super()._handle_coordinator_update()


class GiciskyFailureCountSensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[int]],
    SensorEntity,
):
    """Representation of a Gicisky BLE write failure count sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "failure_count"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:alert-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator[int],
    ) -> None:
        """Initialize the failure count sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        address = hass.data[DOMAIN][entry.entry_id]["address"]
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_unique_id = f"gicisky_{self._identifier}_failure_count"
        self._native_value: int = 0

    @property
    def native_value(self) -> int | None:
        """Return the native value."""
        return self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=f"Gicisky {self._identifier}",
            manufacturer="Gicisky",
        )

    @cached_property
    def available(self) -> bool:
        """Entity always available."""
        return True


class GiciskyLastFailureTimeSensorEntity(
    CoordinatorEntity[DataUpdateCoordinator[datetime | None]],
    SensorEntity,
):
    """Representation of a Gicisky BLE write last failure time sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_failure_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator[datetime | None],
    ) -> None:
        """Initialize the last failure time sensor."""
        CoordinatorEntity.__init__(self, coordinator)
        address = hass.data[DOMAIN][entry.entry_id]["address"]
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_unique_id = f"gicisky_{self._identifier}_last_failure_time"
        self._native_value: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Return the native value."""
        return self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self._address)},
            name=f"Gicisky {self._identifier}",
            manufacturer="Gicisky",
        )

    @cached_property
    def available(self) -> bool:
        """Entity always available."""
        return True

