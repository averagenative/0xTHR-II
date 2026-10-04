"""Header-bar link lights: a Bluetooth rune that glows blue and a USB trident that glows red."""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

COLORS = {"bluetooth": (0.24, 0.62, 1.0), "usb": (1.0, 0.23, 0.2)}
NAMES = {"bluetooth": "Bluetooth", "usb": "USB"}


def _bluetooth(cr) -> None:
    cr.move_to(7, 7.5)
    cr.line_to(16.5, 16.5)
    cr.line_to(12, 21)
    cr.line_to(12, 3)
    cr.line_to(16.5, 7.5)
    cr.line_to(7, 16.5)


def _usb(cr) -> None:
    cr.move_to(12, 20)
    cr.line_to(12, 5)
    cr.move_to(12, 16)
    cr.line_to(7, 12.5)
    cr.line_to(7, 10)
    cr.move_to(12, 14)
    cr.line_to(17, 11)
    cr.line_to(17, 9)


def _usb_solids(cr) -> None:
    cr.move_to(12, 2)
    cr.line_to(9.8, 5.6)
    cr.line_to(14.2, 5.6)
    cr.close_path()
    cr.new_sub_path()
    cr.arc(7, 8.6, 1.6, 0, 2 * math.pi)
    cr.new_sub_path()
    cr.rectangle(15.6, 6.4, 2.8, 2.8)
    cr.new_sub_path()
    cr.arc(12, 20.2, 1.9, 0, 2 * math.pi)


class LinkLight(Gtk.DrawingArea):
    def __init__(self, kind: str):
        super().__init__(accessible_role=Gtk.AccessibleRole.IMG, valign=Gtk.Align.CENTER)
        self.kind = kind
        self.lit = False
        self.controlling = False
        self.set_content_width(26)
        self.set_content_height(26)
        self.set_draw_func(self._draw)
        self._update_text()

    def set_state(self, lit: bool, controlling: bool) -> None:
        if (lit, controlling) != (self.lit, self.controlling):
            self.lit, self.controlling = lit, controlling
            self._update_text()
            self.queue_draw()

    def _update_text(self) -> None:
        name = NAMES[self.kind]
        if self.controlling:
            text = f"{name}: connected, controlling the amp"
        elif self.lit:
            text = f"{name}: connected"
        else:
            text = f"{name}: not connected"
        self.set_tooltip_text(text)
        self.update_property([Gtk.AccessibleProperty.LABEL], [text])

    def _path(self, cr) -> None:
        (_bluetooth if self.kind == "bluetooth" else _usb)(cr)

    def _draw(self, area, cr, width, height) -> None:
        cr.translate((width - 24) / 2, (height - 24) / 2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        if self.lit:
            r, g, b = COLORS[self.kind]
            strength = 1.0 if self.controlling else 0.6
            for width_px, alpha in ((9, 0.08), (6.5, 0.14), (4.5, 0.24)):
                cr.set_line_width(width_px)
                cr.set_source_rgba(r, g, b, alpha * strength)
                self._path(cr)
                cr.stroke()
            color = (r, g, b, 1.0)
        else:
            fg = area.get_color()
            color = (fg.red, fg.green, fg.blue, 0.35)
        cr.set_source_rgba(*color)
        cr.set_line_width(2)
        self._path(cr)
        cr.stroke()
        if self.kind == "usb":
            _usb_solids(cr)
            cr.fill()
