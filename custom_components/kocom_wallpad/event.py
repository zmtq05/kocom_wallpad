"""Kocom Wallpad Event Integration for Home Assistant.

This module implements support for Kocom Wallpad event entities, providing
event-based notifications for elevator arrivals.
"""

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.event import EventEntity
from .hub import Hub, Elevator
from .const import DOMAIN, EVENT_ELEVATOR_ARRIVAL


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad event entities from a config entry.

    Initializes elevator arrival event entity and sets up periodic polling if configured.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being setup.
        async_add_entities: Callback to add new entities to Home Assistant.

    """
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if elevator := hub.elevator:
        async_add_entities([ElevatorArrivalEvent(elevator)])


class ElevatorArrivalEvent(EventEntity):
    """Event entity for elevator arrivals."""

    _attr_event_types = [EVENT_ELEVATOR_ARRIVAL]

    def __init__(self, elevator: Elevator) -> None:
        """Initialize the elevator arrival event entity.

        Args:
            elevator: The Elevator instance this event entity belongs to.

        """
        self.elevator = elevator
        self._attr_name = "엘리베이터 도착 이벤트"
        self._attr_unique_id = "elevator_arrival_event"

    @callback
    def _async_handle_event(self, event: str) -> None:
        self._trigger_event(event)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register event handler for elevator arrival."""
        self.elevator.register_event_handler(self._async_handle_event)
