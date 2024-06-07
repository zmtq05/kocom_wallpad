from __future__ import annotations

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ew11 import Ew11, LightController
from .util import get_data
from .const import CONF_LIGHT, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    ew11: Ew11 = hass.data[DOMAIN][entry.entry_id]
    data = get_data(entry)
    for room, light_size in data[CONF_LIGHT].items():
        room = int(room)
        controller = ew11.light_controllers[room]
        entry.async_create_task(hass, controller.init())
        async_add_entities(
            [KocomLight(room, light, controller) for light in range(light_size)]
        )


class KocomLight(LightEntity):
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
        self.room = room
        self.light = light
        self.controller = controller
        self._attr_name = f"방{room} 조명{light+1}"
        self._attr_unique_id = f"room_{room}_light_{light+1}"

    @property
    def is_on(self) -> bool:
        return self.controller.is_on(self.light)

    async def async_turn_on(self) -> None:
        await self.controller.turn_on(self.light)

    async def async_turn_off(self) -> None:
        await self.controller.turn_off(self.light)

    async def async_added_to_hass(self) -> None:
        self.controller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.controller.remove_callback(self.async_write_ha_state)
