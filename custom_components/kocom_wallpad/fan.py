"""Kocom Wallpad ventilation fan integration for Home Assistant.

This module implements support for Kocom Wallpad ventilation fan control,
allowing users to control their home ventilation system through Home Assistant.
The fan supports multiple speed levels and can be turned on/off.
"""

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .hub import Hub, Fan
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad fan entity from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.
    """
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if fan := hub.fan:
        async_add_entities([KocomFanEntity(fan)])


ORDERED_NAMED_FAN_SPEEDS = [1, 2, 3]  # Low, Medium, High speeds


class KocomFanEntity(FanEntity):
    """Kocom ventilation fan entity for Home Assistant.

    This entity represents a ventilation fan in the Kocom Wallpad system.
    It supports three speed levels (low, medium, high) and can be turned on/off.
    The speed levels are mapped to Home Assistant's percentage-based fan control.
    """

    _attr_supported_features = FanEntityFeature.SET_SPEED
    _attr_speed_count = len(ORDERED_NAMED_FAN_SPEEDS)

    def __init__(self, fan: Fan) -> None:
        """Initialize a new Kocom fan entity.

        Args:
            fan: The fan controller instance that manages this ventilation fan.
        """
        self.fan = fan
        self._attr_unique_id = "fan"
        self._attr_name = "전열교환기"

    @property
    def is_on(self) -> bool:
        """Return whether the fan is currently running.

        Returns:
            bool: True if the fan is running at any speed, False if it's off.
        """
        return self.fan.is_on

    @property
    def percentage(self) -> int:
        """Return the current speed as a percentage.

        The fan's three speed levels (1-3) are mapped to percentages:
        - Speed 1 (Low) = 33%
        - Speed 2 (Medium) = 66%
        - Speed 3 (High) = 100%

        Returns:
            int: The current speed as a percentage (0-100).
        """
        if self.fan.step == 0:
            return 0
        return ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, self.fan.step)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan by percentage.

        Args:
            percentage: The desired speed as a percentage (0-100).
                       0 turns the fan off.
                       1-33 sets to low speed.
                       34-66 sets to medium speed.
                       67-100 sets to high speed.
        """
        if percentage == 0:
            await self.async_turn_off()
            return
        step = percentage_to_ordered_list_item(
            ORDERED_NAMED_FAN_SPEEDS, percentage)
        await self.fan.set_step(step)

    async def async_turn_on(self, percentage: int | None = None) -> None:
        """Turn on the fan.

        Args:
            percentage: Optional speed setting (0-100). If not provided,
                       defaults to medium speed (66%).
        """
        # TODO another frontend?
        # Currently, percentage is always None
        await self.async_set_percentage(percentage or 66)

    async def async_turn_off(self) -> None:
        """Turn off the fan.

        Sets the fan speed to 0, effectively turning it off.
        """
        await self.fan.set_step(0)

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to Home Assistant.

        Performs initial state refresh and sets up state update callback
        when the entity is added to Home Assistant.
        """
        await self.fan.refresh()
        self.fan.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Handle when entity is being removed from Home Assistant.

        Cleans up by removing the state update callback when the entity is removed.
        """
        self.fan.remove_callback(self.async_write_ha_state)
