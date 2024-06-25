from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .ew11 import Ew11

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = ew11 = Ew11(hass, entry)
    await ew11.connect()
    entry.async_create_background_task(hass, ew11.read_loop(), "read_loop")
    entry.async_create_background_task(hass, ew11.send_loop(), "send_loop")

    await hass.config_entries.async_forward_entry_setups(entry, ["light", "climate"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if unload_ok := await hass.config_entries.async_forward_entry_unload(
        entry, "light"
    ):
        ew11 = hass.data[DOMAIN].pop(entry.entry_id)
        await ew11.async_disconnect()

    return unload_ok
