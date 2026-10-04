"""Visual themes: three THR-II finishes, two unrelated looks, and plain Adwaita.

Each theme overrides libadwaita's CSS color variables, adds a few rules of its own (the amp
themes put the THR's Y-pattern speaker grille behind the panels), and picks a knob style.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

TEXTURES = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "thr2" / "themes"


@dataclass(frozen=True)
class KnobStyle:
    kind: str = "arc"
    track: tuple | None = None
    arc: tuple | None = None
    cap_hi: tuple = (0.2, 0.2, 0.2)
    cap_lo: tuple = (0.05, 0.05, 0.05)
    rim: tuple = (0, 0, 0)
    pointer: tuple = (1, 1, 1)
    text: tuple | None = None
    glow: bool = False


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    scheme: Adw.ColorScheme
    knob: KnobStyle = field(default_factory=KnobStyle)
    variables: dict = field(default_factory=dict)
    extra_css: str = ""
    grille: tuple | None = None


def rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def grille_svg(color: str, opacity: float) -> str:
    """One tile of the THR-II grille: upright Y-shaped slots in rows offset by half a slot."""
    arm, width = 3.3, 1.9

    def y_shape(cx, cy):
        angles = (270, 30, 150)
        return "".join(
            f'<line x1="{cx}" y1="{cy}" x2="{cx + arm * math.cos(math.radians(a)):.2f}" '
            f'y2="{cy - arm * math.sin(math.radians(a)):.2f}"/>'
            for a in angles
        )

    shapes = y_shape(6, 5.5) + y_shape(0, 16) + y_shape(12, 16)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="21" viewBox="0 0 12 21">'
        f'<g stroke="{color}" stroke-opacity="{opacity}" stroke-width="{width}" stroke-linecap="round">'
        f"{shapes}</g></svg>"
    )


AMP_CARD_CSS = """
.thr2-window .card { box-shadow: 0 1px 3px var(--card-shade-color), 0 0 0 1px var(--card-shade-color); }
.thr2-window .heading { letter-spacing: 0.06em; }
.thr2-window .caption { letter-spacing: 0.02em; font-weight: 600; }
"""

THEMES = [
    Theme(
        id="adwaita",
        name="Adwaita",
        scheme=Adw.ColorScheme.DEFAULT,
    ),
    Theme(
        id="cream",
        name="THR30II Cream",
        scheme=Adw.ColorScheme.FORCE_LIGHT,
        knob=KnobStyle(kind="cap", track=rgb("#2b2620") + (0.18,), arc=rgb("#3b3326") + (1.0,),
                       cap_hi=rgb("#3a3631"), cap_lo=rgb("#0d0c0b"), rim=rgb("#000000"),
                       pointer=rgb("#f3ead0"), text=rgb("#2b2620")),
        variables={
            "window-bg-color": "#e6daa6", "window-fg-color": "#1f1b14",
            "view-bg-color": "#f2e9c4", "view-fg-color": "#1f1b14",
            "card-bg-color": "#efe5bb", "card-fg-color": "#1f1b14", "card-shade-color": "rgba(60,45,10,0.18)",
            "headerbar-bg-color": "#141311", "headerbar-fg-color": "#efe5bb",
            "headerbar-backdrop-color": "#1d1b18", "headerbar-shade-color": "rgba(0,0,0,0.5)",
            "popover-bg-color": "#f4ecca", "popover-fg-color": "#1f1b14",
            "dialog-bg-color": "#efe5bb", "dialog-fg-color": "#1f1b14",
            "accent-bg-color": "#2b2620", "accent-fg-color": "#f3ead0", "accent-color": "#4a3d22",
        },
        extra_css=AMP_CARD_CSS,
        grille=("#1b1814", 0.85, "#e6daa6"),
    ),
    Theme(
        id="white",
        name="THR30II White",
        scheme=Adw.ColorScheme.FORCE_LIGHT,
        knob=KnobStyle(kind="cap", track=rgb("#3d4044") + (0.15,), arc=rgb("#4a4e53") + (1.0,),
                       cap_hi=rgb("#ffffff"), cap_lo=rgb("#d4d6d8"), rim=rgb("#a9adb1"),
                       pointer=rgb("#33363a"), text=rgb("#33363a")),
        variables={
            "window-bg-color": "#eceeef", "window-fg-color": "#202326",
            "view-bg-color": "#ffffff", "view-fg-color": "#202326",
            "card-bg-color": "#f8f9f9", "card-fg-color": "#202326", "card-shade-color": "rgba(0,0,0,0.10)",
            "headerbar-bg-color": "#f8f9f9", "headerbar-fg-color": "#202326",
            "popover-bg-color": "#ffffff", "popover-fg-color": "#202326",
            "dialog-bg-color": "#f8f9f9", "dialog-fg-color": "#202326",
            "accent-bg-color": "#4a4e53", "accent-fg-color": "#ffffff", "accent-color": "#3d4044",
        },
        extra_css=AMP_CARD_CSS,
        grille=("#3d4044", 0.75, "#e3e5e7"),
    ),
    Theme(
        id="black",
        name="THR30II Black",
        scheme=Adw.ColorScheme.FORCE_DARK,
        knob=KnobStyle(kind="cap", track=rgb("#d9d9d9") + (0.15,), arc=rgb("#c9c9c9") + (1.0,),
                       cap_hi=rgb("#3b3b3b"), cap_lo=rgb("#0a0a0a"), rim=rgb("#000000"),
                       pointer=rgb("#f2f2f2"), text=rgb("#d9d9d9")),
        variables={
            "window-bg-color": "#1a1a1a", "window-fg-color": "#e6e6e6",
            "view-bg-color": "#121212", "view-fg-color": "#e6e6e6",
            "card-bg-color": "#232323", "card-fg-color": "#e6e6e6", "card-shade-color": "rgba(0,0,0,0.5)",
            "headerbar-bg-color": "#0c0c0c", "headerbar-fg-color": "#e6e6e6",
            "popover-bg-color": "#262626", "popover-fg-color": "#e6e6e6",
            "dialog-bg-color": "#202020", "dialog-fg-color": "#e6e6e6",
            "accent-bg-color": "#c9c9c9", "accent-fg-color": "#111111", "accent-color": "#d9d9d9",
        },
        extra_css=AMP_CARD_CSS,
        grille=("#000000", 0.9, "#1f1f1f"),
    ),
    Theme(
        id="neon",
        name="Neon",
        scheme=Adw.ColorScheme.FORCE_DARK,
        knob=KnobStyle(kind="arc", track=rgb("#ff2bd6") + (0.22,), arc=rgb("#00f0ff") + (1.0,),
                       text=rgb("#9ff8ff"), glow=True),
        variables={
            "window-bg-color": "#07070f", "window-fg-color": "#d9f6ff",
            "view-bg-color": "#0b0b18", "view-fg-color": "#d9f6ff",
            "card-bg-color": "#0e0e1f", "card-fg-color": "#d9f6ff", "card-shade-color": "rgba(0,240,255,0.25)",
            "headerbar-bg-color": "#05050b", "headerbar-fg-color": "#ff5be0",
            "popover-bg-color": "#11112a", "popover-fg-color": "#d9f6ff",
            "dialog-bg-color": "#0e0e1f", "dialog-fg-color": "#d9f6ff",
            "accent-bg-color": "#ff2bd6", "accent-fg-color": "#0a0a14", "accent-color": "#ff5be0",
        },
        extra_css="""
.thr2-window scrolledwindow.thr2-scroller {
  background-color: #07070f;
  background-image: repeating-linear-gradient(0deg, rgba(255,43,214,0.07) 0px, rgba(255,43,214,0.07) 1px, transparent 1px, transparent 32px),
                    repeating-linear-gradient(90deg, rgba(0,240,255,0.06) 0px, rgba(0,240,255,0.06) 1px, transparent 1px, transparent 32px);
}
.thr2-window .card {
  border: 1px solid rgba(0,240,255,0.45);
  box-shadow: 0 0 14px rgba(0,240,255,0.18), inset 0 0 18px rgba(255,43,214,0.06);
}
.thr2-window .heading { color: #ff5be0; text-shadow: 0 0 8px rgba(255,43,214,0.8); letter-spacing: 0.12em; }
.thr2-window .caption { color: #9ff8ff; letter-spacing: 0.02em; }
.thr2-window headerbar { box-shadow: inset 0 -1px rgba(255,43,214,0.6); }
""",
    ),
    Theme(
        id="metal",
        name="Bare Metal",
        scheme=Adw.ColorScheme.FORCE_LIGHT,
        knob=KnobStyle(kind="cap", track=rgb("#2c3034") + (0.18,), arc=rgb("#2f3438") + (1.0,),
                       cap_hi=rgb("#f6f7f8"), cap_lo=rgb("#8e959c"), rim=rgb("#5e656c"),
                       pointer=rgb("#1b1e21"), text=rgb("#1b1e21")),
        variables={
            "window-bg-color": "#c3c7cb", "window-fg-color": "#1b1e21",
            "view-bg-color": "#dde0e3", "view-fg-color": "#1b1e21",
            "card-bg-color": "#d3d6d9", "card-fg-color": "#1b1e21", "card-shade-color": "rgba(0,0,0,0.28)",
            "headerbar-bg-color": "#30353a", "headerbar-fg-color": "#e7eaed",
            "popover-bg-color": "#dde0e3", "popover-fg-color": "#1b1e21",
            "dialog-bg-color": "#d3d6d9", "dialog-fg-color": "#1b1e21",
            "accent-bg-color": "#35546e", "accent-fg-color": "#ffffff", "accent-color": "#2c4a63",
        },
        extra_css="""
.thr2-window scrolledwindow.thr2-scroller {
  background-color: #c3c7cb;
  background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.18) 0px, rgba(255,255,255,0.18) 1px,
                    rgba(0,0,0,0.04) 1px, rgba(0,0,0,0.04) 2px, transparent 2px, transparent 3px),
                    linear-gradient(170deg, rgba(255,255,255,0.35), rgba(0,0,0,0.12));
}
.thr2-window .card {
  border: 1px solid #7b828a;
  background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.22) 0px, rgba(255,255,255,0.22) 1px,
                    rgba(0,0,0,0.035) 1px, rgba(0,0,0,0.035) 3px);
  box-shadow: inset 0 1px rgba(255,255,255,0.75), inset 0 -1px rgba(0,0,0,0.18), 0 2px 4px rgba(0,0,0,0.3);
}
.thr2-window .heading { letter-spacing: 0.08em; color: #2b3035; text-shadow: 0 1px rgba(255,255,255,0.7); }
.thr2-window .caption { letter-spacing: 0.02em; font-weight: 700; color: #3a4046; text-shadow: 0 1px rgba(255,255,255,0.6); }
""",
    ),
]

BY_ID = {t.id: t for t in THEMES}
_current = THEMES[0]
_listeners: list = []


def current() -> Theme:
    return _current


def on_change(callback) -> None:
    _listeners.append(callback)


def _texture(theme: Theme) -> Path:
    color, opacity, _bg = theme.grille
    TEXTURES.mkdir(parents=True, exist_ok=True)
    path = TEXTURES / f"grille-{theme.id}.svg"
    path.write_text(grille_svg(color, opacity))
    return path


HEADER_CSS = """
.thr2-window headerbar {
  background-color: var(--headerbar-bg-color);
  color: var(--headerbar-fg-color);
}
"""


def css_for(theme: Theme) -> str:
    lines = [":root {"] + [f"  --{k}: {v};" for k, v in theme.variables.items()] + ["}"]
    if "headerbar-bg-color" in theme.variables:
        lines.append(HEADER_CSS)
    if theme.grille:
        texture = _texture(theme)
        lines.append(
            ".thr2-window scrolledwindow.thr2-scroller {"
            f" background-color: {theme.grille[2]};"
            f" background-image: url('{texture.as_uri()}');"
            " background-size: 16px 28px; }"
        )
    return "\n".join(lines) + "\n" + theme.extra_css


class ThemeManager:
    def __init__(self):
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

    def apply(self, theme_id: str) -> Theme:
        global _current
        theme = BY_ID.get(theme_id, THEMES[0])
        self.provider.load_from_string(css_for(theme))
        Adw.StyleManager.get_default().set_color_scheme(theme.scheme)
        _current = theme
        for callback in _listeners:
            callback(theme)
        return theme


_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager
