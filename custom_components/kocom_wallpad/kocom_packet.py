"""Kocom Packet."""

from typing import Self

_HEADER = b"\xaa\x55"
_FOOTER = b"\x0d\x0d"


class _PacketPart(bytes):
    def __str__(self) -> str:
        return type(self).__name__


class PacketType(_PacketPart):
    @staticmethod
    def parse(value: bytes):
        if value == b"\x30\xbc":
            return Seq()
        if value == b"\x30\xdc":
            return Ack()
        raise ValueError("Invalid packet type")


class Seq(PacketType):
    def __new__(cls, value: int = 0) -> Self:
        return super().__new__(cls, bytes([0x30, 0xBC + value]))


class Ack(PacketType):
    def __new__(cls, value: int = 0) -> Self:
        return super().__new__(cls, bytes([0x30, 0xDC + value]))


class Device(_PacketPart):
    @staticmethod
    def parse(value: bytes):
        if value == b"\x01\x00":
            return Wallpad()
        if value[0] == 0x0E:
            return Light(value[1])
        raise ValueError("Invalid device")


class Wallpad(Device):
    def __new__(cls) -> Self:
        return super().__new__(cls, bytes([0x01, 0x00]))


class Light(Device):
    __match_args__ = ("room",)

    def __new__(cls, room: int) -> Self:
        return super().__new__(cls, bytes([0x0E, 0x00 + room]))

    def __init__(self, room: int = 0) -> None:
        self.room = room


class Command(_PacketPart):
    @staticmethod
    def parse(value: bytes):
        if value == b"\x00":
            return Set()
        if value == b"\x3a":
            return Get()
        raise ValueError("Invalid command")


class Set(Command):
    def __new__(cls) -> Self:
        return super().__new__(cls, b"\x00")


class Get(Command):
    def __new__(cls) -> Self:
        return super().__new__(cls, b"\x3a")


class Value(_PacketPart):
    @classmethod
    def from_state(cls, state: list[bool]) -> Self:
        return cls(bytes([0xFF if x else 0x00 for x in state]))

    @classmethod
    def empty(cls) -> Self:
        return cls(bytes([0] * 8))

    def __str__(self) -> str:
        return self.hex(" ").upper()


class KocomPacket(bytes):
    @classmethod
    def create(cls, dst: Device, cmd: Command, value: Value) -> Self:
        src = Wallpad()  # src of send packet is always Wallpad
        type = Seq()  # type of send packet is always Sequence
        body = type + b"\x00" + dst + src + cmd + value
        checksum = sum(body) % 256
        return cls(_HEADER + body + bytes([checksum]) + _FOOTER)

    def __init__(self, packet: bytes) -> None:
        assert len(packet) == 21, "Invalid packet length"
        assert packet[:2] == _HEADER, "Invalid header"
        assert packet[-2:] == _FOOTER, "Invalid footer"

        self.type = PacketType.parse(packet[2:4])
        self.dst = Device.parse(packet[5:7])
        self.src = Device.parse(packet[7:9])
        self.cmd = Command.parse(packet[9:10])
        self.value = Value(packet[10:18])
        self.checksum: int = packet[18]

    def __str__(self) -> str:
        return self.hex(" ").upper()
