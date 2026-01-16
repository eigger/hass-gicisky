"""The Gicisky Bluetooth integration."""

from collections.abc import Callable
from logging import Logger

from .gicisky_ble import GiciskyBluetoothDeviceData, SensorUpdate

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.core import HomeAssistant

from .types import GiciskyConfigEntry


class GiciskyPassiveBluetoothProcessorCoordinator(
    PassiveBluetoothProcessorCoordinator[SensorUpdate]
):
    """Define a Gicisky Bluetooth Passive Update Processor Coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        address: str,
        mode: BluetoothScanningMode,
        update_method: Callable[[BluetoothServiceInfoBleak], SensorUpdate],
        device_data: GiciskyBluetoothDeviceData,
        entry: GiciskyConfigEntry,
        connectable: bool = False,
    ) -> None:
        """Initialize the Gicisky Bluetooth Passive Update Processor Coordinator."""
        super().__init__(hass, logger, address, mode, update_method, connectable)
        self.device_data = device_data
        self.entry = entry


class GiciskyPassiveBluetoothDataProcessor[_T](
    PassiveBluetoothDataProcessor[_T, SensorUpdate]
):
    """Define a Gicisky Bluetooth Passive Update Data Processor."""

    coordinator: GiciskyPassiveBluetoothProcessorCoordinator
