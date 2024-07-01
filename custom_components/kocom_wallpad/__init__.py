from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry

from custom_components.kocom_wallpad.util import typed_data

from .hub import Hub

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.VALVE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = hub = Hub(hass, entry)
    await hub.connect()
    entry.async_create_background_task(hass, hub.read_loop(), "read_loop")
    entry.async_create_background_task(hass, hub.send_loop(), "send_loop")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hub: Hub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.disconnect()

    return unload_ok
