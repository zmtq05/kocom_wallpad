"""Kocom Wallpad light entity."""

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import Hub, LightController
from .util import typed_data
from .const import CONF_LIGHT, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Kocom Wallpad light entity."""
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    data = typed_data(entry)
    for room, light_size in data[CONF_LIGHT].items():
        room = int(room)
        controller = hub.light_controllers[room]
        entry.async_create_task(hass, controller.refresh())
        async_add_entities(
            [KocomLightEntity(room, light, controller) for light in range(light_size)]
        )


class KocomLightEntity(LightEntity):
    """Representation of a Kocom Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        room: int,
        light: int,
        controller: LightController,
    ):
        """Initialize the Kocom Light entity."""
        self.room = room
        self.light = light
        self.controller = controller
        self._attr_name = f"방{room} 조명{light+1}"
        self._attr_unique_id = f"room_{room}_light_{light+1}"

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        return self.controller.is_on(self.light)

    async def async_turn_on(self) -> None:
        """Turn on the light."""
        await self.controller.turn_on(self.light)

    async def async_turn_off(self) -> None:
        """Turn off the light."""
        await self.controller.turn_off(self.light)

    async def async_added_to_hass(self) -> None:
        """Register the callback."""
        self.controller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the callback."""
        self.controller.remove_callback(self.async_write_ha_state)
