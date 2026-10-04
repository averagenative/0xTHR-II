"""Application entry point: ``python3 -m thr2.gui``."""

from __future__ import annotations

import argparse
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

from .. import log  # noqa: E402
from .window import THRWindow  # noqa: E402

APP_ID = "io.github.averagenative.thr2"

CSS = """
.thr-slider value {
  font-feature-settings: "tnum";
  min-width: 3.5em;
}
"""


def save_png(window: Gtk.Window, path: str, widget: Gtk.Widget | None = None) -> None:
    """Render a widget (default: the window's content) to a PNG without a screen-capture portal."""
    widget = widget or window.get_content()
    width, height = widget.get_width(), widget.get_height()
    snapshot = Gtk.Snapshot()
    background = Adw.StyleManager.get_default().get_dark()
    color = Gdk.RGBA()
    color.parse("#242424" if background else "#fafafa")
    snapshot.append_color(color, Graphene.Rect().init(0, 0, width, height))
    Gtk.WidgetPaintable.new(widget).snapshot(snapshot, width, height)
    texture = window.get_renderer().render_texture(snapshot.to_node(), Graphene.Rect().init(0, 0, width, height))
    texture.save_to_png(path)


class THRApplication(Adw.Application):
    def __init__(self, screenshot: str | None = None, height: int | None = None):
        super().__init__(application_id=APP_ID)
        self.screenshot = screenshot
        self.height = height

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = THRWindow(self, on_first_state=self._capture if self.screenshot else None)
            if self.height:
                window.set_default_size(720, self.height)
        window.present()

    def _capture(self, window):
        def shoot():
            save_png(window, self.screenshot)
            window.close()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(3500, shoot)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thr2-gui")
    parser.add_argument("--screenshot", metavar="PNG", help="Render the window to a PNG after connecting, then quit")
    parser.add_argument("--height", type=int, help="Window height, useful with --screenshot")
    parser.add_argument("--debug", action="store_true", help="Log raw frames and print the log to the terminal")
    args, rest = parser.parse_known_args(argv)
    if args.debug:
        log.to_stderr()
        log.enable_debug(True)
    app = THRApplication(args.screenshot, args.height)
    if args.screenshot:
        app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    return app.run([sys.argv[0], *rest])
