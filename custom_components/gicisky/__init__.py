"""The Gicisky Bluetooth integration."""

from __future__ import annotations

from functools import partial
import logging
from asyncio import sleep, Lock
from io import BytesIO

from .imagegen import *
from .gicisky_ble import GiciskyBluetoothDeviceData, SensorUpdate
from .gicisky_ble.writer import update_image
from homeassistant.components.bluetooth import (
    DOMAIN as BLUETOOTH_DOMAIN,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.signal_type import SignalType
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    LOCK,
)
from .coordinator import GiciskyPassiveBluetoothProcessorCoordinator
from .types import GiciskyConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.CAMERA,
    Platform.IMAGE,
    Platform.TEXT
]

_LOGGER = logging.getLogger(__name__)

def process_service_info(
    hass: HomeAssistant,
    entry: GiciskyConfigEntry,
    device_registry: DeviceRegistry,
    service_info: BluetoothServiceInfoBleak,
) -> SensorUpdate:
    """Process a BluetoothServiceInfoBleak, running side effects and returning sensor data."""
    coordinator = entry.runtime_data
    data = coordinator.device_data
    update = data.update(service_info)

    return update




async def async_setup_entry(hass: HomeAssistant, entry: GiciskyConfigEntry) -> bool:
    """Set up Gicisky Bluetooth from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    address = entry.unique_id
    assert address is not None

    data = GiciskyBluetoothDeviceData()
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN][entry.entry_id]['address'] = address
    hass.data[DOMAIN][entry.entry_id]['data'] = data

    if LOCK not in hass.data[DOMAIN]:
        hass.data[DOMAIN][LOCK] = Lock()

    device_registry = dr.async_get(hass)
    bt_coordinator = GiciskyPassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=partial(process_service_info, hass, entry, device_registry),
        device_data=data,
        connectable=True,
        entry=entry,
    )

    image_coordinator: DataUpdateCoordinator[bytes] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
    )
    preview_coordinator: DataUpdateCoordinator[bytes] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
    )
    connectivity_coordinator: DataUpdateCoordinator[bool] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
    )
    entry.runtime_data = bt_coordinator
    hass.data[DOMAIN][entry.entry_id]['image_coordinator'] = image_coordinator
    hass.data[DOMAIN][entry.entry_id]['preview_coordinator'] = preview_coordinator
    hass.data[DOMAIN][entry.entry_id]['connectivity_coordinator'] = connectivity_coordinator
    connectivity_coordinator.async_set_updated_data(False)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    # callback for the draw custom service
    async def writeservice(service: ServiceCall) -> None:
        lock = hass.data[DOMAIN][LOCK]
        async with lock:
            device_ids = service.data.get("device_id")
            if isinstance(device_ids, str):
                device_ids = [device_ids]

            dry_run = service.data.get("dry_run", False)

            # Process each device
            for device_id in device_ids:
                entry_id = await get_entry_id_from_device(hass, device_id)
                address = hass.data[DOMAIN][entry_id]['address']
                data = hass.data[DOMAIN][entry_id]['data']
                image_coordinator = hass.data[DOMAIN][entry_id]['image_coordinator']
                preview_coordinator = hass.data[DOMAIN][entry_id]['preview_coordinator']
                connectivity_coordinator = hass.data[DOMAIN][entry_id]['connectivity_coordinator']
                ble_device = async_ble_device_from_address(hass, address)
                threshold = int(service.data.get("threshold", 128))
                red_threshold = int(service.data.get("red_threshold", 128))
                image = await hass.async_add_executor_job(customimage, entry_id, data.device, service, hass)
                image_bytes = BytesIO()
                image.save(image_bytes, "PNG")
                preview_coordinator.async_set_updated_data(image_bytes.getvalue())
                # If dry_run is True, skip sending to the actual device
                if dry_run:
                    continue

                max_retries = 3
                connectivity_coordinator.async_set_updated_data(True)
                for attempt in range(1, max_retries + 1):
                    success = await update_image(ble_device, data.device, image, threshold, red_threshold)
                    if success:
                        image_coordinator.async_set_updated_data(image_bytes.getvalue())
                        break

                    _LOGGER.warning(f"Write failed to {address} (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        await sleep(1)
                    else:
                        connectivity_coordinator.async_set_updated_data(False)
                        raise HomeAssistantError(f"Failed to write to {address} after {max_retries} attempts")
                connectivity_coordinator.async_set_updated_data(False)

    # register the services
    hass.services.async_register(DOMAIN, "write", writeservice)

    # only start after all platforms have had a chance to subscribe
    entry.async_on_unload(bt_coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GiciskyConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "write")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def get_entry_id_from_device(hass, device_id: str) -> str:
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get(device_id)
    if not device_entry:
        raise ValueError(f"Unknown device_id: {device_id}")
    if not device_entry.config_entries:
        raise ValueError(f"No config entries for device {device_id}")

    _LOGGER.debug(f"{device_id} to {device_entry.config_entries}")
    try:
        entry_id = next(iter(device_entry.config_entries))
    except StopIteration:
        _LOGGER.error("%s None", device_id)
        return None

    return entry_id