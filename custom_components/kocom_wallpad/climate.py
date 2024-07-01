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
        async_add_entities([KocomIntegrationThermostat(room, thermostat)])


class KocomIntegrationThermostat(ClimateEntity):
    def __init__(self, room: int, thermostat: Thermostat) -> None:
        self.room = room
        self.thermostat = thermostat
        self._attr_unique_id = f"room_{room}_thermostat"
        self._attr_name = f"방{room} 보일러"
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 1
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
        self._attr_preset_mode = PRESET_NONE

    @property
    def current_temperature(self) -> float:
        return self.thermostat.current_temp

    @property
    def target_temperature(self) -> float:
        return self.thermostat.target_temp

    @property
    def hvac_mode(self) -> HVACMode:
        if self.thermostat.is_on:
            return HVACMode.HEAT
        else:
            return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.thermostat.is_on:
            return HVACAction.OFF
        if self.thermostat.current_temp < self.thermostat.target_temp:
            return HVACAction.HEATING
        else:
            return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        match hvac_mode:
            case HVACMode.HEAT:
                await self.thermostat.on()
            case HVACMode.OFF:
                await self.thermostat.off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = int(kwargs["temperature"])
        await self.thermostat.set_temp(temp)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._attr_preset_mode = preset_mode
        if preset_mode == PRESET_AWAY:
            await self.thermostat.away()

        elif preset_mode == PRESET_NONE:
            if self.thermostat.is_on:
                await self.thermostat.on()
            else:
                await self.thermostat.off()

    async def async_added_to_hass(self) -> None:
        self.thermostat.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.thermostat.remove_callback(self.async_write_ha_state)
