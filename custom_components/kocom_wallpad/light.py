"""Kocom Wallpad light entity."""

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import Hub, LightController
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Kocom Wallpad light entity."""
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    for controller in hub.light_controllers.values():
        async_add_entities(
            [KocomLightEntity(controller, n) for n in range(controller.size)]
        )


class KocomLightEntity(LightEntity):
    """Representation of a Kocom Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        controller: LightController,
        n: int,
    ):
        """Initialize the Kocom Light entity."""
        self.n = n
        self.controller = controller
        self._attr_name = f"조명{controller.room}-{n}"
        self._attr_unique_id = f"light_{controller.room}_{n}"

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        return self.controller.is_on(self.n)

    async def async_turn_on(self) -> None:
        """Turn on the light."""
        await self.controller.turn_on(self.n)

    async def async_turn_off(self) -> None:
        """Turn off the light."""
        await self.controller.turn_off(self.n)

    async def async_added_to_hass(self) -> None:
        """Register the callback."""
        await self.controller.refresh()
        self.controller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the callback."""
        self.controller.remove_callback(self.async_write_ha_state)
