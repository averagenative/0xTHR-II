"""Logging for thr2: a ring buffer the app's console reads, plus optional raw frame tracing.

Every module logs to the "thr2" logger. ``enable_debug(True)`` turns on DEBUG level, which
includes a hex line for every frame sent to or received from the amp.
"""

from __future__ import annotations

import collections
import logging
import threading

LOGGER = logging.getLogger("thr2")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
FORMAT = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")


class RingHandler(logging.Handler):
    """Keeps the last lines in memory and tells listeners about new ones from any thread."""

    def __init__(self, size: int = 3000):
        super().__init__()
        self.lines: collections.deque[str] = collections.deque(maxlen=size)
        self.listeners: list = []
        self._lock = threading.Lock()
        self.setFormatter(FORMAT)

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        with self._lock:
            self.lines.append(line)
            listeners = list(self.listeners)
        for listener in listeners:
            listener(line)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self.lines)

    def clear(self) -> None:
        with self._lock:
            self.lines.clear()


RING = RingHandler()
LOGGER.addHandler(RING)


def get(name: str) -> logging.Logger:
    return LOGGER.getChild(name)


def enable_debug(on: bool) -> None:
    LOGGER.setLevel(logging.DEBUG if on else logging.INFO)
    LOGGER.info("Debug logging %s", "on: raw frames are traced" if on else "off")


def debug_enabled() -> bool:
    return LOGGER.isEnabledFor(logging.DEBUG)


def to_stderr() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(FORMAT)
    LOGGER.addHandler(handler)


def frame(direction: str, data: bytes, transport: str) -> None:
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.getChild("frames").debug("%s %s %d bytes: %s", transport, direction, len(data), data.hex(" "))
