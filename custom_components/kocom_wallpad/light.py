"""Kocom Wallpad light integration for Home Assistant.

This module implements support for Kocom Wallpad light controls, allowing users to
control their Kocom-connected lights through Home Assistant.
"""

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .hub import Hub, LightController
from .const import DOMAIN, NAME, VERSION, DEVICE_ID


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad light entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.
    """
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    for controller in hub.light_controllers.values():
        await controller.refresh()
        async_add_entities(
            [KocomLightEntity(controller, n)
             for n in range(controller.size)]
        )


class KocomLightEntity(LightEntity):
    """Representation of a Kocom Light Entity.

    This entity represents a single light control point in the Kocom Wallpad system.
    It supports basic on/off functionality and integrates with Home Assistant's
    light component.
    """

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, DEVICE_ID)},
        name=NAME,
        manufacturer="KOCOM",
        model="월패드",
        sw_version=VERSION,
    )

    def __init__(
        self,
        controller: LightController,
        n: int,
    ):
        """Initialize a new Kocom Light entity.

        Args:
            controller: The light controller instance that manages this light.
            n: The index number of this light within its room/controller.
        """
        self.n = n
        self.controller = controller
        self._attr_name = f"조명{controller.room}-{n}"
        self._attr_unique_id = f"light_{controller.room}_{n}"

    @property
    def is_on(self) -> bool:
        """Return whether the light is currently turned on.

        Returns:
            bool: True if the light is on, False otherwise.
        """
        return self.controller.is_on(self.n)

    async def async_turn_on(self) -> None:
        """Turn on the light.

        Sends a command through the controller to turn on this specific light.
        """
        await self.controller.turn_on(self.n)

    async def async_turn_off(self) -> None:
        """Turn off the light.

        Sends a command through the controller to turn off this specific light.
        """
        await self.controller.turn_off(self.n)

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant.

        Sets up state update callback when the entity is added to Home Assistant.
        """
        self.controller.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity is being removed from Home Assistant.

        Cleans up by removing the state update callback when the entity is removed.
        """
        self.controller.remove_callback(self.async_write_ha_state)
