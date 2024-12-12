"""Switch platform for Kocom Wallpad."""

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import Hub, OutletController
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad switch entities from a config entry."""
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    for controller in hub.outlet_controllers.values():
        await controller.refresh()
        async_add_entities(
            [KocomOutletEntity(controller, n) for n in range(controller.size)]
        )


class KocomOutletEntity(SwitchEntity):
    """Representation of a Kocom outlet."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, controller: OutletController, n: int) -> None:
        """Initialize a new Kocom Outlet entity."""
        self.n = n
        self.controller = controller
        self._attr_name = f"콘센트{controller.room}-{n}"
        self._attr_unique_id = f"outlet_{controller.room}_{n}"

    @property
    def is_on(self) -> bool:
        """Return whether the outlet is currently turned on."""
        return self.controller.is_on(self.n)

    async def async_turn_on(self) -> None:
        """Turn on the outlet."""
        await self.controller.turn_on(self.n)

    async def async_turn_off(self) -> None:
        """Turn off the outlet."""
        await self.controller.turn_off(self.n)

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant."""
        self.controller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity is being removed from Home Assistant."""
        self.controller.remove_callback(self.async_write_ha_state)
