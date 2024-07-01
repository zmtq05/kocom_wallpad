"""Kocom Wallpad valve entity."""

from homeassistant.components.valve import (
    ValveEntity,
    ValveEntityFeature,
    ValveDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .hub import Hub, GasValve
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Kocom Wallpad valve entity."""
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if hub.gas_valve:
        async_add_entities([KocomIntegrationGasValve(hub.gas_valve)])


class KocomIntegrationGasValve(ValveEntity):
    """Kocom gas valve entity."""

    def __init__(self, gas_valve: GasValve) -> None:
        """Initialize the Kocom gas valve entity."""
        self.gas_valve = gas_valve
        self._attr_unique_id = "gas_valve"
        self._attr_name = "가스 밸브"
        self._attr_device_class = ValveDeviceClass.GAS
        self._attr_supported_features = ValveEntityFeature.CLOSE
        self._attr_reports_position = False

    @property
    def is_closed(self) -> bool:
        """Return true if the valve is closed."""
        return self.gas_valve.is_locked

    async def async_close_valve(self) -> None:
        """Close the valve."""
        await self.gas_valve.lock()

    async def async_added_to_hass(self) -> None:
        """Register the callback."""
        await self.gas_valve.refresh()
        self.gas_valve.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the callback."""
        self.gas_valve.remove_callback(self.async_write_ha_state)
