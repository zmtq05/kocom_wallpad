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


class Hub:

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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

        if data["fan"]:
            self.fan = Fan(self)
        else:
            self.fan = None

        if data["gas"]:
            self.gas_valve = GasValve(self)
        else:
            self.gas_valve = None

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
                    await self.light_controllers[room]._handle_packet(packet)
                case (Device.Thermostat, room):
                    await self.thermostats[room]._handle_packet(packet)
                case (Device.Fan, _):
                    if self.fan:
                        await self.fan._handle_packet(packet)
                case (Device.GasValve, _):
                    if self.gas_valve:
                        await self.gas_valve._handle_packet(packet)
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

    async def send(
        self,
        dst: Device | tuple[Device, int],
        command: Command,
        value: list[int] = [0, 0, 0, 0, 0, 0, 0, 0],
    ) -> None:
        await self._send_queue.put(KocomPacket.create(dst, command, value))


class _HubChild:
    def __init__(self, hub: Hub, device: Device | tuple[Device, int]) -> None:
        self._hub = hub
        self._device = device
        self._callbacks: set[Callable[[], None]] = set()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Unregister callback."""
        self._callbacks.discard(callback)

    async def write_ha_state(self):
        for async_write_ha_state in self._callbacks:
            async_write_ha_state()

    async def refresh(self) -> None:
        await self._hub.send(self._device, Command.Get)


class LightController(_HubChild):
    """Control the lights."""

    def __init__(self, hub: Hub, room: int, light_size: int) -> None:
        super().__init__(hub, (Device.Light, room))
        self._room: int = room
        self._size: int = light_size
        self._state: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]
        self._task = None

    async def _set(self) -> None:
        # 일괄 점등, 소등용 batch
        # 하나의 조명마다 패킷을 보내는 대신
        # 일정시간 기다렸다가 하나로 모아서 보냄
        async def task():
            await asyncio.sleep(0.2)
            await self._hub.send(
                (Device.Light, self._room),
                Command.Set,
                self._state,
            )

        if not self._task:
            self._task = self._hub._entry.async_create_task(
                self._hub._hass, task(), "set"
            )

    async def turn_on(self, light: int) -> None:
        """Turn on the light."""
        self._state[light] = 0xFF
        await self._set()

    async def turn_off(self, light: int) -> None:
        """Turn off the light."""
        self._state[light] = 0x00
        await self._set()

    def is_on(self, light: int) -> bool:
        """Return true if the light is on."""
        return self._state[light] == 0xFF

    async def _handle_packet(self, packet: KocomPacket) -> None:
        self._state = packet.value
        _LOGGER.info("Room %s Light: %s", self._room, self._state[: self._size])
        await self.write_ha_state()
        self._task = None


class Thermostat(_HubChild):
    def __init__(self, ew11: Hub, room: int) -> None:
        super().__init__(ew11, (Device.Thermostat, room))
        self._state = [0, 0, 0, 0, 0, 0, 0, 0]
        self.room = room

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
        await self._hub.send(
            self._device,
            Command.Set,
            self._state,
        )

    async def _handle_packet(self, packet: KocomPacket) -> None:
        self._state = packet.value

        _LOGGER.info(
            "Thermostat { room: %s, on: %s, away: %s, target: %s, current: %s }",
            self.room,
            self.is_on,
            self.is_away,
            self.target_temp,
            self.current_temp,
        )
        await self.write_ha_state()


class Fan(_HubChild):
    def __init__(self, ew11: Hub) -> None:
        super().__init__(ew11, Device.Fan)
        self._state = [0, 0x01, 0, 0, 0, 0, 0, 0]

    async def _send(self) -> None:
        await self._hub.send(Device.Fan, Command.Set, self._state)

    @property
    def is_on(self) -> bool:
        return self._state[0] == 0x11

    @property
    def step(self) -> int:
        return self._state[2] // 0x40

    async def set_step(self, step: int):
        if step == 0:
            self._state[0] = 0x00
        else:
            self._state[0] = 0x11
            self._state[2] = step * 0x40
        await self._send()

    async def _handle_packet(self, packet: KocomPacket):
        self._state = packet.value
        await self.write_ha_state()


class GasValve(_HubChild):
    def __init__(self, ew11: Hub) -> None:
        super().__init__(ew11, Device.GasValve)
        self.is_locked = False

    async def lock(self) -> None:
        await self._hub.send(Device.GasValve, Command.Lock)

    async def _handle_packet(self, packet: KocomPacket) -> None:
        match packet.cmd:
            case Command.Lock:
                self.is_locked = True
            case Command.Unlock:
                self.is_locked = False
        await self.write_ha_state()
