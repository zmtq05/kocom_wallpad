from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.kocom_wallpad.ew11 import Ew11
from .util import get_data

from .const import CONF_LIGHT, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    ew11: Ew11 = hass.data[DOMAIN][entry.entry_id]
    entry.async_create_task(hass, ew11.init_light())
    data = get_data(entry)
    for room, light_size in data[CONF_LIGHT].items():
        for light in range(light_size):
            async_add_entities([KocomLight(int(room), light, ew11)])


class KocomLight(LightEntity):
    """Representation of a Kocom Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, room: int, light: int, ew11: Ew11):
        self._is_on = False
        self.room = room
        self.light = light
        self._ew11 = ew11
        self._attr_name = f"방{room} 조명{light+1}"
        self._attr_unique_id = f"room_{room}_light_{light+1}"

    @property
    def is_on(self) -> bool:
        # return self._is_on
        return self._ew11.lights[self.room]["state"][self.light] == 0xFF

    async def async_turn_on(self) -> None:
        await self._ew11.turn_on_light(self.room, self.light)

    async def async_turn_off(self) -> None:
        await self._ew11.turn_off_light(self.room, self.light)

    async def async_added_to_hass(self) -> None:
        self._ew11.register_callback(self.room, self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._ew11.unregister_callback(self.room, self.async_write_ha_state)
