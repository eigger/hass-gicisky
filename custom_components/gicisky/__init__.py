"""The Gicisky Bluetooth integration."""

from __future__ import annotations

from functools import partial
import logging
from asyncio import sleep, Lock
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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.signal_type import SignalType
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_DISCOVERED_EVENT_CLASSES,
    DOMAIN,
    LOCK,
    GiciskyBleEvent,
)
from .coordinator import GiciskyPassiveBluetoothProcessorCoordinator
from .types import GiciskyConfigEntry

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR]

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


def format_event_dispatcher_name(
    address: str, event_class: str
) -> SignalType[GiciskyBleEvent]:
    """Format an event dispatcher name."""
    return SignalType(f"{DOMAIN}_event_{address}_{event_class}")


def format_discovered_event_class(address: str) -> SignalType[str, GiciskyBleEvent]:
    """Format a discovered event class."""
    return SignalType(f"{DOMAIN}_discovered_event_class_{address}")


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
    event_classes = set(entry.data.get(CONF_DISCOVERED_EVENT_CLASSES, ()))
    bt_coordinator = GiciskyPassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=partial(process_service_info, hass, entry, device_registry),
        device_data=data,
        discovered_event_classes=event_classes,
        connectable=True,
        entry=entry,
    )

    async def _async_poll_data(hass: HomeAssistant, entry: GiciskyConfigEntry,) -> SensorUpdate:
        try:
            coordinator = entry.runtime_data
            return await coordinator.device_data.async_poll()
        except Exception as err:
            raise UpdateFailed(f"polling error: {err}") from err

    poll_coordinator = DataUpdateCoordinator[SensorUpdate](
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=partial(_async_poll_data, hass, entry),
        update_interval=timedelta(hours=24),
    )

    entry.runtime_data = bt_coordinator
    entry.runtime_data.poll_coordinator = poll_coordinator
    hass.data[DOMAIN][entry.entry_id]['poll_coordinator'] = poll_coordinator
    await poll_coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


    @callback
    # callback for the draw custom service
    async def writeservice(service: ServiceCall) -> None:
        lock = hass.data[DOMAIN][LOCK]
        async with lock:
            device_ids = service.data.get("device_id")
            if isinstance(device_ids, str):
                device_ids = [device_ids]

            # Process each device
            for device_id in device_ids:
                entry_id = await get_entry_id_from_device(hass, device_id)
                address = hass.data[DOMAIN][entry_id]['address']
                data = hass.data[DOMAIN][entry_id]['data']
                coordinator = hass.data[DOMAIN][entry_id]['poll_coordinator']
                ble_device = async_ble_device_from_address(hass, address)
                threshold = int(service.data.get("threshold", 128))
                red_threshold = int(service.data.get("red_threshold", 128))
                image = await hass.async_add_executor_job(customimage, entry_id, data.device, service, hass)

                max_retries = 3
                await data.set_connected(True)
                await coordinator.async_refresh()
                for attempt in range(1, max_retries + 1):
                    success = await update_image(ble_device, data.device, image, threshold, red_threshold)
                    if success:
                        await data.last_update()
                        break

                    _LOGGER.warning(f"Write failed to {address} (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        await sleep(1)
                    else:
                        await data.set_connected(False)
                        await coordinator.async_refresh()
                        raise HomeAssistantError(f"Failed to write to {address} after {max_retries} attempts")
                await data.set_connected(False)
                await coordinator.async_refresh()

    # register the services
    hass.services.async_register(DOMAIN, "write", writeservice)

    # only start after all platforms have had a chance to subscribe
    entry.async_on_unload(bt_coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GiciskyConfigEntry) -> bool:
    """Unload a config entry."""
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