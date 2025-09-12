
import logging
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_BLUETOOTH
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Gicisky camera."""
    preview_coordinator = hass.data[DOMAIN][entry.entry_id]["preview_coordinator"]
    async_add_entities([GiciskyCamera(hass, entry, preview_coordinator)])


class GiciskyCamera(CoordinatorEntity[DataUpdateCoordinator[bytes]], Camera):
    """Gicisky Camera."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_supported_features = CameraEntityFeature.ON_OFF

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: DataUpdateCoordinator[bytes]) -> None:
        """Initialize the camera."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        address = hass.data[DOMAIN][entry.entry_id]['address']
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_name = f"Gicisky {self._identifier} Preview Content"
        self._attr_unique_id = f"gicisky_{self._identifier}_preview_content"
        #self._attr_is_on = False
        self._image = None

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
    
    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the camera image."""
        return self._image

    # def turn_off(self) -> None:
    #     """Turn the camera off."""
    #     self._attr_is_on = False
    #     self.async_write_ha_state()


    @property
    def data(self) -> bytes:
        """Return coordinator data for this entity."""
        return self.coordinator.data
            
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Updated camera data")
        self._image = self.data
        super()._handle_coordinator_update()