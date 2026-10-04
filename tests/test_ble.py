"""BLE-MIDI framing tests (no Bluetooth hardware needed)."""

import unittest

try:
    from thr2.ble import Reassembler, packetize
except ImportError:
    packetize = None


@unittest.skipIf(packetize is None, "PyGObject not installed")
class FramingTest(unittest.TestCase):
    def test_round_trip_long_sysex(self):
        message = bytes([0xF0]) + bytes(i % 0x80 for i in range(300)) + bytes([0xF7])
        for mtu in (23, 64, 185):
            packets = packetize(message, mtu)
            self.assertTrue(all(len(p) <= max(mtu - 3, 5) for p in packets), mtu)
            self.assertTrue(all(p[0] & 0x80 for p in packets))
            reassembler = Reassembler()
            out = [m for p in packets for m in reassembler.feed(p)]
            self.assertEqual(out, [message], mtu)

    def test_identity_reply_from_thr30ii(self):
        packet = bytes.fromhex("8080f07e7f0602000 10c2400020061002801 80f7".replace(" ", ""))
        self.assertEqual(Reassembler().feed(packet),
                         [bytes.fromhex("f07e7f060200010c2400020061002801f7")])

    def test_ignores_realtime_between_messages(self):
        out = Reassembler().feed(bytes([0x80, 0x80, 0xF8, 0x80, 0xF0, 0x01, 0x02, 0x80, 0xF7]))
        self.assertEqual(out, [bytes([0xF0, 0x01, 0x02, 0xF7])])


if __name__ == "__main__":
    unittest.main()
