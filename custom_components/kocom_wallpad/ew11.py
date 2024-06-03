"""Ew11 Wrapper."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .kocom_packet import KocomPacket, Light, Get, Seq, Set, Value
from .const import CONF_LIGHT
from .util import get_data

_LOGGER = logging.getLogger(__name__)


class Ew11Socket:
    """Ew11 Socket."""

    def __init__(self, host: str, port: int) -> None:
        """Ew11 Socket."""
        self._sock = socket.create_connection(address=(host, port), timeout=5)

    def close(self) -> None:
        """Close the socket."""
        self._sock.close()


class Ew11:
    """Ew11 Wrapper."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Ew11 Wrapper."""
        self._hass = hass
        self._entry = entry
        data = get_data(entry)
        self._host = data[CONF_HOST]
        self._port = data[CONF_PORT]
        self._reader, self._writer = None, None
        self.lights: dict[int, dict[Literal["state", "callback"], Any]] = {
            int(room): {"state": [0x00] * 8, "callback": set()}
            for room in data[CONF_LIGHT]
        }

    async def async_connect(self) -> None:
        """Connect to the device."""
        self._reader, self._writer = await asyncio.open_connection(
            host=self._host, port=self._port
        )

    async def async_disconnect(self) -> None:
        """Disconnect from the device."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._reader, self._writer = None, None

    def register_callback(self, room: int, callback: Callable[[], None]) -> None:
        """Register callback."""
        self.lights[room]["callback"].add(callback)

    def unregister_callback(self, room: int, callback: Callable[[], None]) -> None:
        """Unregister callback."""
        self.lights[room]["callback"].discard(callback)

    async def listen(self) -> None:
        """Listen for incoming messages."""
        while self._reader is not None:
            data = await self._reader.read(21)
            if not data:
                break

            try:
                packet = KocomPacket(data)
                # _LOGGER.debug("<-(%s) %s", self._host, packet)
                _LOGGER.info("%s %s-> %s %s: %s", packet.src, packet.type, packet.dst, packet.cmd, packet.value)
            except ValueError as err:
                _LOGGER.warning("Invalid packet: %s", err)
                continue

            if packet.type != Seq():
                continue

            if packet.cmd != Set():
                continue

            src = packet.src
            match (src[0], src[1]):
                case (0x0E, room):
                    self.lights[room]["state"] = list(packet.value)
                    for cb in self.lights[room]["callback"]:
                        cb()
                case _:
                    _LOGGER.warning("Unhandle packet: %s", packet)



    async def turn_on_light(self, room: int, light: int) -> None:
        """Turn on the light."""
        state = self.lights[room]["state"]
        state[light] = 0xFF
        packet = KocomPacket.create(Light(room), Set(), Value.from_state(state))
        assert self._writer
        self._writer.write(packet)
        await self._writer.drain()

    async def turn_off_light(self, room: int, light: int) -> None:
        """Turn off the light."""
        state = self.lights[room]["state"]
        state[light] = 0x00
        packet = KocomPacket.create(Light(room), Set(), Value.from_state(state))
        assert self._writer
        self._writer.write(packet)
        await self._writer.drain()

    async def init_light(self) -> None:
        """Initialize the light."""
        for room in self.lights:
            state: list[int] = self.lights[room]["state"]
            packet = KocomPacket.create(Light(room), Get(), Value.from_state(state))
            assert self._writer
            self._writer.write(packet)
            await self._writer.drain()
