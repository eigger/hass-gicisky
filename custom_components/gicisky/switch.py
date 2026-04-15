"""Support for Gicisky write lock switch."""

import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from propcache.api import cached_property

from .const import DOMAIN, WRITE_LOCK

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Gicisky write lock switch."""
    async_add_entities([GiciskyWriteLockSwitch(hass, entry)])


class GiciskyWriteLockSwitch(RestoreEntity, SwitchEntity):
    """Switch that locks physical writes (virtual updates still apply)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:lock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        address = hass.data[DOMAIN][entry.entry_id]["address"]
        self._address = address
        self._identifier = address.replace(":", "")[-8:]
        self._attr_name = f"Gicisky {self._identifier} Write Lock"
        self._attr_unique_id = f"gicisky_{self._identifier}_write_lock"
        self._hass = hass
        self._entry_id = entry.entry_id
        self._is_on = False

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

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the write lock."""
        self._is_on = True
        self._hass.data[DOMAIN][self._entry_id][WRITE_LOCK] = True

        # Save to config entry data for persistence
        config_entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if config_entry:
            data = {**config_entry.data, WRITE_LOCK: True}
            self._hass.config_entries.async_update_entry(config_entry, data=data)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the write lock."""
        self._is_on = False
        self._hass.data[DOMAIN][self._entry_id][WRITE_LOCK] = False

        # Save to config entry data for persistence
        config_entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if config_entry:
            data = {**config_entry.data, WRITE_LOCK: False}
            self._hass.config_entries.async_update_entry(config_entry, data=data)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore state when added to hass."""
        await super().async_added_to_hass()

        # Restore from config entry data (most reliable for config entities)
        config_entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if config_entry and WRITE_LOCK in config_entry.data:
            self._is_on = config_entry.data[WRITE_LOCK]
        else:
            # Fallback to RestoreEntity if not in config entry
            last_state = await self.async_get_last_state()
            if last_state is not None:
                self._is_on = last_state.state == "on"
            else:
                # Default to False if no previous state
                self._is_on = False

        # Update hass.data with restored state
        self._hass.data[DOMAIN][self._entry_id][WRITE_LOCK] = self._is_on
