from __future__ import annotations

import logging
from bluetooth_sensor_state_data import BluetoothData
from home_assistant_bluetooth import BluetoothServiceInfoBleak
from sensor_state_data import (
    SensorLibrary,
)

from .devices import DEVICE_TYPES, DeviceEntry

_LOGGER = logging.getLogger(__name__)

def to_mac(addr: bytes) -> str:
    """Return formatted MAC address."""
    return ":".join(f"{i:02X}" for i in addr)

class GiciskyBluetoothDeviceData(BluetoothData):
    """Data for BTHome Bluetooth devices."""

    def __init__(self) -> None:
        super().__init__()

        # The last service_info we saw that had a payload
        self.last_service_info: BluetoothServiceInfoBleak | None = None

        self.device: DeviceEntry | None = None

    def supported(self, data: BluetoothServiceInfoBleak) -> bool:
        if not super().supported(data):
            return False
        return True

    def _start_update(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Update from BLE advertisement data."""
        #_LOGGER.info("Parsing Gicisky BLE advertisement data: %s", service_info)
        if 0x5053 in service_info.manufacturer_data:
            #_LOGGER.info("BLE Info: %s", service_info)
            data = service_info.manufacturer_data[0x5053]
            for uuid in service_info.service_uuids:
                #_LOGGER.info("Gicisky %s BLE UUID %s data: %s", service_info.name, uuid, data.hex())
                if self._parse_gicisky(service_info, data):
                    self.last_service_info = service_info
        return None

    def _parse_gicisky(
        self, service_info: BluetoothServiceInfo, data: bytes
    ) -> bool:
        """Parser for Gicisky sensors"""
        if len(data) != 5:
            return False

        # determine the device type
        device_id = data[0]
        bettery = data[1]
        firmware = (data[2] << 8) + data[3]
        hardware = (data[0] << 8) + data[4]
        try:
            device = DEVICE_TYPES[device_id]
        except KeyError:
            _LOGGER.error("Unknown Gicisky device found. Data: %s", data.hex())
            return False

        self.device = device
        self.device_id = device_id
        identifier = service_info.address.replace(":", "")[-8:]
        self.set_title(f"{identifier} ({device.model})")
        self.set_device_name(f"{device.manufacturer} {identifier}")
        self.set_device_type(f"{device.model} {device.width}x{device.height}")
        self.set_device_manufacturer(device.manufacturer)
        self.set_device_sw_version(f"0x{firmware:04X}")
        self.set_device_hw_version(f"0x{hardware:04X}")

        volt = bettery / 10
        min = device.min_voltage
        max = device.max_voltage
        batt = (volt - min) * 100 / (max - min)
        self.update_predefined_sensor(SensorLibrary.BATTERY__PERCENTAGE, round(batt, 1))
        self.update_predefined_sensor(
            SensorLibrary.VOLTAGE__ELECTRIC_POTENTIAL_VOLT, round(volt, 1)
        )
        return True
    
