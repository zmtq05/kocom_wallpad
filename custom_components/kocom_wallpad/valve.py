from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
    ValveDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .ew11 import Ew11, GasValve
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    ew11: Ew11 = hass.data[DOMAIN][entry.entry_id]
    if ew11.gas_valve:
        async_add_entities([KocomIntegrationGasValve(ew11.gas_valve)])


class KocomIntegrationGasValve(ValveEntity):
    def __init__(self, gas_valve: GasValve) -> None:
        self.gas_valve = gas_valve
        self._attr_unique_id = "gas_valve"
        self._attr_name = "가스 밸브"
        self._attr_device_class = ValveDeviceClass.GAS
        self._attr_supported_features = ValveEntityFeature.CLOSE
        self._attr_reports_position = False

    @property
    def is_closed(self) -> bool:
        return self.gas_valve.is_locked

    async def async_added_to_hass(self) -> None:
        await self.gas_valve.refresh()
        self.gas_valve.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.gas_valve.remove_callback(self.async_write_ha_state)

    async def async_close_valve(self) -> None:
        await self.gas_valve.lock()