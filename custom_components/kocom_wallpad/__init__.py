from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry

from custom_components.kocom_wallpad.util import typed_data

from .ew11 import Ew11

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.VALVE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ew11 = Ew11(hass, entry)
    await ew11.connect()
    entry.async_create_background_task(hass, ew11.read_loop(), "read_loop")
    entry.async_create_background_task(hass, ew11.send_loop(), "send_loop")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        ew11: Ew11 = hass.data[DOMAIN].pop(entry.entry_id)
        await ew11.disconnect()

    return unload_ok
