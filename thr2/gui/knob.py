"""Rotary knob control: drag, scroll, or use the arrow keys.

The scroll and arrow-key step comes from a shared setting (1, 2, 5, or 10 on the 0 to 100
scale) so the player can choose between quick moves and fine adjustment. Holding Shift
always moves by the finest step.
"""

from __future__ import annotations

import math

import cairo
import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, Gtk, PangoCairo  # noqa: E402

ARC_START = 0.75 * math.pi
ARC_SWEEP = 1.5 * math.pi
DRAG_PIXELS_FULL_RANGE = 180.0
SURFACE_PIXELS_PER_STEP = 15.0


class StepSetting:
    """Shared knob step in 0-to-100 units."""

    def __init__(self, step: float = 2.0):
        self.step = step


class Knob(Gtk.Box):
    def __init__(self, label: str, on_change, steps: StepSetting, lower=0.0, upper=100.0, raw=False,
                 unit="", tooltip: str | None = None, size: int = 50):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.CENTER)
        self._on_change = on_change
        self.steps = steps
        self.lower, self.upper = float(lower), float(upper)
        self.raw = raw
        self.unit = unit
        self.value = self.lower
        self._drag_start = self.lower
        self._scroll_acc = 0.0
        self.param = None

        self.dial = Gtk.DrawingArea(accessible_role=Gtk.AccessibleRole.SLIDER, focusable=True, focus_on_click=True)
        self.dial.set_content_width(size)
        self.dial.set_content_height(size)
        self.dial.set_halign(Gtk.Align.CENTER)
        self.dial.set_draw_func(self._draw)
        self.dial.set_cursor_from_name("ns-resize")
        if tooltip:
            self.set_tooltip_text(tooltip)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        self.dial.add_controller(drag)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._scroll)
        self.dial.add_controller(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.dial.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda *_: self.dial.queue_draw())
        focus.connect("leave", lambda *_: self.dial.queue_draw())
        self.dial.add_controller(focus)

        name = Gtk.Label(label=label, justify=Gtk.Justification.CENTER)
        name.add_css_class("caption")
        self.append(self.dial)
        self.append(name)
        self.dial.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.VALUE_MIN, Gtk.AccessibleProperty.VALUE_MAX],
            [label, self.lower, self.upper],
        )

    def _unit_step(self, state: Gdk.ModifierType | None) -> float:
        """Step in the knob's display units: percent for 0-to-100 knobs, dB for raw dB knobs."""
        return 1.0 if state and state & Gdk.ModifierType.SHIFT_MASK else self.steps.step

    def _set(self, value: float, notify: bool = True) -> None:
        value = float(min(self.upper, max(self.lower, value)))
        if abs(value - self.value) < 1e-9:
            return
        self.value = value
        self.dial.update_property(
            [Gtk.AccessibleProperty.VALUE_NOW, Gtk.AccessibleProperty.VALUE_TEXT], [value, self.text()]
        )
        self.dial.queue_draw()
        if notify:
            self._on_change(value if self.raw else value / 100.0)

    def text(self) -> str:
        return f"{self.value:.0f}{self.unit}"

    def set_wire_value(self, value) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        self._set(value if self.raw else value * 100.0, notify=False)

    def _drag_begin(self, gesture, _x, _y) -> None:
        self._drag_start = self.value
        self.dial.grab_focus()

    def _drag_update(self, gesture, dx, dy) -> None:
        state = gesture.get_current_event_state()
        scale = 0.2 if state & Gdk.ModifierType.SHIFT_MASK else 1.0
        self._set(self._drag_start + (dx - dy) * scale * (self.upper - self.lower) / DRAG_PIXELS_FULL_RANGE)

    def _scroll(self, controller, _dx, dy) -> bool:
        if controller.get_unit() == Gdk.ScrollUnit.SURFACE:
            dy /= SURFACE_PIXELS_PER_STEP
        self._scroll_acc += dy
        notches = int(self._scroll_acc)
        if notches:
            self._scroll_acc -= notches
            self._set(self.value - notches * self._unit_step(controller.get_current_event_state()))
        return True

    def _key(self, controller, keyval, _code, state) -> bool:
        step = self._unit_step(state)
        moves = {
            Gdk.KEY_Up: step, Gdk.KEY_Right: step, Gdk.KEY_Down: -step, Gdk.KEY_Left: -step,
            Gdk.KEY_Page_Up: step * 10, Gdk.KEY_Page_Down: -step * 10,
        }
        if keyval in moves:
            self._set(self.value + moves[keyval])
        elif keyval == Gdk.KEY_Home:
            self._set(self.lower)
        elif keyval == Gdk.KEY_End:
            self._set(self.upper)
        else:
            return False
        return True

    def _draw(self, area, cr, width, height) -> None:
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 5
        fg = area.get_color()
        accent = Adw.StyleManager.get_default().get_accent_color_rgba()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(5)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
        cr.arc(cx, cy, radius, ARC_START, ARC_START + ARC_SWEEP)
        cr.stroke()
        fraction = (self.value - self.lower) / (self.upper - self.lower)
        if fraction > 0.001:
            cr.set_source_rgba(accent.red, accent.green, accent.blue, 1.0)
            cr.arc(cx, cy, radius, ARC_START, ARC_START + ARC_SWEEP * fraction)
            cr.stroke()
        if area.has_focus():
            cr.set_line_width(2)
            cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.5)
            cr.arc(cx, cy, radius + 4, 0, 2 * math.pi)
            cr.stroke()
        layout = area.create_pango_layout(self.text())
        font = area.get_pango_context().get_font_description().copy()
        font.set_size(int(font.get_size() * (0.8 if width < 56 else 1.0)))
        layout.set_font_description(font)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.9)
        cr.move_to(cx - tw / 2, cy - th / 2)
        PangoCairo.show_layout(cr, layout)
