"""Kocom Wallpad gas valve integration for Home Assistant.

This module implements support for Kocom Wallpad gas valve control, providing
safety features for gas control through Home Assistant.
"""

from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
    ValveDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from .hub import Hub, GasValve
from .const import DOMAIN, NAME, VERSION, DEVICE_ID


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad gas valve entity from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.

    """
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if hub.gas_valve:
        async_add_entities([KocomGasValveEntity(hub.gas_valve)])


class KocomGasValveEntity(ValveEntity):
    """Kocom gas valve entity for Home Assistant.

    This entity represents a gas valve in the Kocom Wallpad system.
    It supports closing the valve for safety purposes, but does not support
    opening the valve remotely as a safety precaution.
    """

    _attr_device_class = ValveDeviceClass.GAS
    _attr_supported_features = ValveEntityFeature.CLOSE
    _attr_reports_position = False
    _attr_has_entity_name = True
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, DEVICE_ID)},
        name=NAME,
        manufacturer="KOCOM",
        model="월패드",
        sw_version=VERSION,
    )

    def __init__(self, gas_valve: GasValve) -> None:
        """Initialize a new Kocom gas valve entity.

        Args:
            gas_valve: The gas valve controller instance that manages this valve.

        """
        self.gas_valve = gas_valve
        self._attr_unique_id = "gas_valve"
        self._attr_name = "가스 밸브"

    @property
    def is_closed(self) -> bool:
        """Return whether the gas valve is currently closed (locked).

        Returns:
            bool: True if the valve is closed/locked, False if it's open/unlocked.

        """
        return self.gas_valve.is_locked

    async def async_close_valve(self) -> None:
        """Close (lock) the gas valve.

        This is a safety feature that allows remote shutoff of the gas supply.
        Note that the valve cannot be reopened remotely for safety reasons.
        """
        await self.gas_valve.lock()

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant.

        Performs initial state refresh and sets up state update callback
        when the entity is added to Home Assistant.
        """
        await self.gas_valve.refresh()
        self.gas_valve.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity is being removed from Home Assistant.

        Cleans up by removing the state update callback when the entity is removed.
        """
        self.gas_valve.remove_callback(self.async_write_ha_state)
