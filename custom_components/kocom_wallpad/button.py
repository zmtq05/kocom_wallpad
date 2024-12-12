"""Kocom Wallpad Button Integration for Home Assistant.

This module implements support for Kocom Wallpad button entities, providing
buttons for calling the elevator.
"""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import Hub, Elevator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad button entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.

    """
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if elevator := hub.elevator:
        async_add_entities([ElevatorCallButton(elevator)])


class ElevatorCallButton(ButtonEntity):
    """Button entity for elevator call."""

    def __init__(self, elevator: Elevator) -> None:
        """Initialize the elevator call button."""
        self.elevator = elevator
        self._attr_name = "엘리베이터 호출"
        self._attr_unique_id = "elevator_call_button"

    async def async_press(self) -> None:
        """Execute when the button is pressed."""
        await self.elevator.call()
