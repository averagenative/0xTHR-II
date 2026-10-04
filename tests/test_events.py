"""Event decoding, replaying change reports captured from a THR30II Wireless on 1.40.0a."""

import json
import unittest
from pathlib import Path

from thr2.client import THR
from thr2.sysex import Frame


def hexbytes(text: str) -> bytes:
    return bytes.fromhex(text.replace(" ", ""))


def fake_thr() -> THR:
    symbols = [f"sym{i:x}" for i in range(0x200)]
    symbols[0x10C], symbols[0x13C], symbols[0x107], symbols[0xAF] = "Amp", "GuitarProc", "SpkSimType", "AmpModel"
    return THR(midi=None, symbols=symbols)


class EventTest(unittest.TestCase):
    def test_unit_type_change(self):
        msg = hexbytes("f0 00 01 0c 24 02 4d 00 40 00 00 0f 00 03 00 00 00 08 00 00 02 00 0c 01 00 00 2f 00 00 00 00 00 00 00 00 00 f7")
        thr = fake_thr()
        thr._queue_event(Frame.decode(msg), msg)
        event = thr.events.get_nowait()
        self.assertEqual((event.opcode, event.unit, event.param, event.value), (3, "Amp", "type", "AmpModel"))

    def test_cabinet_change(self):
        msg = hexbytes(
            "f0 00 01 0c 24 02 4d 00 41 00 01 07 00 04 00 00 00 10 00 00 00 00 3c 01 00 00"
            " 07 01 00 00 00 04 00 00 00 00 20 00 00 40 00 00 00 00 f7"
        )
        thr = fake_thr()
        thr._queue_event(Frame.decode(msg), msg)
        event = thr.events.get_nowait()
        self.assertEqual((event.unit, event.param, event.value), ("GuitarProc", "SpkSimType", 4.0))


if __name__ == "__main__":
    unittest.main()
