"""Client behavior against a scripted transport (no amp needed)."""

import unittest

from thr2.client import THR, THRError
from thr2.sysex import Frame, words


class ScriptedMidi:
    kind = "USB"

    def __init__(self):
        self.replies: list[bytes] = []

    def write(self, data: bytes) -> None:
        pass

    def receive(self, timeout=None):
        return self.replies.pop(0) if self.replies else None


def answer(ok: bool = True) -> bytes:
    return Frame(0x24, 0x02, 0, 0, 0, words(0x01, 4, 0 if ok else 0xFFFFFFFF)).encode()


class MissedAnswerTest(unittest.TestCase):
    def test_counts_unanswered_commands_until_an_answer_arrives(self):
        midi = ScriptedMidi()
        thr = THR(midi=midi)
        for expected in (1, 2):
            with self.assertRaises(THRError):
                thr.command(0, 0x01, timeout=0.01)
            self.assertEqual(thr.missed, expected)
        midi.replies.append(answer())
        self.assertTrue(thr.command(0, 0x01, timeout=0.01).ok)
        self.assertEqual(thr.missed, 0)


if __name__ == "__main__":
    unittest.main()
