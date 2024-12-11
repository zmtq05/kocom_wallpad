"""Kocom Wallpad Climate Integration for Home Assistant.

This module implements support for Kocom Wallpad thermostats, providing heating control
and temperature monitoring capabilities through Home Assistant's climate platform.
Features include:
- Temperature monitoring and control
- Multiple operation modes (Heat, Off)
- Away mode support
- Periodic status polling
"""

import asyncio
from typing import Any
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
    HVACAction,
    PRESET_AWAY,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature

from .util import typed_data
from .hub import Hub, Thermostat
from .const import CONF_THERMO_POLL_INTERVAL, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad climate entities from a config entry.

    Initializes thermostat entities and sets up periodic polling if configured.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.

    """
    data = typed_data(entry)
    interval = data.get(CONF_THERMO_POLL_INTERVAL, 60)

    async def polling(hub: Hub):
        """Periodically poll thermostats for status updates.

        Args:
            hub: The Hub instance containing the thermostats to poll.

        """
        while True:
            # refresh thermostats every 60 seconds
            # no packets when controlling the target temperature
            await asyncio.sleep(interval)
            for thermostat in hub.thermostats.values():
                await thermostat.refresh()

    hub: Hub = hass.data[DOMAIN][entry.entry_id]

    if interval > 0:
        entry.async_create_background_task(hass, polling(hub), "polling_thermostat")

    for room, thermostat in hub.thermostats.items():
        async_add_entities([KocomThermostatEntity(room, thermostat)])


class KocomThermostatEntity(ClimateEntity):
    """Representation of a Kocom Thermostat Entity.

    This entity represents a single room's thermostat in the Kocom Wallpad system.
    It supports temperature control, heating modes, and away mode functionality.
    Temperature is controlled in Celsius with 1-degree steps.
    """

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
    _attr_preset_mode = PRESET_NONE
    _attr_has_entity_name = True

    def __init__(self, room: int, thermostat: Thermostat) -> None:
        """Initialize a new Kocom thermostat entity.

        Args:
            room: The room number this thermostat controls.
            thermostat: The thermostat controller instance.

        """
        self.room = room
        self.thermostat = thermostat
        self._attr_unique_id = f"thermostat_{room}"
        self._attr_name = f"보일러{room}"

    @property
    def current_temperature(self) -> float:
        """Get the current room temperature.

        Returns:
            float: The current temperature in degrees Celsius.

        """
        return self.thermostat.current_temp

    @property
    def target_temperature(self) -> float:
        """Get the target temperature setting.

        Returns:
            float: The target temperature in degrees Celsius.

        """
        return self.thermostat.target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Get the current HVAC operation mode.

        Returns:
            HVACMode: HEAT if the thermostat is on, OFF otherwise.

        """
        if self.thermostat.is_on:
            return HVACMode.HEAT
        else:
            return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Get the current HVAC action status.

        Returns:
            HVACAction: The current action:
                - OFF if the thermostat is off
                - HEATING if the current temperature is below target
                - IDLE if the target temperature is reached

        """
        if not self.thermostat.is_on:
            return HVACAction.OFF
        if self.thermostat.current_temp < self.thermostat.target_temp:
            return HVACAction.HEATING
        else:
            return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC operation mode.

        Args:
            hvac_mode: The desired operation mode (HEAT or OFF).

        """
        match hvac_mode:
            case HVACMode.HEAT:
                await self.thermostat.on()
            case HVACMode.OFF:
                await self.thermostat.off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature.

        Args:
            **kwargs: Must contain 'temperature' key with the desired
                     temperature in degrees Celsius.

        """
        temp = int(kwargs["temperature"])
        await self.thermostat.set_temp(temp)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of operation.

        Args:
            preset_mode: The desired preset mode:
                - PRESET_AWAY: Sets the thermostat to away mode
                - PRESET_NONE: Returns to normal operation mode

        """
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_AWAY:
            await self.thermostat.away()
        elif preset_mode == PRESET_NONE:
            if self.thermostat.is_on:
                await self.thermostat.on()
            else:
                await self.thermostat.off()

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant.

        Performs initial state refresh and sets up state update callback
        when the entity is added to Home Assistant.
        """
        await self.thermostat.refresh()
        self.thermostat.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity is being removed from Home Assistant.

        Cleans up by removing the state update callback when the entity is removed.
        """
        self.thermostat.remove_callback(self.async_write_ha_state)
