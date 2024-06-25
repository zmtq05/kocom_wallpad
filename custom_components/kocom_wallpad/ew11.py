"""Ew11 Wrapper."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_LIGHT, CONF_THERMO
from .kocom_packet import KocomPacket, PacketType, Device, Command
from .util import typed_data

_LOGGER = logging.getLogger(__name__)


class Ew11:
    """Ew11 Wrapper."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Ew11 Wrapper."""
        data = typed_data(entry)
        self._entry = entry
        self._hass = hass
        self._host = data[CONF_HOST]
        self._port = data[CONF_PORT]
        self._reader, self._writer = None, None
        self._send_queue = asyncio.Queue()

        self.light_controllers = {
            int(room): LightController(self, int(room), light_size)
            for room, light_size in data[CONF_LIGHT].items()
        }

        self.thermostats = {
            int(room): Thermostat(self, int(room)) for room in data[CONF_THERMO]
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

            if packet.type != PacketType.Seq:
                continue

            match packet.src:
                case (Device.Light, room):
                    self.light_controllers[room].update(packet.value)
                case (Device.Thermostat, room):
                    self.thermostats[room].update(packet.value)
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


class _Component:
    def __init__(self, ew11: Ew11) -> None:
        self._ew11: Ew11 = ew11
        self._callbacks: set[Callable[[], None]] = set()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Unregister callback."""
        self._callbacks.discard(callback)

    def update(self):
        for async_write_ha_state in self._callbacks:
            async_write_ha_state()


class LightController(_Component):
    """Control the lighting in a room."""

    def __init__(self, ew11: Ew11, room: int, light_size: int) -> None:
        super().__init__(ew11)
        self._room: int = room
        self._size: int = light_size
        self._state: list[int] = [0] * 8
        self._task = None

    async def _spawn_task_if_not_exists(self) -> None:
        # 일괄 점등, 소등용 batch
        # 하나의 조명마다 패킷을 보내는 대신
        # 일정시간 기다렸다가 하나로 모아서 보냄
        async def task():
            await asyncio.sleep(0.2)
            await self._ew11.send(
                KocomPacket.create(
                    (Device.Light, self._room),
                    Command.Set,
                    self._state,
                )
            )

        if not self._task:
            self._task = self._ew11._entry.async_create_task(
                self._ew11._hass, task(), "order"
            )

    async def turn_on(self, light: int) -> None:
        """Turn on the light."""
        self._state[light] = 0xFF
        await self._spawn_task_if_not_exists()

    async def turn_off(self, light: int) -> None:
        """Turn off the light."""
        self._state[light] = 0
        await self._spawn_task_if_not_exists()

    def is_on(self, light: int) -> bool:
        """Return true if the light is on."""
        return self._state[light] == 0xFF

    async def init(self) -> None:
        """Initialize the lights."""
        await self._ew11.send(
            KocomPacket.create((Device.Light, self._room), Command.Get)
        )

    def update(self, state: list[int]) -> None:
        self._state = state
        _LOGGER.info("Room %s Light: %s", self._room, self._state[: self._size])
        super().update()
        self._task = None


class Thermostat(_Component):
    def __init__(self, ew11: Ew11, room: int) -> None:
        super().__init__(ew11)
        self.room = room
        self._state = [0, 0, 0, 0, 0, 0, 0, 0]

    async def refresh(self) -> None:
        await self._ew11.send(
            KocomPacket.create(
                dst=(Device.Thermostat, self.room),
                cmd=Command.Get,
            )
        )

    @property
    def is_on(self) -> bool:
        return self._state[0] == 0x11

    @property
    def is_away(self) -> bool:
        return self._state[1] == 0x01

    @property
    def target_temp(self) -> int:
        return self._state[2]

    @property
    def current_temp(self) -> int:
        return self._state[4]

    async def set_temp(self, target_temp: int):
        self._state[2] = target_temp
        await self._send()

    async def on(self):
        self._state[0] = 0x11
        self._state[1] = 0x00
        await self._send()

    async def off(self):
        self._state[0] = 0x01
        self._state[1] = 0x00
        await self._send()

    async def away(self) -> None:
        self._state[0] = 0x11  # on
        self._state[1] = 0x01  # away
        await self._send()

    async def _send(self):
        await self._ew11.send(
            KocomPacket.create(
                (Device.Thermostat, self.room),
                Command.Set,
                self._state,
            )
        )

    def update(self, state: list[int]) -> None:
        self._state = list(state)

        _LOGGER.info(
            "Thermostat { room: %s, on: %s, away: %s, target: %s, current: %s }",
            self.room,
            self.is_on,
            self.is_away,
            self.target_temp,
            self.current_temp,
        )
        super().update()
