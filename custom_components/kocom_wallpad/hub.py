"""Kocom Wallpad Hub and Device Controllers.

This module provides the core functionality for communicating with Kocom Wallpad devices
through an EW11 network interface. It manages the connection, packet handling, and
state management for all supported device types including:
- Lights
- Thermostats
- Ventilation fans
- Gas valves

The Hub class serves as the central coordinator, while individual device controllers
handle device-specific operations.
"""

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
    """Central hub for managing Kocom Wallpad device connections and communications.

    This class handles the network connection to the EW11 interface and coordinates
    all communication with the various Kocom devices. It maintains the connection,
    processes incoming packets, and manages the outgoing packet queue.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Kocom Wallpad hub.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry containing connection and device settings.
        """
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
        """Establish connection to the EW11 network interface."""
        self._reader, self._writer = await asyncio.open_connection(
            host=self._host, port=self._port
        )
        _LOGGER.info("Connected to %s", self._host)

    async def disconnect(self) -> None:
        """Close the connection to the EW11 network interface."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._reader, self._writer = None, None
            _LOGGER.info("Disconneted from %s", self._host)

    async def read_loop(self) -> None:
        """Continuously listen for and process incoming packets.

        This coroutine runs indefinitely, reading packets from the network connection
        and dispatching them to the appropriate device controllers.
        """
        _LOGGER.debug("Read loop started")
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
        _LOGGER.debug("Read loop finished")

    async def send_loop(self) -> None:
        """Continuously process and send outgoing packets.

        This coroutine runs indefinitely, taking packets from the send queue
        and transmitting them to the EW11 interface. It includes a delay between
        packets to prevent collisions.
        """
        _LOGGER.debug("Send loop started")
        while self._writer is not None:
            packet = await self._send_queue.get()
            _LOGGER.debug("->(%s) %s", self._host, packet)
            self._writer.write(packet)
            await self._writer.drain()
            await asyncio.sleep(1)  # prevent packet collision
            self._send_queue.task_done()
        _LOGGER.debug("Send loop finished")

    async def send(
        self,
        dst: Device | tuple[Device, int],
        command: Command,
        value: list[int] = [0, 0, 0, 0, 0, 0, 0, 0],
    ) -> None:
        """Queue a packet for sending to a device.

        Args:
            dst: The target device or (device, room) tuple.
            command: The command to send.
            value: The command parameters (defaults to all zeros).
        """
        await self._send_queue.put(KocomPacket.create(dst, command, value))


class _HubChild:
    """Base class for all device controllers.

    Provides common functionality for device state management and callbacks.
    All specific device controllers (Light, Thermostat, etc.) inherit from this class.
    """

    def __init__(self, hub: Hub, device: Device | tuple[Device, int]) -> None:
        """Initialize a device controller.

        Args:
            hub: The Hub instance this device belongs to.
            device: The device type or (device, room) tuple this controller manages.
        """
        self._hub = hub
        self._device = device
        self._callbacks: set[Callable[[], None]] = set()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for state updates.

        Args:
            callback: The callback function to be called when device state changes.
        """
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered callback.

        Args:
            callback: The callback function to remove.
        """
        self._callbacks.discard(callback)

    async def write_ha_state(self):
        """Notify Home Assistant of state changes by calling all registered callbacks."""
        for async_write_ha_state in self._callbacks:
            async_write_ha_state()

    async def refresh(self) -> None:
        """Request current state from the device."""
        await self._hub.send(self._device, Command.Get)


class LightController(_HubChild):
    """Controller for Kocom light devices.

    Manages multiple lights within a room, supporting individual on/off control
    and batch operations for efficiency.
    """

    def __init__(self, hub: Hub, room: int, light_size: int) -> None:
        """Initialize a light controller for a specific room.

        Args:
            hub: The Hub instance this controller belongs to.
            room: The room number this controller manages.
            light_size: The number of lights in this room.
        """
        super().__init__(hub, (Device.Light, room))
        self.room: int = room
        self.size: int = light_size
        # 0~7 - light; on: FF / off: 00
        self._state: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]
        self._task = None

    async def _set(self) -> None:
        """Queue a batch update for light states.

        This method implements a small delay to allow multiple rapid changes
        to be combined into a single packet, improving efficiency.
        """
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
        """Turn on a specific light.

        Args:
            n: The index of the light to turn on.
        """
        self._state[n] = 0xFF
        await self._set()

    async def turn_off(self, n: int) -> None:
        """Turn off a specific light.

        Args:
            n: The index of the light to turn off.
        """
        self._state[n] = 0x00
        await self._set()

    def is_on(self, light: int) -> bool:
        """Check if a specific light is on.

        Args:
            light: The index of the light to check.

        Returns:
            bool: True if the light is on, False otherwise.
        """
        return self._state[light] == 0xFF

    async def _handle_packet(self, packet: KocomPacket) -> None:
        """Process an incoming packet from the device.

        Updates the internal state and notifies Home Assistant of any changes.

        Args:
            packet: The received packet containing light states.
        """
        self._state = packet.value
        state_str = ", ".join(
            f"{i+1}: on" if x == 0xFF else f"{i+1}: off"
            for i, x in enumerate(self._state[: self.size])
        )
        _LOGGER.info("Light: { room: %s, %s }", self.room, state_str)
        await self.write_ha_state()
        self._task = None


class Thermostat(_HubChild):
    """Controller for Kocom thermostat devices.

    Manages temperature control and operation modes for a single room's heating system.
    Supports normal, away, and off modes with temperature control.
    """

    def __init__(self, ew11: Hub, room: int) -> None:
        """Initialize a thermostat controller for a specific room.

        Args:
            ew11: The Hub instance this controller belongs to.
            room: The room number this controller manages.
        """
        super().__init__(ew11, (Device.Thermostat, room))
        # 0+1 - mode; on: 11 00 / off: 01 00 / away: 11 01
        # 2 - target temperature
        # 4 - current temperature
        self._state = [0, 0, 0, 0, 0, 0, 0, 0]
        self.room = room

    @property
    def is_on(self) -> bool:
        """Check if the thermostat is currently on.

        Returns:
            bool: True if the thermostat is on, False if off.
        """
        return self._state[0] == 0x11

    @property
    def is_away(self) -> bool:
        """Check if the thermostat is in away mode.

        Returns:
            bool: True if in away mode, False otherwise.
        """
        return self._state[1] == 0x01

    @property
    def target_temp(self) -> int:
        """Get the target temperature setting.

        Returns:
            int: The target temperature in degrees Celsius.
        """
        return self._state[2]

    @property
    def current_temp(self) -> int:
        """Get the current room temperature.

        Returns:
            int: The current temperature in degrees Celsius.
        """
        return self._state[4]

    async def set_temp(self, target_temp: int) -> None:
        """Set the target temperature.

        Args:
            target_temp: The desired temperature in degrees Celsius.
        """
        self._state[2] = target_temp
        await self._send()

    async def on(self) -> None:
        """Turn on the thermostat in normal mode."""
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
        """Send the current state to the device."""
        await self._hub.send(
            self._device,
            Command.Set,
            self._state,
        )

    async def _handle_packet(self, packet: KocomPacket) -> None:
        """Process an incoming packet from the device.

        Updates the internal state and notifies Home Assistant of any changes.

        Args:
            packet: The received packet containing thermostat state.
        """
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
    """Controller for Kocom ventilation fan.

    Manages the ventilation fan system with multiple speed levels.
    """

    def __init__(self, ew11: Hub) -> None:
        """Initialize the ventilation fan controller.

        Args:
            ew11: The Hub instance this controller belongs to.
        """
        super().__init__(ew11, Device.Fan)
        # 0 - mode; on: 11 / off: 00
        # 1 - fixed(01)
        # 2 - step; 40, 80, C0
        self._state = [0, 0x01, 0, 0, 0, 0, 0, 0]

    async def _send(self) -> None:
        """Send the current state to the device."""
        await self._hub.send(Device.Fan, Command.Set, self._state)

    @property
    def is_on(self) -> bool:
        """Check if the fan is currently running.

        Returns:
            bool: True if the fan is on, False if off.
        """
        return self._state[0] == 0x11

    @property
    def step(self) -> int:
        """Get the current fan speed level.

        Returns:
            int: The current speed level (0-3).
        """
        return self._state[2] // 0x40

    async def set_step(self, step: int) -> None:
        """Set the fan speed level.

        Args:
            step: The desired speed level (0-3, where 0 is off).
        """
        if step == 0:
            self._state[0] = 0x00
        else:
            self._state[0] = 0x11
            self._state[2] = step * 0x40
        await self._send()

    async def _handle_packet(self, packet: KocomPacket) -> None:
        """Process an incoming packet from the device.

        Updates the internal state and notifies Home Assistant of any changes.

        Args:
            packet: The received packet containing fan state.
        """
        self._state = packet.value
        _LOGGER.info("Fan { on: %s, step: %s }", self.is_on, self.step)
        await self.write_ha_state()


class GasValve(_HubChild):
    """Controller for Kocom gas valve.

    Manages the gas valve safety system with lock/unlock status monitoring.
    For safety reasons, only supports remote locking (closing) of the valve.
    """

    def __init__(self, ew11: Hub) -> None:
        """Initialize the gas valve controller.

        Args:
            ew11: The Hub instance this controller belongs to.
        """
        super().__init__(ew11, Device.GasValve)
        self.is_locked = False

    async def lock(self) -> None:
        """Lock (close) the gas valve for safety."""
        await self._hub.send(Device.GasValve, Command.Lock)

    async def _handle_packet(self, packet: KocomPacket) -> None:
        """Process an incoming packet from the device.

        Updates the internal state and notifies Home Assistant of any changes.

        Args:
            packet: The received packet containing valve state.
        """
        match packet.cmd:
            case Command.Lock:
                self.is_locked = True
            case Command.Unlock:
                self.is_locked = False
        _LOGGER.info("GasValve { locked: %s }", self.is_locked)
        await self.write_ha_state()
