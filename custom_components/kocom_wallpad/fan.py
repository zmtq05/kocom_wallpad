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
):
    hub: Hub = hass.data[DOMAIN][entry.entry_id]
    if fan := hub.fan:
        async_add_entities([KocomIntegrationFan(fan)])


ORDERED_NAMED_FAN_SPEEDS = [1, 2, 3]


class KocomIntegrationFan(FanEntity):
    def __init__(self, fan: Fan) -> None:
        self.fan = fan
        self._attr_unique_id = "fan"
        self._attr_name = "환기"
        self._attr_supported_features = FanEntityFeature.SET_SPEED
        self._attr_speed_count = len(ORDERED_NAMED_FAN_SPEEDS)

    @property
    def is_on(self):
        return self.fan.is_on

    @property
    def percentage(self):
        if self.fan.step == 0:
            return 0
        return ordered_list_item_to_percentage(ORDERED_NAMED_FAN_SPEEDS, self.fan.step)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        step = percentage_to_ordered_list_item(ORDERED_NAMED_FAN_SPEEDS, percentage)
        await self.fan.set_step(step)

    async def async_turn_on(self, percentage: int | None = None) -> None:
        # TODO another frontend?
        # Currently, percentage is always None
        await self.async_set_percentage(percentage or 66)

    async def async_turn_off(self) -> None:
        await self.fan.set_step(0)

    async def async_added_to_hass(self) -> None:
        await self.fan.refresh()
        self.fan.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self.fan.remove_callback(self.async_write_ha_state)
