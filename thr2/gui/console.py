"""Console window: the live thr2 log, with a raw-frame debug switch, copy, and clear."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import log  # noqa: E402

MAX_LINES = 5000


class ConsoleWindow(Adw.Window):
    def __init__(self, on_debug_changed):
        super().__init__(title="THR-II Console", default_width=900, default_height=480)
        self._on_debug_changed = on_debug_changed
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()

        debug_box = Gtk.Box(spacing=6)
        debug_label = Gtk.Label(label="Debug")
        self.debug_switch = Gtk.Switch(active=log.debug_enabled(), valign=Gtk.Align.CENTER,
                                       tooltip_text="Also log every frame sent to and received from the amp")
        self.debug_switch.update_property([Gtk.AccessibleProperty.LABEL], ["Debug logging"])
        self.debug_switch.connect("notify::active", self._debug_toggled)
        debug_box.append(debug_label)
        debug_box.append(self.debug_switch)
        header.pack_start(debug_box)

        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy the log")
        copy.connect("clicked", self._copy)
        clear = Gtk.Button(icon_name="edit-clear-all-symbolic", tooltip_text="Clear the log")
        clear.connect("clicked", self._clear)
        header.pack_end(copy)
        header.pack_end(clear)
        view.add_top_bar(header)

        self.buffer = Gtk.TextBuffer()
        self.text = Gtk.TextView(buffer=self.buffer, editable=False, cursor_visible=False, monospace=True,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8,
                                 left_margin=10, right_margin=10)
        self.scroller = Gtk.ScrolledWindow(child=self.text, vexpand=True)
        view.set_content(self.scroller)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        for line in log.RING.snapshot():
            self.buffer.insert(self.buffer.get_end_iter(), line + "\n")
        self._scroll_to_end()
        log.RING.listeners.append(self._from_any_thread)
        self.connect("close-request", self._closed)

    def _from_any_thread(self, line: str) -> None:
        GLib.idle_add(self._append, line)

    def _append(self, line: str) -> bool:
        adj = self.scroller.get_vadjustment()
        at_bottom = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 24
        self.buffer.insert(self.buffer.get_end_iter(), line + "\n")
        extra = self.buffer.get_line_count() - MAX_LINES
        if extra > 0:
            self.buffer.delete(self.buffer.get_start_iter(), self.buffer.get_iter_at_line(extra)[1])
        if at_bottom:
            self._scroll_to_end()
        return GLib.SOURCE_REMOVE

    def _scroll_to_end(self) -> None:
        GLib.idle_add(lambda: self.text.scroll_to_mark(self.buffer.get_insert(), 0, False, 0, 1)
                      if self.buffer.place_cursor(self.buffer.get_end_iter()) is None else False)

    def _debug_toggled(self, switch, _pspec) -> None:
        log.enable_debug(switch.get_active())
        self._on_debug_changed(switch.get_active())

    def _copy(self, _button) -> None:
        text = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)
        Gdk.Display.get_default().get_clipboard().set(text)
        self.toasts.add_toast(Adw.Toast(title="Copied the log", timeout=2))

    def _clear(self, _button) -> None:
        log.RING.clear()
        self.buffer.set_text("")

    def _closed(self, *_args):
        if self._from_any_thread in log.RING.listeners:
            log.RING.listeners.remove(self._from_any_thread)
        return False
