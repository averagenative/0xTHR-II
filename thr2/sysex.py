"""SysEx framing for the Yamaha THR-II family.

The THR-II speaks Line 6's SysEx dialect. Every frame looks like:

    F0 | 00 01 0C | family model 4D | ab cnt part | last_hi last_lo | payload... | F7

* ``00 01 0C`` is the Line 6 manufacturer ID.
* ``family``/``model`` come from the identity reply (0x24/0x02 for a THR30II Wireless).
* ``ab`` selects one of two command groups, each with its own 7-bit frame counter ``cnt``.
* ``part`` numbers the frames of a multi-frame payload series.
* ``last_hi``/``last_lo`` hold the index of the last valid decoded payload byte, split
  into its high and low nibble.
* The payload is "bitbucket" coded: every 7 raw bytes travel as 8 bytes, where the
  first byte collects the 7 high bits.

Decoded payloads are mostly little-endian 32-bit words.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

SOX = 0xF0
EOX = 0xF7
LINE6 = bytes((0x00, 0x01, 0x0C))
SUB_ID = 0x4D

IDENTITY_REQUEST = bytes((0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7))


def bitbucket_encode(raw: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(raw), 7):
        group = raw[start:start + 7].ljust(7, b"\x00")
        bucket = 0
        for i, byte in enumerate(group):
            if byte & 0x80:
                bucket |= 1 << (6 - i)
        out.append(bucket)
        out.extend(byte & 0x7F for byte in group)
    return bytes(out)


def bitbucket_decode(coded: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(coded) - len(coded) % 8, 8):
        bucket = coded[start]
        for i, byte in enumerate(coded[start + 1:start + 8]):
            out.append(byte | 0x80 if bucket & (1 << (6 - i)) else byte)
    return bytes(out)


def words(*values: int) -> bytes:
    return struct.pack(f"<{len(values)}I", *(v & 0xFFFFFFFF for v in values))


def unpack_words(data: bytes) -> list[int]:
    n = len(data) // 4
    return list(struct.unpack(f"<{n}I", data[:n * 4]))


def float_word(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def word_float(word: int) -> float:
    return struct.unpack("<f", struct.pack("<I", word & 0xFFFFFFFF))[0]


@dataclass
class Frame:
    family: int
    model: int
    ab: int
    counter: int
    part: int
    payload: bytes
    sub_id: int = SUB_ID

    def encode(self) -> bytes:
        if not 1 <= len(self.payload) <= 256:
            raise ValueError(f"payload must be 1 to 256 bytes, got {len(self.payload)}")
        last = len(self.payload) - 1
        header = LINE6 + bytes((
            self.family, self.model, self.sub_id,
            self.ab, self.counter & 0x7F, self.part,
            last >> 4, last & 0x0F,
        ))
        return bytes((SOX,)) + header + bitbucket_encode(self.payload) + bytes((EOX,))

    @property
    def words(self) -> list[int]:
        return unpack_words(self.payload)

    @classmethod
    def decode(cls, message: bytes) -> Frame | None:
        if len(message) < 13 or message[0] != SOX or message[-1] != EOX:
            return None
        if message[1:4] != LINE6:
            return None
        family, model, sub_id, ab, counter, part, last_hi, last_lo = message[4:12]
        last = (last_hi << 4) | last_lo
        payload = bitbucket_decode(message[12:-1])[:last + 1]
        return cls(family, model, ab, counter, part, payload, sub_id)


def parse_identity(message: bytes) -> dict | None:
    """Parse a universal identity reply: F0 7E dev 06 02 mfr(3) fam(2) model(2) ver(4) F7."""
    if len(message) < 17 or message[:2] != b"\xf0\x7e" or message[3:5] != b"\x06\x02":
        return None
    v = message[12:16]
    return {
        "manufacturer": message[5:8].hex(),
        "family": message[8] | message[9] << 8,
        "model": message[10] | message[11] << 8,
        "version": f"{v[3]}.{v[2]}.{v[1]}{chr(v[0])}",
        "firmware_word": v[3] << 24 | int(f"{v[2]:d}", 16) << 16 | v[1] << 8 | v[0],
    }
