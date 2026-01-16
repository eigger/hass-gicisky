"""Support for Gicisky sensors."""

from __future__ import annotations
from datetime import datetime
from typing import cast
import logging
from .gicisky_ble import SensorDeviceClass as GiciskySensorDeviceClass, SensorUpdate, Units
from .gicisky_ble.const import (
    ExtendedSensorDeviceClass as GiciskyExtendedSensorDeviceClass,
)
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
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfConductivity,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
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
    # Acceleration (m/s²)
    (
        GiciskySensorDeviceClass.ACCELERATION,
        Units.ACCELERATION_METERS_PER_SQUARE_SECOND,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.ACCELERATION}_{Units.ACCELERATION_METERS_PER_SQUARE_SECOND}",
        native_unit_of_measurement=Units.ACCELERATION_METERS_PER_SQUARE_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Battery (percent)
    (GiciskySensorDeviceClass.BATTERY, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.BATTERY}_{Units.PERCENTAGE}",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Channel (-)
    (GiciskyExtendedSensorDeviceClass.CHANNEL, None): SensorEntityDescription(
        key=str(GiciskyExtendedSensorDeviceClass.CHANNEL),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Conductivity (µS/cm)
    (
        GiciskySensorDeviceClass.CONDUCTIVITY,
        Units.CONDUCTIVITY,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.CONDUCTIVITY}_{Units.CONDUCTIVITY}",
        device_class=SensorDeviceClass.CONDUCTIVITY,
        native_unit_of_measurement=UnitOfConductivity.MICROSIEMENS_PER_CM,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Count (-)
    (GiciskySensorDeviceClass.COUNT, None): SensorEntityDescription(
        key=str(GiciskySensorDeviceClass.COUNT),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # CO2 (parts per million)
    (
        GiciskySensorDeviceClass.CO2,
        Units.CONCENTRATION_PARTS_PER_MILLION,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.CO2}_{Units.CONCENTRATION_PARTS_PER_MILLION}",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Current (Ampere)
    (
        GiciskySensorDeviceClass.CURRENT,
        Units.ELECTRIC_CURRENT_AMPERE,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.CURRENT}_{Units.ELECTRIC_CURRENT_AMPERE}",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Dew Point (°C)
    (GiciskySensorDeviceClass.DEW_POINT, Units.TEMP_CELSIUS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.DEW_POINT}_{Units.TEMP_CELSIUS}",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Directions (°)
    (GiciskyExtendedSensorDeviceClass.DIRECTION, Units.DEGREE): SensorEntityDescription(
        key=f"{GiciskyExtendedSensorDeviceClass.DIRECTION}_{Units.DEGREE}",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Distance (mm)
    (
        GiciskySensorDeviceClass.DISTANCE,
        Units.LENGTH_MILLIMETERS,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.DISTANCE}_{Units.LENGTH_MILLIMETERS}",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Distance (m)
    (GiciskySensorDeviceClass.DISTANCE, Units.LENGTH_METERS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.DISTANCE}_{Units.LENGTH_METERS}",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Duration (seconds)
    (GiciskySensorDeviceClass.DURATION, Units.TIME_SECONDS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.DURATION}_{Units.TIME_SECONDS}",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Energy (kWh)
    (
        GiciskySensorDeviceClass.ENERGY,
        Units.ENERGY_KILO_WATT_HOUR,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.ENERGY}_{Units.ENERGY_KILO_WATT_HOUR}",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
    ),
    # Gas (m3)
    (
        GiciskySensorDeviceClass.GAS,
        Units.VOLUME_CUBIC_METERS,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.GAS}_{Units.VOLUME_CUBIC_METERS}",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL,
    ),
    # Gyroscope (°/s)
    (
        GiciskySensorDeviceClass.GYROSCOPE,
        Units.GYROSCOPE_DEGREES_PER_SECOND,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.GYROSCOPE}_{Units.GYROSCOPE_DEGREES_PER_SECOND}",
        native_unit_of_measurement=Units.GYROSCOPE_DEGREES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Humidity in (percent)
    (GiciskySensorDeviceClass.HUMIDITY, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.HUMIDITY}_{Units.PERCENTAGE}",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Illuminance (lux)
    (GiciskySensorDeviceClass.ILLUMINANCE, Units.LIGHT_LUX): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.ILLUMINANCE}_{Units.LIGHT_LUX}",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Mass sensor (kg)
    (GiciskySensorDeviceClass.MASS, Units.MASS_KILOGRAMS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.MASS}_{Units.MASS_KILOGRAMS}",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Mass sensor (lb)
    (GiciskySensorDeviceClass.MASS, Units.MASS_POUNDS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.MASS}_{Units.MASS_POUNDS}",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.POUNDS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Moisture (percent)
    (GiciskySensorDeviceClass.MOISTURE, Units.PERCENTAGE): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.MOISTURE}_{Units.PERCENTAGE}",
        device_class=SensorDeviceClass.MOISTURE,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Packet Id (-)
    (GiciskySensorDeviceClass.PACKET_ID, None): SensorEntityDescription(
        key=str(GiciskySensorDeviceClass.PACKET_ID),
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # PM10 (µg/m3)
    (
        GiciskySensorDeviceClass.PM10,
        Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.PM10}_{Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER}",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # PM2.5 (µg/m3)
    (
        GiciskySensorDeviceClass.PM25,
        Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.PM25}_{Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER}",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Power (Watt)
    (GiciskySensorDeviceClass.POWER, Units.POWER_WATT): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.POWER}_{Units.POWER_WATT}",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Precipitation (mm)
    (
        GiciskyExtendedSensorDeviceClass.PRECIPITATION,
        Units.LENGTH_MILLIMETERS,
    ): SensorEntityDescription(
        key=f"{GiciskyExtendedSensorDeviceClass.PRECIPITATION}_{Units.LENGTH_MILLIMETERS}",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Pressure (mbar)
    (GiciskySensorDeviceClass.PRESSURE, Units.PRESSURE_MBAR): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.PRESSURE}_{Units.PRESSURE_MBAR}",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.MBAR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Raw (-)
    (GiciskyExtendedSensorDeviceClass.RAW, None): SensorEntityDescription(
        key=str(GiciskyExtendedSensorDeviceClass.RAW),
    ),
    # Rotation (°)
    (GiciskySensorDeviceClass.ROTATION, Units.DEGREE): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.ROTATION}_{Units.DEGREE}",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Signal Strength (RSSI) (dB)
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
    # Speed (m/s)
    (
        GiciskySensorDeviceClass.SPEED,
        Units.SPEED_METERS_PER_SECOND,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.SPEED}_{Units.SPEED_METERS_PER_SECOND}",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Temperature (°C)
    (GiciskySensorDeviceClass.TEMPERATURE, Units.TEMP_CELSIUS): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.TEMPERATURE}_{Units.TEMP_CELSIUS}",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Text (-)
    (GiciskyExtendedSensorDeviceClass.TEXT, None): SensorEntityDescription(
        key=str(GiciskyExtendedSensorDeviceClass.TEXT),
    ),
    # Timestamp (datetime object)
    (
        GiciskySensorDeviceClass.TIMESTAMP,
        None,
    ): SensorEntityDescription(
        key=str(GiciskySensorDeviceClass.TIMESTAMP),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    # UV index (-)
    (
        GiciskySensorDeviceClass.UV_INDEX,
        None,
    ): SensorEntityDescription(
        key=str(GiciskySensorDeviceClass.UV_INDEX),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Volatile organic Compounds (VOC) (µg/m3)
    (
        GiciskySensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS}_{Units.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER}",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
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
    ),
    # Volume (L)
    (
        GiciskySensorDeviceClass.VOLUME,
        Units.VOLUME_LITERS,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.VOLUME}_{Units.VOLUME_LITERS}",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
    ),
    # Volume (mL)
    (
        GiciskySensorDeviceClass.VOLUME,
        Units.VOLUME_MILLILITERS,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.VOLUME}_{Units.VOLUME_MILLILITERS}",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        state_class=SensorStateClass.TOTAL,
    ),
    # Volume Flow Rate (m3/hour)
    (
        GiciskySensorDeviceClass.VOLUME_FLOW_RATE,
        Units.VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.VOLUME_FLOW_RATE}_{Units.VOLUME_FLOW_RATE_CUBIC_METERS_PER_HOUR}",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Volume Storage (L)
    (
        GiciskyExtendedSensorDeviceClass.VOLUME_STORAGE,
        Units.VOLUME_LITERS,
    ): SensorEntityDescription(
        key=f"{GiciskyExtendedSensorDeviceClass.VOLUME_STORAGE}_{Units.VOLUME_LITERS}",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Water (L)
    (
        GiciskySensorDeviceClass.WATER,
        Units.VOLUME_LITERS,
    ): SensorEntityDescription(
        key=f"{GiciskySensorDeviceClass.WATER}_{Units.VOLUME_LITERS}",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.TOTAL,
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
    async_add_entities([GiciskyDurationSensorEntity(hass, entry, duration_coordinator)])


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

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT

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
        self._attr_name = f"Gicisky {self._identifier} Write Duration"
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

