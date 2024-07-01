"""Kocom Wallpad thermostat entity."""

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

from .hub import Hub, Thermostat
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Kocom Wallpad climate entity."""

    async def polling(hub: Hub):
        while True:
            # refresh thermostats every 60 seconds
            # no packets when controlling the target temperature
            for thermostat in hub.thermostats.values():
                await thermostat.refresh()
            await asyncio.sleep(60)

    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    entry.async_create_background_task(hass, polling(hub), "polling_thermostat")

    for room, thermostat in hub.thermostats.items():
        async_add_entities([KocomThermostatEntity(room, thermostat)])


class KocomThermostatEntity(ClimateEntity):
    """Kocom thermostat entity."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
    _attr_preset_mode = PRESET_NONE

    def __init__(self, room: int, thermostat: Thermostat) -> None:
        """Initialize the Kocom thermostat entity."""
        self.room = room
        self.thermostat = thermostat
        self._attr_unique_id = f"thermostat_{room}"
        self._attr_name = f"보일러{room}"

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self.thermostat.current_temp

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self.thermostat.target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current hvac mode."""
        if self.thermostat.is_on:
            return HVACMode.HEAT
        else:
            return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current hvac action."""
        if not self.thermostat.is_on:
            return HVACAction.OFF
        if self.thermostat.current_temp < self.thermostat.target_temp:
            return HVACAction.HEATING
        else:
            return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the hvac mode."""
        match hvac_mode:
            case HVACMode.HEAT:
                await self.thermostat.on()
            case HVACMode.OFF:
                await self.thermostat.off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temp = int(kwargs["temperature"])
        await self.thermostat.set_temp(temp)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode."""
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_AWAY:
            await self.thermostat.away()

        elif preset_mode == PRESET_NONE:
            if self.thermostat.is_on:
                await self.thermostat.on()
            else:
                await self.thermostat.off()

    async def async_added_to_hass(self) -> None:
        """Register the callback."""
        self.thermostat.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the callback."""
        self.thermostat.remove_callback(self.async_write_ha_state)
