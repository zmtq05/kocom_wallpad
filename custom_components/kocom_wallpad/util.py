from typing import TypedDict, cast
from homeassistant.config_entries import ConfigEntry


class EntryData(TypedDict):
    host: str
    port: int
    light: dict[str, int]
    thermostat: dict[str, bool]
    fan: bool
    gas: bool
    elevator: bool
    room_name: dict[str, str]


def typed_data(entry: ConfigEntry) -> EntryData:
    return cast(EntryData, entry.data)
