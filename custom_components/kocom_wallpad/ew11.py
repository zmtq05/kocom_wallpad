"""Ew11 Wrapper."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback

from .const import CONF_LIGHT
from .kocom_packet import Get, KocomPacket, Light, Seq, Set, Value
from .util import typed_data

_LOGGER = logging.getLogger(__name__)


class Ew11:
    """Ew11 Wrapper."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Ew11 Wrapper."""
        data = typed_data(entry)
        self._hass = hass
        self._host = data[CONF_HOST]
        self._port = data[CONF_PORT]
        self._reader, self._writer = None, None
        self._send_queue = asyncio.Queue()

        self.light_controllers = {
            int(room): LightController(self, int(room), light_size)
            for room, light_size in data[CONF_LIGHT].items()
        }

    async def connect(self) -> None:
        """Connect to the device."""
        self._reader, self._writer = await asyncio.open_connection(
            host=self._host, port=self._port
        )
        _LOGGER.info("Connected to %s", self._host)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._reader, self._writer = None, None
            _LOGGER.info("Disconneted from %s", self._host)

    async def read_loop(self) -> None:
        """Listen for incoming messages."""
        while self._reader is not None:
            data = await self._reader.read(21)

            if not data:
                break

            try:
                packet = KocomPacket(data)
                _LOGGER.debug("<-(%s) %s", self._host, packet)
            except AssertionError:
                _LOGGER.warning("Invalid packet: %s", data.hex(" ").upper())
                continue

            match packet.src:
                case Light(room) if packet.type == Seq():
                    await self.light_controllers[room].update(packet.value)
                case _:
                    pass

    async def send_loop(self) -> None:
        """Send packets."""
        while self._writer is not None:
            packet = await self._send_queue.get()
            _LOGGER.debug("->(%s) %s", self._host, packet)
            self._writer.write(packet)
            await self._writer.drain()
            await asyncio.sleep(1)  # prevent packet collision
            self._send_queue.task_done()

    async def send(self, packet: KocomPacket) -> None:
        """Send a packet."""
        await self._send_queue.put(packet)


class LightController:
    """Control the lighting in a room."""

    def __init__(self, ew11: Ew11, room: int, light_size: int) -> None:
        self._ew11: Ew11 = ew11
        self._room: int = room
        self._size: int = light_size
        self._state: list[bool] = [False] * 8
        self._callbacks: set[Callable[[], None]] = set()

    async def turn_on(self, light: int) -> None:
        """Turn on the light."""
        self._state[light] = True
        await self._ew11.send(
            KocomPacket.create(Light(self._room), Set(), Value.from_state(self._state))
        )

    async def turn_off(self, light: int) -> None:
        """Turn off the light."""
        self._state[light] = False
        await self._ew11.send(
            KocomPacket.create(Light(self._room), Set(), Value.from_state(self._state))
        )

    def is_on(self, light: int) -> bool:
        """Return true if the light is on."""
        return self._state[light]

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Unregister callback."""
        self._callbacks.discard(callback)

    async def init(self) -> None:
        """Initialize the lights."""
        await self._ew11.send(
            KocomPacket.create(Light(self._room), Get(), Value.from_state(self._state))
        )

    @callback
    async def update(self, state: Value) -> None:
        self._state = [x == 0xFF for x in state]
        _LOGGER.info("Room %s Light: %s", self._room, self._state[: self._size])
        for async_write_ha_state in self._callbacks:
            async_write_ha_state()
