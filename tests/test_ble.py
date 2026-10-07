"""BLE-MIDI framing tests (no Bluetooth hardware needed)."""

import unittest
from unittest import mock

try:
    from thr2 import ble
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


class FakeBus:
    def __init__(self):
        self.calls = []

    def call_sync(self, _name, _path, interface, method, params, *_rest):
        self.calls.append((interface, method, params.unpack() if params is not None else None))


@unittest.skipIf(packetize is None, "PyGObject not installed")
class ReleaseTest(unittest.TestCase):
    def release(self, connected: bool, trusted: bool):
        info = {"device": "/org/bluez/hci0/dev_X", "name": "LE_THRII", "connected": connected, "trusted": trusted}
        bus = FakeBus()
        with mock.patch.object(ble, "find_thr", return_value=info), mock.patch.object(ble, "_bus", return_value=bus):
            return ble.release(), bus.calls

    def test_untrusts_before_disconnecting(self):
        dropped, calls = self.release(connected=True, trusted=True)
        self.assertTrue(dropped)
        self.assertEqual([c[1] for c in calls], ["Set", "Disconnect"])
        self.assertEqual(calls[0][2], ("org.bluez.Device1", "Trusted", False))

    def test_untrusts_an_idle_link_without_disconnecting(self):
        dropped, calls = self.release(connected=False, trusted=True)
        self.assertFalse(dropped)
        self.assertEqual([c[1] for c in calls], ["Set"])

    def test_leaves_an_untrusted_idle_amp_alone(self):
        self.assertEqual(self.release(connected=False, trusted=False), (False, []))


if __name__ == "__main__":
    unittest.main()
