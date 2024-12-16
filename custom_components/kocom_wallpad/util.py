"""Utilities for development."""

from typing import TypedDict, cast
from homeassistant.config_entries import ConfigEntry


class EntryData(TypedDict):
    """Config type."""

    host: str
    port: int
    light: dict[str, int]
    thermostat: dict[str, bool]
    thermostat_poll_interval: int
    outlet: dict[str, int]
    air_conditioner: dict[str, bool]
    fan: bool
    gas: bool
    elevator: bool
    air_quality: bool


def typed_data(entry: ConfigEntry) -> EntryData:
    """Cast the config entry data to the typed dictionary."""

    return cast(EntryData, entry.data)
