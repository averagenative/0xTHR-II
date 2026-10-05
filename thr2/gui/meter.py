"""USB recording level meter: what the computer receives from the amp.

A GStreamer pipeline (pipewiresrc ! level) taps the amp's PipeWire capture node alongside
REAPER or any other recorder, and posts peak and decay levels on the GLib main loop.
The stream refuses to fall back to another source, so the meter never shows the laptop
microphone when the amp goes away.
"""

from __future__ import annotations

import json
import math
import subprocess
import time

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gst, Gtk, PangoCairo  # noqa: E402

DB_MIN = -60.0
TICKS = (-48, -36, -24, -12, -6, 0)
HOT_DB = -12.0
DANGER_DB = -3.0
CLIP_DB = -0.1
FALLOFF_DB_PER_S = 24.0

GREEN = (0.18, 0.76, 0.49)
AMBER = (0.90, 0.65, 0.04)
RED = (0.88, 0.11, 0.14)


def find_capture_node(match: str = "THR") -> str | None:
    """Return the PipeWire node name of the amp's USB capture, or None."""
    try:
        dump = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5).stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    for obj in dump:
        props = (obj.get("info") or {}).get("props") or {}
        name = str(props.get("node.name", ""))
        if props.get("media.class") == "Audio/Source" and name.startswith("alsa_input.") and match.lower() in name.lower():
            return name
    return None


class LevelMonitor:
    """Runs pipewiresrc ! level for one node and calls ``on_level(peaks, holds)`` in dBFS."""

    def __init__(self, node: str, on_level, on_stopped=None, capture_sink: bool = False):
        Gst.init(None)
        self.on_level = on_level
        self.on_stopped = on_stopped
        self.pipeline = Gst.parse_launch(
            "pipewiresrc name=src ! audioconvert ! audio/x-raw,format=F32LE ! "
            "level name=level interval=50000000 peak-ttl=1500000000 peak-falloff=20 post-messages=true ! "
            "fakesink sync=false"
        )
        src = self.pipeline.get_by_name("src")
        src.set_property("target-object", node)
        src.set_property("client-name", "THR-II Control meter")
        if src.find_property("on-disconnect"):   # PipeWire 1.2 and later; older plugins lack it
            src.set_property("on-disconnect", 2)
        props = "props,node.dont-fallback=true,node.dont-reconnect=true"
        if capture_sink:
            props += ",stream.capture.sink=true"
        src.set_property("stream-properties", Gst.Structure.from_string(props)[0])
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        self._watch = bus.connect("message", self._on_message)
        self.pipeline.set_state(Gst.State.PLAYING)

    def _on_message(self, _bus, msg) -> None:
        if msg.type == Gst.MessageType.ELEMENT:
            s = msg.get_structure()
            if s and s.get_name() == "level":
                self.on_level(list(s.get_value("peak")), list(s.get_value("decay")))
        elif msg.type in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
            self.stop()
            if self.on_stopped:
                self.on_stopped()

    def stop(self) -> None:
        if self.pipeline is None:
            return
        bus = self.pipeline.get_bus()
        bus.disconnect(self._watch)
        bus.remove_signal_watch()
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = None


def _x(db: float, width: float) -> float:
    return max(0.0, min(1.0, (db - DB_MIN) / -DB_MIN)) * width


class LevelMeter(Gtk.DrawingArea):
    """Two horizontal peak bars with held-peak markers and a dB scale."""

    def __init__(self):
        super().__init__()
        self.set_content_height(44)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["USB recording level"])
        self.shown = [DB_MIN, DB_MIN]
        self.holds = [DB_MIN, DB_MIN]
        self.active = False
        self._last = time.monotonic()

    def set_levels(self, peaks: list[float], holds: list[float]) -> None:
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        if len(peaks) == 1:
            peaks, holds = peaks * 2, holds * 2
        for i in range(2):
            fallen = self.shown[i] - FALLOFF_DB_PER_S * dt
            self.shown[i] = max(_finite(peaks[i]), fallen)
            self.holds[i] = _finite(holds[i])
        self.active = True
        self.queue_draw()

    def reset(self) -> None:
        self.shown = [DB_MIN, DB_MIN]
        self.holds = [DB_MIN, DB_MIN]
        self.active = False
        self.queue_draw()

    def _draw(self, _area, cr, width, height) -> None:
        fg = self.get_color()
        bar_h, gap, top = 9, 4, 2
        for i in range(2):
            y = top + i * (bar_h + gap)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            cr.rectangle(0, y, width, bar_h)
            cr.fill()
            level = self.shown[i]
            for lo, hi, color in ((DB_MIN, HOT_DB, GREEN), (HOT_DB, DANGER_DB, AMBER), (DANGER_DB, 0.0, RED)):
                if level <= lo:
                    break
                x0, x1 = _x(lo, width), _x(min(level, hi), width)
                cr.set_source_rgb(*color)
                cr.rectangle(x0, y, x1 - x0, bar_h)
                cr.fill()
            if self.holds[i] > DB_MIN:
                hold = self.holds[i]
                color = RED if hold > DANGER_DB else AMBER if hold > HOT_DB else GREEN
                cr.set_source_rgb(*color)
                cr.rectangle(_x(hold, width) - 1, y, 2, bar_h)
                cr.fill()

        scale_y = top + 2 * bar_h + gap + 3
        font = self.get_pango_context().get_font_description().copy()
        font.set_size(int(font.get_size() * 0.72))
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
        for tick in TICKS:
            x = _x(tick, width)
            cr.rectangle(x - 0.5, scale_y, 1, 3)
            cr.fill()
            layout = self.create_pango_layout(str(tick))
            layout.set_font_description(font)
            tw, _th = layout.get_pixel_size()
            cr.move_to(min(max(x - tw / 2, 0), width - tw), scale_y + 4)
            PangoCairo.show_layout(cr, layout)
        if not self.active:
            layout = self.create_pango_layout("No signal from the amp")
            layout.set_font_description(font)
            cr.move_to(4, top)
            PangoCairo.show_layout(cr, layout)


def _finite(db: float) -> float:
    return db if math.isfinite(db) and db > DB_MIN else DB_MIN

