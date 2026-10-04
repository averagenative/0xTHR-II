"""Round-trip tests built from worked examples in SYSEX_PROTOCOL_THR30II.pdf."""

import unittest

from thr2.sysex import Frame, bitbucket_decode, bitbucket_encode, parse_identity, word_float


def hexbytes(text: str) -> bytes:
    return bytes.fromhex(text.replace(" ", ""))


class BitbucketTest(unittest.TestCase):
    def test_round_trip(self):
        raw = bytes(range(256))
        self.assertEqual(bitbucket_decode(bitbucket_encode(raw))[:256], raw)

    def test_high_bits_cleared(self):
        self.assertTrue(all(b < 0x80 for b in bitbucket_encode(bytes([0xFF] * 21))))


class FrameTest(unittest.TestCase):
    def test_decode_global_parameter_change(self):
        msg = hexbytes(
            "f0 00 01 0c 24 02 4d 00 0f 00 00 0f 78 7f 7f 7f 7f 55 01 00"
            " 03 00 04 00 00 00 16 7f 40 19 3e 00 00 00 00 00 f7"
        )
        frame = Frame.decode(msg)
        self.assertEqual(frame.words, [0xFFFFFFFF, 0x155, 0x4, 0x3E99FF96])
        self.assertEqual((frame.ab, frame.counter, frame.part), (0, 0x0F, 0))

    def test_set_master_body_round_trip(self):
        msg = hexbytes(
            "f0 00 01 0c 22 02 4d 00 5b 00 00 0f 00 0c 01 00 00 4c 00 00"
            " 03 00 04 00 00 00 16 67 40 7b 3e 00 00 00 00 00 f7"
        )
        frame = Frame.decode(msg)
        self.assertEqual(frame.words, [0x10C, 0x4C, 4, 0x3EFBE796])
        self.assertAlmostEqual(word_float(frame.words[3]) * 100, 49.2, places=3)
        self.assertEqual(frame.encode(), msg)

    def test_activation_key_body(self):
        msg = hexbytes("f0 00 01 0c 24 02 4d 00 02 00 00 03 28 72 4d 54 5d 00 00 00 f7")
        self.assertEqual(Frame.decode(msg).words, [0xDD54CD72])
        rebuilt = Frame(0x24, 0x02, ab=0, counter=2, part=0, payload=Frame.decode(msg).payload)
        self.assertEqual(rebuilt.encode(), msg)

    def test_rejects_foreign_sysex(self):
        self.assertIsNone(Frame.decode(hexbytes("f0 7e 7f 06 01 f7")))


class UploadHeaderTest(unittest.TestCase):
    def test_header_matches_protocol_notes_example(self):
        from thr2.sysex import words
        payload = words(0x0D, 0x26E, 2, 0x266, 0, 1, 0)
        frame = Frame(0x22, 0x02, ab=1, counter=0x0B, part=0, payload=payload)
        expected = hexbytes(
            "f0 00 01 0c 22 02 4d 01 0b 00 01 0b 00 0d 00 00 00 6e 02 00 00 00 02 00 00 00 66 02"
            " 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 00 f7"
        )
        self.assertEqual(frame.encode(), expected)


class IdentityTest(unittest.TestCase):
    def test_thr30ii_wireless_1_40_0a(self):
        ident = parse_identity(hexbytes("f0 7e 7f 06 02 00 01 0c 24 00 02 00 61 00 28 01 f7"))
        self.assertEqual(ident["version"], "1.40.0a")
        self.assertEqual(ident["firmware_word"], 0x01400061)
        self.assertEqual((ident["family"], ident["model"]), (0x24, 0x02))


if __name__ == "__main__":
    unittest.main()
