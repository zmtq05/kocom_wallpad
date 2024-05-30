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

            # handle packet
            _LOGGER.debug("<-(%s) %s", self._host, data.hex(" ").upper())

            if len(data) != 21:
                # invalid length; truncated?
                continue

            header = data[0:2]
            type_ = data[2:4]
            # pad = data[4]
            dst = data[5:7]
            src = data[7:9]
            cmd = data[9]
            val = data[10:18]
            # chksum = data[18]
            footer = data[19:21]

            if header != b"\xaa\x55":
                # invalid header
                _LOGGER.warning("Invalid header")
                continue

            if footer != b"\x0d\x0d":
                # invalid footer
                _LOGGER.warning("Invalid footer")
                continue

            if dst != b"\x01\x00":
                # ignore broadcast
                _LOGGER.debug("Ignoring broadcast message")
                continue

            if src == b"\x01\x00":
                # ignore self
                _LOGGER.debug("Ignoring self message")
                continue

            match (type_[0], type_[1]):
                case (0x30, 0xBC | 0xBD | 0xBE):
                    match cmd:
                        case 0x00:
                            match (src[0], src[1]):
                                case (0x0E, room):
                                    self.lights[room]["state"] = list(val)
                                    for cb in self.lights[room]["callback"]:
                                        cb()
                                case _:
                                    pass  # TODO handle other sources
                        case _:
                            pass
                case (0x30, 0xDC | 0xDD | 0xDE):
                    _LOGGER.debug("Received ACK")
                case _:
                    # invalid type
                    _LOGGER.warning("Invalid type: %s", type_.hex(" ").upper())
                    continue

    async def turn_on_light(self, room: int, light: int) -> None:
        """Turn on the light."""
        value = self.lights[room]["state"]
        value[light] = 0xFF
        body = bytearray([0x30, 0xBC, 0x00, 0x0E, room, 0x01, 0x00, 0x00] + value)
        body += (sum(body) % 256).to_bytes()
        assert self._writer
        self._writer.write(b"\xAA\x55" + body + b"\x0D\x0D")
        await self._writer.drain()

    async def turn_off_light(self, room: int, light: int) -> None:
        """Turn off the light."""
        value = self.lights[room]["state"]
        value[light] = 0x00
        body = bytearray([0x30, 0xBC, 0x00, 0x0E, room, 0x01, 0x00, 0x00] + value)
        body += (sum(body) % 256).to_bytes()
        assert self._writer
        self._writer.write(b"\xAA\x55" + body + b"\x0D\x0D")
        await self._writer.drain()

    async def init_light(self) -> None:
        """Initialize the light."""
        for room in self.lights:
            body = bytearray(
                [0x30, 0xBC, 0x00, 0x0E, room, 0x01, 0x00, 0x3A] + [0x00] * 8
            )
            body += (sum(body) % 256).to_bytes()
            assert self._writer
            self._writer.write(b"\xAA\x55" + body + b"\x0D\x0D")
            await self._writer.drain()
