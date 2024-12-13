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
    FAN_HIGH,
    FAN_MEDIUM,
    FAN_LOW,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature

from .util import typed_data
from .hub import AirConditioner, AirConditionerMode, Hub, Thermostat
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

    for room, air_conditioner in hub.air_conditioners.items():
        async_add_entities([KocomAirConditionerEntity(room, air_conditioner)])


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


class KocomAirConditionerEntity(ClimateEntity):
    """Representation of a Kocom Air Conditioner Entity.

    This entity represents a single room's air conditioner in the Kocom Wallpad system.
    It supports temperature control, fan speed control, and operation mode control.
    """

    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
        HVACMode.AUTO,
    ]
    _attr_fan_modes = [FAN_HIGH, FAN_MEDIUM, FAN_LOW]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_has_entity_name = True

    def __init__(self, room: int, air_conditioner: AirConditioner) -> None:
        """Initialize a new Kocom air conditioner entity.

        Args:
            room: The room number this air conditioner controls.
            air_conditioner: The air conditioner controller instance.

        """
        self.room = room
        self.air_conditioner = air_conditioner
        self._attr_unique_id = f"air_conditioner_{room}"
        self._attr_name = f"에어컨{room}"

    @property
    def current_temperature(self) -> float:
        """Get the current room temperature.

        Returns:
            float: The current temperature in degrees Celsius.

        """
        return self.air_conditioner.current_temperature

    @property
    def target_temperature(self) -> float:
        """Get the target temperature setting.

        Returns:
            float: The target temperature in degrees Celsius.

        """
        return self.air_conditioner.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Get the current HVAC operation mode.

        Returns:
            HVACMode: The current operation mode:
                - COOL if cooling mode is active
                - FAN_ONLY if fan only mode is active
                - DRY if drying mode is active
                - AUTO if automatic mode is active

        """
        match self.air_conditioner.mode:
            case AirConditionerMode.Cooling:
                return HVACMode.COOL
            case AirConditionerMode.FanOnly:
                return HVACMode.FAN_ONLY
            case AirConditionerMode.Dry:
                return HVACMode.DRY
            case AirConditionerMode.Auto:
                return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        """Get the current HVAC action status.

        Returns:
            HVACAction: The current action:
                - OFF if the air conditioner is off
                - COOLING if cooling mode is active
                - FAN if fan only mode is active
                - DRYING if drying mode is active

        """
        if not self.air_conditioner.is_on:
            return HVACAction.OFF

        match self.air_conditioner.mode:
            case AirConditionerMode.Cooling:
                return HVACAction.COOLING
            case AirConditionerMode.FanOnly:
                return HVACAction.FAN
            case AirConditionerMode.Dry:
                return HVACAction.DRYING

        # FIXME: is this reachable?
        return HVACAction.OFF

    @property
    def fan_mode(self) -> str:
        """Get the current fan speed setting.

        Returns:
            str: The current fan speed:
                - FAN_LOW if the fan speed is low
                - FAN_MEDIUM if the fan speed is medium
                - FAN_HIGH if the fan speed is high

        """
        match self.air_conditioner.fan_speed:
            case 0x01:
                return FAN_LOW
            case 0x02:
                return FAN_MEDIUM
            case 0x03:
                return FAN_HIGH
            case _:
                raise ValueError(f"Invalid fan speed: {self.air_conditioner.fan_speed}")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC operation mode.

        Args:
            hvac_mode: The desired operation mode (COOL, FAN_ONLY, DRY, AUTO, or OFF).

        """
        match hvac_mode:
            case HVACMode.OFF:
                await self.air_conditioner.turn_off()
            case HVACMode.COOL:
                await self.air_conditioner.set_mode(AirConditionerMode.Cooling)
            case HVACMode.FAN_ONLY:
                await self.air_conditioner.set_mode(AirConditionerMode.FanOnly)
            case HVACMode.DRY:
                await self.air_conditioner.set_mode(AirConditionerMode.Dry)
            case HVACMode.AUTO:
                await self.air_conditioner.set_mode(AirConditionerMode.Auto)

    async def async_turn_on(self) -> None:
        """Turn on the air conditioner."""
        await self.air_conditioner.turn_on()

    async def async_turn_off(self) -> None:
        """Turn off the air conditioner."""
        await self.air_conditioner.turn_off()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan speed.

        Args:
            fan_mode: The desired fan speed (low, medium, high).

        """
        fan_speed = 0
        match fan_mode:
            case "low":
                fan_speed = 0x01
            case "medium":
                fan_speed = 0x02
            case "high":
                fan_speed = 0x03
        await self.air_conditioner.set_fan_speed(fan_speed)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature.

        Args:
            **kwargs: Must contain 'temperature' key with the desired
                     temperature in degrees Celsius.

        """
        temp = int(kwargs["temperature"])
        await self.air_conditioner.set_temp(temp)

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant.

        Performs initial state refresh and sets up state update callback
        when the entity is added to Home Assistant.
        """
        self.air_conditioner.register_callback(self.async_write_ha_state)
        await self.air_conditioner.refresh()
