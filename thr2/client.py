"""High-level THR-II client: unlock, query, monitor, and change settings over USB MIDI.

Protocol facts come from Martin Zwerschke's reverse-engineering notes
(SYSEX_PROTOCOL_THR30II.pdf in github.com/martinzw/THRII-direct-USB-pedalboard).
Opcodes, key numbers, and system-setting codes are best guesses from that work and from
probing a THR30II Wireless on firmware 1.40.0a.
"""

from __future__ import annotations

import json
import os
import queue
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import log
from .device import RawMidi, open_transport
from .patch import Patch, parse_patch
from .sysex import (
    IDENTITY_REQUEST, Frame, float_word, parse_identity, unpack_words, word_float, words,
)

GLOBAL_UNIT = 0xFFFFFFFF
ACTUAL_SETTINGS = 0xFFFFFFFF
NOT_ACK = 0xFFFFFFFF

UNLOCK_KEYS = {
    0x01300063: 0x686FBEEB,
    0x0131006B: 0x9809EB24,
    0x01400061: 0x7986615C,
    0x01420067: 0xDD54CD72,
    0x01430062: 0xDD54CD72,
    0x01440061: 0xDD54CD72,
}
LATEST_KEY = 0xDD54CD72

TYPE_ENUM = 2
TYPE_BOOL = 3
TYPE_FLOAT = 4

SYSTEM_SETTINGS = {
    "user_setting": 0x00,
    "user_setting_changed": 0x01,
    "front_led": 0x02,
    "wireless_channel_mode": 0x03,
    "wireless_channel": 0x04,
    "extended_stereo": 0x06,
    "streaming_eq": 0x07,
    "volumes_to_line_out": 0x08,
    "usb_output_volume": 0x09,
    "g10t_plugged_in": 0x0B,
    "battery_level": 0x0C,
    "guitar_di_mode": 0x0D,
    "speaker_tuner_mode": 0x0E,
    "eco_recharge": 0x0F,
}

CABINETS = [
    "British 4x12", "American 4x12", "Brown 4x12", "Vintage 4x12", "Fuel 4x12",
    "Juicy 4x12", "Mods 4x12", "American 2x12", "British 2x12", "British Blues",
    "Boutique 2x12", "Yamaha 2x12", "California 1x12", "American 1x12", "American 4x10",
    "Boutique 1x12", "Bypass",
]

AMP_NAMES = {
    "THR30_Carmen": "Clean / Modern", "THR10C_BJunior2": "Clean / Boutique",
    "THR10C_Deluxe": "Clean / Classic", "THR30_SR101": "Crunch / Modern",
    "THR10C_Mini": "Crunch / Boutique", "THR10C_DC30": "Crunch / Classic",
    "THR10_Brit": "Lead / Modern", "THR30_Blondie": "Lead / Boutique",
    "THR10_Lead": "Lead / Classic", "THR10X_Brown2": "Hi Gain / Modern",
    "THR30_FLead": "Hi Gain / Boutique", "THR10_Modern": "Hi Gain / Classic",
    "THR30_Stealth": "Special / Modern", "THR10X_South": "Special / Boutique",
    "THR10X_Brown1": "Special / Classic", "THR30_JKBass2": "Bass / Modern",
    "THR10_Bass_Mesa": "Bass / Boutique", "THR10_Bass_Eden_Marcus": "Bass / Classic",
    "THR10_Aco_Dynamic1": "Acoustic / Modern", "THR10_Aco_Tube1": "Acoustic / Boutique",
    "THR10_Aco_Condenser1": "Acoustic / Classic", "THR10_Flat_V": "Flat / Modern",
    "THR10_Flat_B": "Flat / Boutique", "THR10_Flat": "Flat / Classic",
}

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "thr2"
LOG = log.get("client")


class THRError(RuntimeError):
    pass


@dataclass
class Event:
    """An unsolicited report from the amp (knob turned, preset recalled, and so on)."""

    opcode: int
    words: list[int]
    unit: str | None = None
    param: str | None = None
    value: object = None
    raw: bytes = b""


@dataclass
class Answer:
    words: list[int]
    data: bytes = b""

    @property
    def ok(self) -> bool:
        return not self.words or self.words[0] != NOT_ACK


@dataclass
class THR:
    midi: RawMidi
    identity: dict = field(default_factory=dict)
    firmware: int = 0
    symbols: list[str] = field(default_factory=list)
    events: queue.Queue = field(default_factory=queue.Queue)
    _counters: dict = field(default_factory=lambda: {0: 0, 1: 0})

    @classmethod
    def open(cls, path: str | None = None, load_symbols: bool = True, via: str = "auto") -> THR:
        thr = cls(RawMidi(path) if path else open_transport(via))
        thr.connect(load_symbols=load_symbols)
        return thr

    def close(self) -> None:
        self.midi.close()

    def __enter__(self) -> THR:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def family(self) -> int:
        return self.identity.get("family", 0x24) & 0x7F

    @property
    def model(self) -> int:
        return self.identity.get("model", 0x02) & 0x7F

    def connect(self, load_symbols: bool = True) -> None:
        for _attempt in range(4):
            self.midi.write(IDENTITY_REQUEST)
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline and not self.identity:
                msg = self.midi.receive(timeout=0.2)
                if msg and (ident := parse_identity(msg)):
                    self.identity = ident
            if self.identity:
                break
        if not self.identity:
            self.midi.close()
            raise THRError("No identity reply. The amp may be off or in firmware-update mode.")
        LOG.info("Amp identified: family 0x%02x model %d firmware %s", self.identity["family"],
                 self.identity["model"], self.identity["version"])
        self._drain(0.3)

        answer = self.command(0, 0x01)
        self.firmware = answer.words[0] if answer.words else self.identity["firmware_word"]

        key = UNLOCK_KEYS.get(self.firmware, LATEST_KEY)
        ack = self.command(0, 0x04, words(key))
        if not ack.ok:
            raise THRError(f"Amp rejected the unlock key for firmware {self.firmware_text}.")
        LOG.info("MIDI control unlocked (firmware %s)", self.firmware_text)
        if load_symbols:
            self.symbols = self.load_symbols()

    @property
    def firmware_text(self) -> str:
        fw = self.firmware.to_bytes(4, "big")
        return f"{fw[0]}.{fw[1]:x}.{fw[2]:x}{chr(fw[3])}"

    def _send(self, ab: int, payload: bytes) -> None:
        frame = Frame(self.family, self.model, ab, self._counters[ab], 0, payload)
        self._counters[ab] = (self._counters[ab] + 1) & 0x7F
        self.midi.write(frame.encode())

    def command(self, ab: int, opcode: int, body: bytes = b"", standalone: bool = False,
                timeout: float = 2.0) -> Answer:
        """Send a command and wait for its answer frame(s).

        A-commands with a body go out as a header frame (opcode, body length) followed by a
        body frame. Some B-commands carry the body inside the header frame instead; pass
        ``standalone=True`` for those.
        """
        if standalone or not body:
            self._send(ab, words(opcode, len(body)) + body)
        else:
            self._send(ab, words(opcode, len(body)))
            self._send(ab, body)
        return self._await_answer(ab, timeout)

    def _await_answer(self, ab: int, timeout: float) -> Answer:
        deadline = time.monotonic() + timeout
        total = None
        data = bytearray()
        next_part = 0
        while time.monotonic() < deadline:
            msg = self.midi.receive(timeout=max(0.0, deadline - time.monotonic()))
            if msg is None:
                break
            frame = Frame.decode(msg)
            if frame is None or frame.sub_id != 0x4D:
                continue
            if total is None:
                w = frame.words
                if frame.ab == ab and frame.part == 0 and len(w) >= 2 and w[0] == 0x01:
                    total = w[1]
                    data.extend(frame.payload[8:])
                    next_part = 1
                else:
                    self._queue_event(frame, msg)
                    continue
            elif frame.ab == ab and frame.part == next_part:
                data.extend(frame.payload)
                next_part += 1
            else:
                self._queue_event(frame, msg)
                continue
            if len(data) >= total:
                data = data[:total]
                return Answer(unpack_words(bytes(data)), bytes(data))
        LOG.warning("Timed out waiting for an answer (group %s, got %d of %s bytes)", "AB"[ab], len(data), total)
        raise THRError("Timed out waiting for the amp to answer.")

    def _drain(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            msg = self.midi.receive(timeout=0.05)
            if msg and (frame := Frame.decode(msg)):
                self._queue_event(frame, msg)

    def symbol(self, key: int) -> str:
        if 0 <= key < len(self.symbols):
            return self.symbols[key]
        return f"0x{key:04x}"

    def key(self, name: str) -> int:
        try:
            return self.symbols.index(name)
        except ValueError:
            raise THRError(f"Unknown symbol {name!r} on firmware {self.firmware_text}.") from None

    def load_symbols(self) -> list[str]:
        cache = CACHE_DIR / f"symbols-{self.firmware:08x}.json"
        if cache.exists():
            LOG.debug("Symbol table from cache %s", cache)
            return json.loads(cache.read_text())
        LOG.info("Downloading the symbol table from the amp")
        data = self.command(0, 0x03, timeout=10).data
        count = int.from_bytes(data[0:4], "little")
        table = data[8:8 + 12 * count]
        strings = data[8 + 12 * count:]
        names = []
        for i in range(count):
            offset, _crc, length = unpack_words(table[i * 12:i * 12 + 12])
            names.append(strings[offset:offset + length].decode("utf-8", "replace"))
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(names))
        return names

    def system(self, name_or_code: str | int) -> tuple[int, int]:
        """Read a system setting. Returns (type, value)."""
        code = SYSTEM_SETTINGS.get(name_or_code, name_or_code)
        answer = self.command(0, 0x0D, words(code))
        if len(answer.words) < 3 or answer.words[0] != 0:
            raise THRError(f"System setting 0x{code:02x} is not available.")
        return answer.words[1], answer.words[2]

    def set_system(self, name_or_code: str | int, value: int, value_type: int | None = None) -> bool:
        """Write a system setting. Experimental: the frame layout is inferred, not documented."""
        code = SYSTEM_SETTINGS.get(name_or_code, name_or_code)
        if value_type is None:
            value_type = self.system(code)[0]
        return self.command(0, 0x0E, words(code, value_type, value)).ok

    def get_global(self, name: str) -> object:
        answer = self.command(0, 0x09, words(GLOBAL_UNIT, self.key(name)))
        if len(answer.words) < 3 or answer.words[0] != 0:
            raise THRError(f"Global parameter {name!r} is not available.")
        return decode_value(answer.words[1], answer.words[2])

    def set_param(self, unit: str | int, param: str, value: float) -> bool:
        """Set a float parameter. Values are 0.0 to 1.0 on the wire; most UIs show 0 to 100."""
        LOG.debug("set %s.%s = %.4f", unit, param, value)
        ukey = GLOBAL_UNIT if unit in (GLOBAL_UNIT, "global") else self.key(unit)
        body = words(ukey, self.key(param), TYPE_FLOAT, float_word(value))
        return self.command(0, 0x0A, body).ok

    def batch(self, steps: list[tuple], window: int = 6, progress=None) -> list[str]:
        """Send several changes, a few at a time, without waiting for each answer.

        Each step is ("type", unit, symbol) or ("param", unit, param, value). Answers come
        back in order, so after sending up to ``window`` changes the client collects that
        many answers. Raises THRError if an answer goes missing, so the caller can retry
        one change at a time. Returns notes about changes the amp didn't accept.
        """
        bodies, notes = [], []
        for step in steps:
            try:
                if step[0] == "type":
                    bodies.append((step, 0x08, words(self.key(step[1]), self.key(step[2]))))
                else:
                    ukey = GLOBAL_UNIT if step[1] == "global" else self.key(step[1])
                    bodies.append((step, 0x0A, words(ukey, self.key(step[2]), TYPE_FLOAT, float_word(step[3]))))
            except THRError as err:
                notes.append(f"{step[1]} {step[2]}: {err}")
        started = time.monotonic()
        for i in range(0, len(bodies), window):
            chunk = bodies[i:i + window]
            for step, opcode, body in chunk:
                LOG.debug("batch %s", step)
                self._send(0, words(opcode, len(body)))
                self._send(0, body)
            for step, _opcode, _body in chunk:
                if not self._await_answer(0, timeout=2.0).ok:
                    notes.append(f"{step[1]} {step[2]}: not accepted")
            if progress:
                progress(min(i + window, len(bodies)), len(bodies))
        LOG.info("Sent %d changes in %.0f ms", len(bodies), (time.monotonic() - started) * 1000)
        return notes

    def set_unit_type(self, unit: str, type_name: str) -> bool:
        """Switch a unit's model, for example the Amp unit to THR10X_Brown1."""
        return self.command(0, 0x08, words(self.key(unit), self.key(type_name))).ok

    def patch_name(self, index: int) -> str:
        data = self.command(1, 0x06, words(index), standalone=True).data
        length = int.from_bytes(data[4:8], "little")
        return data[8:8 + length].split(b"\x00")[0].decode("utf-8", "replace")

    def dump_raw(self, index: int = ACTUAL_SETTINGS) -> bytes:
        """The raw patch dump (without its leading four words) for the current tone or a memory."""
        return self.command(1, 0x0C, words(index), standalone=True, timeout=10).data[16:]

    def store_memory(self, index: int, dump: bytes) -> bool:
        """Write a raw patch dump into user memory ``index`` (0-based). Overwrites that memory.

        Frame layout from the protocol notes: a B-command header (opcode 0x0D, total length,
        memory index, data length, then 0, 1, 0), followed by the dump in 210-byte body
        frames that share one frame counter and number their pieces 0, 1, 2, and so on.
        """
        if not 0 <= index <= 4:
            raise THRError("User memories are numbered 1 to 5.")
        LOG.info("Storing %d bytes into user memory %d", len(dump), index + 1)
        self._send(1, words(0x0D, len(dump) + 20, index, len(dump) + 12, 0, 1, 0))
        counter = self._counters[1]
        self._counters[1] = (counter + 1) & 0x7F
        for part, start in enumerate(range(0, len(dump), 210)):
            frame = Frame(self.family, self.model, 1, counter, part, dump[start:start + 210])
            self.midi.write(frame.encode())
        return self._await_answer(1, timeout=5.0).ok

    def dump(self, index: int = ACTUAL_SETTINGS) -> Patch:
        data = self.command(1, 0x0C, words(index), standalone=True, timeout=10).data
        return parse_patch(data[16:], self.symbol)

    def _queue_event(self, frame: Frame, raw: bytes) -> None:
        w = frame.words
        if frame.sub_id != 0x4D or not w or frame.part != 0:
            return
        event = Event(opcode=w[0], words=w, raw=raw)
        if w[0] == 0x04 and len(w) >= 6:
            event.unit = "global" if w[2] == GLOBAL_UNIT else self.symbol(w[2])
            event.param = self.symbol(w[3])
            event.value = decode_value(w[4], w[5])
        elif w[0] == 0x03 and len(w) >= 4:
            event.unit = self.symbol(w[2])
            event.param = "type"
            event.value = self.symbol(w[3])
        elif w[0] == 0x02 and len(w) >= 6:
            event.unit = "user_setting"
            event.param = "dumped" if w[5] == 1 else "recalled"
            event.value = w[3] + 1 if w[3] != ACTUAL_SETTINGS else "actual"
        self.events.put(event)

    def recall(self, index: int) -> bool:
        """Load user memory 1 to 5 (0-based index) into the active settings."""
        return self.command(1, 0x0E, words(index), standalone=True).ok

    def poll_events(self, timeout: float = 0.05) -> list[Event]:
        """Read whatever the amp has sent within ``timeout`` and return the decoded events."""
        msg = self.midi.receive(timeout=timeout)
        while msg is not None:
            if frame := Frame.decode(msg):
                self._queue_event(frame, msg)
            msg = self.midi.receive(timeout=0)
        events = []
        while not self.events.empty():
            events.append(self.events.get_nowait())
        return events

    def listen(self, timeout: float = 0.2):
        """Yield events as the amp reports them. Stop by breaking out of the loop."""
        while True:
            try:
                yield self.events.get_nowait()
                continue
            except queue.Empty:
                pass
            msg = self.midi.receive(timeout=timeout)
            if msg and (frame := Frame.decode(msg)):
                self._queue_event(frame, msg)


def decode_value(value_type: int, raw: int) -> object:
    if value_type == TYPE_FLOAT:
        return word_float(raw)
    if value_type == TYPE_BOOL:
        return bool(raw)
    return raw
