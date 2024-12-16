"""Kocom Packet."""

from enum import IntEnum
from typing import Self

_HEADER = [0xAA, 0x55]
_FOOTER = [0x0D, 0x0D]


class PacketType(IntEnum):
    """Packet type."""

    Seq = 0xBC
    Ack = 0xDC


class Device(IntEnum):
    """Device type."""

    Wallpad = 0x01
    Light = 0x0E
    Thermostat = 0x36
    GasValve = 0x2C
    Fan = 0x48
    Elevator = 0x44
    Outlet = 0x3B
    AirConditioner = 0x39
    AirQuality = 0x98


class Command(IntEnum):
    """Command type."""

    Get = 0x3A
    Set = 0x00
    Lock = 0x02  # Gas valve only
    Unlock = 0x01  # Gas valve only
    Elevator = 0x01


class KocomPacket(bytes):
    """Kocom packet."""

    @classmethod
    def create(
        cls,
        dst: tuple[Device, int] | Device,
        cmd: Command,
        value: list[int] = [0, 0, 0, 0, 0, 0, 0, 0],
    ) -> Self:
        """Create a packet."""
        if isinstance(dst, Device):
            dst = (dst, 0x00)

        type = (0x30, PacketType.Seq)
        src = (Device.Wallpad, 0x00)

        body = [*type, 0x00, *dst, *src, cmd, *value]
        checksum = sum(body) % 256
        body.append(checksum)
        return cls(bytes(_HEADER + body + _FOOTER))

    @classmethod
    def create_rare(
        cls,
        type: tuple[int, int],
        dst: tuple[Device, int] | Device,
        src: tuple[Device, int] | Device,
        cmd: Command,
        value: list[int] = [0, 0, 0, 0, 0, 0, 0, 0],
    ) -> Self:
        """Create a rare packet."""
        if isinstance(dst, Device):
            dst = (dst, 0x00)
        if isinstance(src, Device):
            src = (src, 0x00)

        body = [*type, 0x00, *dst, *src, cmd, *value]
        checksum = sum(body) % 256
        body.append(checksum)
        return cls(bytes(_HEADER + body + _FOOTER))

    def __init__(self, packet: bytes) -> None:
        """Initialize the packet."""
        assert len(packet) == 21, "Invalid packet length"
        assert packet[:2] == b"\xaa\x55", "Invalid header"
        assert packet[-2:] == b"\x0d\x0d", "Invalid footer"

        if packet[3] in (0xBC, 0xBD, 0xBE):
            self.type = PacketType.Seq
        elif packet[3] in (0xDC, 0xDD, 0xDE):
            self.type = PacketType.Ack
        else:
            raise AssertionError("Invalid type")
        self.dst: tuple[Device, int] = (Device(packet[5]), packet[6])
        self.src: tuple[Device, int] = (Device(packet[7]), packet[8])
        self.cmd: Command = Command(packet[9])
        self.value: list[int] = list(packet[10:18])
        self.checksum: int = packet[18]

    def __str__(self) -> str:
        """Return the packet as a string."""
        return self.hex(" ").upper()
