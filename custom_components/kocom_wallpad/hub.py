"""Ew11 Wrapper."""

import asyncio
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_FAN, CONF_GAS, CONF_LIGHT, CONF_THERMO
from .kocom_packet import KocomPacket, PacketType, Device, Command
from .util import typed_data

_LOGGER = logging.getLogger(__name__)


class Hub:
    """Hub for managing connections and devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Hub."""
        data = typed_data(entry)
        self._entry = entry
        self._hass = hass
        self._host = data[CONF_HOST]
        self._port = data[CONF_PORT]
        self._reader, self._writer = None, None
        self._send_queue: asyncio.Queue[KocomPacket] = asyncio.Queue()

        self.light_controllers: dict[int, LightController] = {
            int(room): LightController(self, int(room), light_size)
            for room, light_size in data[CONF_LIGHT].items()
        }

        self.thermostats: dict[int, Thermostat] = {
            int(room): Thermostat(self, int(room)) for room in data[CONF_THERMO]
        }

        if data[CONF_FAN]:
            self.fan = Fan(self)
        else:
            self.fan = None

        if data[CONF_GAS]:
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

            if packet.type == PacketType.Ack:
                # ignore
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
        """Send a packet."""
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
        """Write HA state."""
        for async_write_ha_state in self._callbacks:
            async_write_ha_state()

    async def refresh(self) -> None:
        """Refresh the device."""
        await self._hub.send(self._device, Command.Get)


class LightController(_HubChild):
    """Control the lights."""

    def __init__(self, hub: Hub, room: int, light_size: int) -> None:
        """Initialize the LightController."""
        super().__init__(hub, (Device.Light, room))
        self.room: int = room
        self.size: int = light_size
        # 0~7 - light; on: FF / off: 00
        self._state: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]
        self._task = None

    async def _set(self) -> None:
        # 일괄 점등, 소등용 batch
        # 하나의 조명마다 패킷을 보내는 대신
        # 일정시간 기다렸다가 하나로 모아서 보냄
        async def task():
            await asyncio.sleep(0.2)
            await self._hub.send(
                self._device,
                Command.Set,
                self._state,
            )

        if not self._task:
            self._task = self._hub._entry.async_create_task(
                self._hub._hass, task(), "set"
            )

    async def turn_on(self, n: int) -> None:
        """Turn on the light."""
        self._state[n] = 0xFF
        await self._set()

    async def turn_off(self, n: int) -> None:
        """Turn off the light."""
        self._state[n] = 0x00
        await self._set()

    def is_on(self, light: int) -> bool:
        """Return true if the light is on."""
        return self._state[light] == 0xFF

    async def _handle_packet(self, packet: KocomPacket) -> None:
        self._state = packet.value
        state_str = ", ".join(
            f"{i+1}: on" if x == 0xFF else f"{i+1}: off"
            for i, x in enumerate(self._state[: self.size])
        )
        _LOGGER.info("Light: { room: %s, %s }", self.room, state_str)
        await self.write_ha_state()
        self._task = None


class Thermostat(_HubChild):
    """Control the thermostat."""

    def __init__(self, ew11: Hub, room: int) -> None:
        """Initialize the Thermostat."""
        super().__init__(ew11, (Device.Thermostat, room))
        # 0+1 - mode; on: 11 00 / off: 01 00 / away: 11 01
        # 2 - target temperature
        # 4 - current temperature
        self._state = [0, 0, 0, 0, 0, 0, 0, 0]
        self.room = room

    @property
    def is_on(self) -> bool:
        """Return true if the thermostat is on."""
        return self._state[0] == 0x11

    @property
    def is_away(self) -> bool:
        """Return true if the thermostat mode is away."""
        return self._state[1] == 0x01

    @property
    def target_temp(self) -> int:
        """Return the target temperature."""
        return self._state[2]

    @property
    def current_temp(self) -> int:
        """Return the current temperature."""
        return self._state[4]

    async def set_temp(self, target_temp: int) -> None:
        """Set the target temperature."""
        self._state[2] = target_temp
        await self._send()

    async def on(self) -> None:
        """Turn on the thermostat."""
        self._state[0] = 0x11
        self._state[1] = 0x00
        await self._send()

    async def off(self) -> None:
        """Turn off the thermostat."""
        self._state[0] = 0x01
        self._state[1] = 0x00
        await self._send()

    async def away(self) -> None:
        """Set the thermostat to away mode."""
        self._state[0] = 0x11
        self._state[1] = 0x01
        await self._send()

    async def _send(self) -> None:
        await self._hub.send(
            self._device,
            Command.Set,
            self._state,
        )

    async def _handle_packet(self, packet: KocomPacket) -> None:
        self._state = packet.value

        _LOGGER.info(
            "Thermostat { room: %s, on: %s, away: %s, target_temp: %s, current_temp: %s }",
            self.room,
            self.is_on,
            self.is_away,
            self.target_temp,
            self.current_temp,
        )
        await self.write_ha_state()


class Fan(_HubChild):
    """Control the fan."""

    def __init__(self, ew11: Hub) -> None:
        """Initialize the Fan."""
        super().__init__(ew11, Device.Fan)
        # 0 - mode; on: 11 / off: 00
        # 1 - fixed(01)
        # 2 - step; 40, 80, C0
        self._state = [0, 0x01, 0, 0, 0, 0, 0, 0]

    async def _send(self) -> None:
        await self._hub.send(Device.Fan, Command.Set, self._state)

    @property
    def is_on(self) -> bool:
        """Return true if the fan is on."""
        return self._state[0] == 0x11

    @property
    def step(self) -> int:
        """Return the current step."""
        return self._state[2] // 0x40

    async def set_step(self, step: int) -> None:
        """Set the fan speed."""
        if step == 0:
            self._state[0] = 0x00
        else:
            self._state[0] = 0x11
            self._state[2] = step * 0x40
        await self._send()

    async def _handle_packet(self, packet: KocomPacket) -> None:
        self._state = packet.value
        _LOGGER.info("Fan { on: %s, step: %s }", self.is_on, self.step)
        await self.write_ha_state()


class GasValve(_HubChild):
    """Control the gas valve."""

    def __init__(self, ew11: Hub) -> None:
        """Initialize the GasValve."""
        super().__init__(ew11, Device.GasValve)
        self.is_locked = False

    async def lock(self) -> None:
        """Lock the gas valve."""
        await self._hub.send(Device.GasValve, Command.Lock)

    async def _handle_packet(self, packet: KocomPacket) -> None:
        match packet.cmd:
            case Command.Lock:
                self.is_locked = True
            case Command.Unlock:
                self.is_locked = False
        _LOGGER.info("GasValve { locked: %s }", self.is_locked)
        await self.write_ha_state()
