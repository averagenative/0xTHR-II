"""Parser for THR-II patch dumps (the "actual settings" or a stored user memory).

A dump is a stream of 6-byte tokens. Structural tokens open and close the "meta" and
"data" sections and the nested units (GuitarProc holding Amp, FX1 to FX4). Value tokens
are a 2-byte key, a 4-byte type marker, and a 4-byte value, or a length and UTF-8 bytes
for strings. Unit and parameter keys index into the amp's symbol table.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Callable

STRUCT_OPEN = bytes.fromhex("000000800200")
STRUCT_CLOSE = bytes.fromhex("020000800000")
UNIT_OPEN = bytes.fromhex("030000800700")
UNIT_CLOSE = bytes.fromhex("040000800000")
DATA = bytes.fromhex("010000000100")
META = bytes.fromhex("020000000100")
TOKEN_META = bytes.fromhex("0080020050535250")
TOKEN_DATA = bytes.fromhex("0080020054525447")

DUMP_BOOL = 1
DUMP_ENUM = 2
DUMP_FLOAT = 3
DUMP_STRING = 4

META_KEYS = {0: "name", 1: "tnid", 2: "unknown", 3: "tempo"}


class PatchError(ValueError):
    pass


@dataclass
class Unit:
    name: str
    type: str
    params: dict[str, object] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)


@dataclass
class Patch:
    meta: dict[str, object] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.meta.get("name", ""))

    def walk(self):
        """Yield (unit, parent) pairs depth-first."""
        stack = [(u, None) for u in reversed(self.units.values())]
        while stack:
            unit, parent = stack.pop()
            yield unit, parent
            stack.extend((u, unit) for u in reversed(unit.units.values()))

    def find(self, name: str) -> Unit | None:
        return next((u for u, _ in self.walk() if u.name == name), None)


def _u16(data: bytes, pos: int) -> int:
    return struct.unpack_from("<H", data, pos)[0]


def _u32(data: bytes, pos: int) -> int:
    return struct.unpack_from("<I", data, pos)[0]


def _value(vtype: int, raw: int) -> object:
    if vtype == DUMP_FLOAT:
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    if vtype == DUMP_BOOL:
        return bool(raw)
    return raw


def parse_patch(data: bytes, symbol: Callable[[int], str]) -> Patch:
    patch = Patch()
    section = None
    stack: list[Unit] = []
    pos = 0
    while pos + 6 <= len(data):
        token = data[pos:pos + 6]
        if token == STRUCT_OPEN:
            marker, octet = data[pos + 6:pos + 12], data[pos + 12:pos + 20]
            if marker == META and octet == TOKEN_META:
                section = "meta"
            elif marker == DATA and octet == TOKEN_DATA:
                section = "data"
            else:
                raise PatchError(f"Unknown structure at offset {pos}")
            pos += 20
        elif token == STRUCT_CLOSE:
            section = None
            pos += 6
        elif token == UNIT_OPEN:
            unit = Unit(symbol(_u16(data, pos + 6)), symbol(_u16(data, pos + 16)))
            (stack[-1].units if stack else patch.units)[unit.name] = unit
            stack.append(unit)
            pos += 30
        elif token == UNIT_CLOSE:
            if stack:
                stack.pop()
            pos += 6
        else:
            key, vtype = _u16(data, pos), data[pos + 4]
            if vtype == DUMP_STRING:
                length = _u32(data, pos + 6)
                value = data[pos + 10:pos + 10 + length].split(b"\x00")[0].decode("utf-8", "replace")
                pos += 10 + length
            else:
                value = _value(vtype, _u32(data, pos + 6))
                pos += 10
            if section == "meta":
                patch.meta[META_KEYS.get(key, f"meta_{key}")] = value
            elif stack:
                stack[-1].params[symbol(key)] = value
    return patch


NAME_LIMIT = 64


def dump_name(dump: bytes) -> str:
    """The name stored in a raw patch dump, or an empty string."""
    try:
        return str(parse_patch(dump, lambda key: str(key)).meta.get("name", ""))
    except (PatchError, struct.error):
        return ""


def rename_dump(dump: bytes, name: str) -> bytes:
    """Return a copy of a raw patch dump with its name changed.

    The name is the first value in the dump's meta section: a 2-byte key (0), the string
    type marker, a 4-byte length including the trailing NUL, and UTF-8 bytes.
    """
    prefix = len(STRUCT_OPEN) + len(META) + len(TOKEN_META)
    if dump[:6] != STRUCT_OPEN or dump[6:12] != META or dump[12:prefix] != TOKEN_META:
        raise PatchError("Unexpected dump layout; can't rename it.")
    key, vtype = _u16(dump, prefix), dump[prefix + 4]
    if key != 0 or vtype != DUMP_STRING:
        raise PatchError("The dump doesn't start with a name; can't rename it.")
    old_len = _u32(dump, prefix + 6)
    encoded = name.encode("utf-8")[:NAME_LIMIT - 1] + b"\x00"
    head = dump[:prefix + 6]
    tail = dump[prefix + 10 + old_len:]
    return head + struct.pack("<I", len(encoded)) + encoded + tail
