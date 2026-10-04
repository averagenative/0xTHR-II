"""Raw ALSA MIDI transport: finds the THR's /dev/snd/midiC*D* node and moves SysEx in and out.

Using the rawmidi device node directly keeps the project dependency-free. logind grants the
seated user an ACL on it, so no group membership is needed.
"""

from __future__ import annotations

import os
import queue
import re
import select
import threading
from pathlib import Path

from . import log

LOG = log.get("transport")

CARDS = Path("/proc/asound/cards")


class DeviceNotFound(RuntimeError):
    pass


def find_thr_midi() -> tuple[str, str]:
    """Return (device path, card description) for the first THR-II found."""
    for line in CARDS.read_text().splitlines():
        match = re.match(r"\s*(\d+)\s+\[.*?\]:\s+(.*)", line)
        if match and "THR" in match.group(2).upper():
            card = match.group(1)
            path = f"/dev/snd/midiC{card}D0"
            if os.path.exists(path):
                return path, match.group(2).strip()
    raise DeviceNotFound("No THR-II MIDI device found. Is the amp on and connected over USB?")


class RawMidi:
    """Full-duplex rawmidi with a reader thread that splits the byte stream into SysEx messages."""

    kind = "USB"

    def __init__(self, path: str | None = None):
        self.path = path or find_thr_midi()[0]
        self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        self.messages: queue.Queue[bytes] = queue.Queue()
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name="thr2-midi-in", daemon=True)
        self._reader.start()

    def write(self, data: bytes) -> None:
        log.frame("TX", data, "usb")
        view = memoryview(data)
        while view:
            try:
                sent = os.write(self.fd, view)
                view = view[sent:]
            except BlockingIOError:
                select.select([], [self.fd], [], 0.05)

    def receive(self, timeout: float | None = None) -> bytes | None:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_loop(self) -> None:
        pending = bytearray()
        in_sysex = False
        while not self._stop.is_set():
            ready, _, _ = select.select([self.fd], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            except OSError as err:
                LOG.warning("USB MIDI read failed: %s", err)
                break
            for byte in chunk:
                if byte == 0xF0:
                    pending = bytearray((byte,))
                    in_sysex = True
                elif in_sysex:
                    pending.append(byte)
                    if byte == 0xF7:
                        log.frame("RX", bytes(pending), "usb")
                        self.messages.put(bytes(pending))
                        in_sysex = False

    def alive(self) -> bool:
        return os.path.exists(self.path) and self._reader.is_alive()

    def close(self) -> None:
        self._stop.set()
        self._reader.join(timeout=1)
        os.close(self.fd)

    def __enter__(self) -> RawMidi:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_transport(via: str = "auto", bluetooth: bool = True):
    """Open the amp over USB or Bluetooth.

    ``auto`` prefers USB. Without USB it uses a paired THR-II Wireless over Bluetooth,
    asking BlueZ to connect it if needed. ``usb`` and ``bluetooth`` force one or the other.
    """
    usb_error = None
    if via in ("auto", "usb"):
        try:
            midi = RawMidi()
            LOG.info("Opened USB MIDI at %s", midi.path)
            return midi
        except DeviceNotFound as err:
            LOG.debug("USB: %s", err)
            if via == "usb":
                raise
            usb_error = err
    if via == "auto" and not bluetooth:
        raise usb_error or DeviceNotFound("No THR-II on USB.")
    try:
        from .ble import BleMidi, find_thr
    except ImportError:
        raise DeviceNotFound("No THR-II on USB, and Bluetooth needs PyGObject.") from usb_error
    info = find_thr()
    LOG.debug("Bluetooth lookup: %s", info)
    if info is None:
        raise DeviceNotFound("Turn the amp on and connect it with a USB cable, or pair a THR-II Wireless "
                             "in Bluetooth settings.")
    try:
        midi = BleMidi(info, connect_timeout=8.0)
        LOG.info("Opened Bluetooth MIDI to %s (%s), MTU %d", info["name"], info["address"], midi.mtu)
        return midi
    except Exception as err:
        LOG.warning("Bluetooth open failed: %s", err)
        state = "connected" if info["connected"] else "paired but not reachable"
        raise DeviceNotFound(f"{info['name']} is {state} over Bluetooth. Turn the amp on, or plug in a "
                             f"USB cable. ({err})") from err
