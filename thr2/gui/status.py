"""A slim bar that shows a preset being applied: spinner, text, and progress."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402


class ApplyStatus(Gtk.Revealer):
    def __init__(self):
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, reveal_child=False)
        box = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=14, margin_end=14)
        self.spinner = Adw.Spinner()
        self.spinner.set_size_request(16, 16)
        self.label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.label.add_css_class("caption-heading")
        self.bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
        self.bar.set_size_request(180, -1)
        box.append(self.spinner)
        box.append(self.label)
        box.append(self.bar)
        self.set_child(box)
        self._hide_source = 0
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Preset status"])

    def _cancel_hide(self) -> None:
        if self._hide_source:
            GLib.source_remove(self._hide_source)
            self._hide_source = 0

    def _hide_later(self, ms: int) -> None:
        self._cancel_hide()

        def hide():
            self._hide_source = 0
            self.set_reveal_child(False)
            return GLib.SOURCE_REMOVE

        self._hide_source = GLib.timeout_add(ms, hide)

    def update(self, name: str, done: int, total: int, next_name: str | None = None) -> None:
        self._cancel_hide()
        self.spinner.set_visible(True)
        text = f"Applying '{name}': {done} of {total} changes" if total else f"Applying '{name}'"
        if next_name:
            text += f". Next: '{next_name}'"
        self.label.set_label(text)
        self.bar.set_visible(True)
        self.bar.set_fraction(done / total if total else 0.0)
        self.set_reveal_child(True)

    def busy(self, text: str) -> None:
        self._cancel_hide()
        self.spinner.set_visible(True)
        self.bar.set_visible(False)
        self.label.set_label(text)
        self.set_reveal_child(True)

    def done(self, text: str) -> None:
        self.spinner.set_visible(False)
        self.bar.set_visible(False)
        self.label.set_label(text)
        self.set_reveal_child(True)
        self._hide_later(2500)

    def finish(self, name: str, total: int) -> None:
        self.spinner.set_visible(False)
        self.bar.set_fraction(1.0)
        self.label.set_label(f"Loaded '{name}'" if total else f"'{name}' already matches the amp")
        self.set_reveal_child(True)
        self._hide_later(1500)

    def fail(self, name: str) -> None:
        self.spinner.set_visible(False)
        self.bar.set_visible(False)
        self.label.set_label(f"Couldn't finish loading '{name}'. See Console.")
        self.set_reveal_child(True)
        self._hide_later(4000)
