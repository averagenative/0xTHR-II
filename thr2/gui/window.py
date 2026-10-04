"""Main window: one screen laid out like the amp's front panel, kept in sync with the amp."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from ..client import AMP_NAMES, CABINETS  # noqa: E402
from . import settings, themes  # noqa: E402
from .knob import Knob, StepSetting  # noqa: E402
from .. import library, log, thrl6p  # noqa: E402
from ..device import DeviceNotFound, find_thr_midi  # noqa: E402
from .console import ConsoleWindow  # noqa: E402
from .indicators import LinkLight  # noqa: E402
from .meter import CLIP_DB, DB_MIN, LevelMeter, LevelMonitor, find_capture_node  # noqa: E402
from .presets import PresetsDialog  # noqa: E402
from .worker import AmpState, AmpWorker  # noqa: E402

MODELS = {0: "THR10II", 1: "THR10II Wireless", 2: "THR30II Wireless", 3: "THR30IIA Wireless"}
CATEGORIES = ["Clean", "Crunch", "Lead", "Hi Gain", "Special", "Bass", "Acoustic", "Flat"]
CHARACTERS = ["Modern", "Boutique", "Classic"]
AMP_GRID = {tuple(v.split(" / ")): k for k, v in AMP_NAMES.items()}
STEPS = ["1", "2", "5", "10"]

SLOTS = [
    ("FX1", "Compressor", "Evens out picking dynamics"),
    ("FX2", "Effect", "Chorus, flanger, phaser, or tremolo"),
    ("FX3", "Echo", "Tape echo or digital delay"),
    ("FX4", "Reverb", "Spring, plate, hall, or room"),
]
EFFECT_TYPES = {
    "FX1": [("RedComp", "Compressor")],
    "FX2": [("StereoSquareChorus", "Chorus"), ("L6Flanger", "Flanger"), ("Phaser", "Phaser"),
            ("BiasTremolo", "Tremolo")],
    "FX3": [("TapeEcho", "Tape echo"), ("L6DigitalDelay", "Digital delay")],
    "FX4": [("StandardSpring", "Spring"), ("LargePlate1", "Plate"), ("ReallyLargeHall", "Hall"),
            ("SmallRoom1", "Room")],
}
PARAM_LABELS = {
    "Drive": "Gain", "Mid": "Middle", "Freq": "Rate", "Pre": "Pre-delay", "PreDelay": "Pre-delay",
}
HIDDEN_PARAMS = {"SyncSelect"}
AMP_KNOBS = [("Drive", "Gain"), ("Master", "Master"), ("Bass", "Bass"), ("Mid", "Middle"),
             ("Treble", "Treble")]


def card(title: str, *suffixes: Gtk.Widget, tooltip: str | None = None) -> tuple[Gtk.Box, Gtk.Box]:
    """A rounded panel with a heading row. Returns (outer, body)."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                   margin_top=10, margin_bottom=12, margin_start=14, margin_end=14)
    header = Gtk.Box(spacing=8)
    label = Gtk.Label(label=title, xalign=0, hexpand=True)
    label.add_css_class("heading")
    if tooltip:
        label.set_tooltip_text(tooltip)
    header.append(label)
    for widget in suffixes:
        widget.set_valign(Gtk.Align.CENTER)
        header.append(widget)
    body.append(header)
    outer.append(body)
    return outer, body


def knob_row() -> Gtk.Box:
    return Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, homogeneous=True)


class EffectSlot:
    """One effect unit: on/off switch, model picker, mix, and the model's own settings."""

    def __init__(self, window: THRWindow, unit: str, title: str, hint: str):
        self.window = window
        self.unit = unit
        self.types = EFFECT_TYPES[unit]
        self.current_type = None
        self.param_knobs: list[Knob] = []
        self._syncing = False

        self.switch = Gtk.Switch()
        self.switch.update_property([Gtk.AccessibleProperty.LABEL], [f"{title} on or off"])
        self.switch.connect("notify::active", self._enable_changed)
        suffixes = [self.switch]
        self.dropdown = None
        if len(self.types) > 1:
            self.dropdown = Gtk.DropDown.new_from_strings([t[1] for t in self.types])
            self.dropdown.update_property([Gtk.AccessibleProperty.LABEL], [f"{title} model"])
            self.dropdown.connect("notify::selected", self._type_changed)
            suffixes.insert(0, self.dropdown)
        self.widget, body = card(title, *suffixes, tooltip=hint)
        self.widget.set_hexpand(True)

        self.knobs = knob_row()
        self.mix = Knob("Mix", lambda v: window.worker.set_param("GuitarProc", f"{unit}Mix", v), window.steps)
        self.knobs.append(self.mix)
        body.append(self.knobs)
        window.bind(("GuitarProc", f"{unit}Mix"), self.mix.set_wire_value)
        window.bind(("GuitarProc", f"{unit}Enable"), self.set_enabled)

    def _enable_changed(self, switch, _pspec) -> None:
        self._show_enabled(switch.get_active())
        if not self._syncing:
            self.window.worker.set_param("GuitarProc", f"{self.unit}Enable", 1.0 if switch.get_active() else 0.0)

    def _show_enabled(self, enabled: bool) -> None:
        self.knobs.set_opacity(1.0 if enabled else 0.45)

    def _type_changed(self, dropdown, _pspec) -> None:
        if self._syncing:
            return
        symbol = self.types[dropdown.get_selected()][0]
        if symbol != self.current_type:
            self.window.worker.submit("unit_type", self.unit, symbol, False)

    def set_enabled(self, value) -> None:
        self._syncing = True
        self.switch.set_active(bool(value))
        self._syncing = False

    def apply(self, patch) -> None:
        proc = patch.find("GuitarProc")
        unit = patch.find(self.unit)
        self._syncing = True
        if proc:
            self.switch.set_active(bool(proc.params.get(f"{self.unit}EnableState")))
            self._show_enabled(self.switch.get_active())
            self.mix.set_wire_value(proc.params.get(f"{self.unit}MixState"))
        if unit and unit.type != self.current_type:
            self._rebuild_params(unit)
        elif unit:
            for knob in self.param_knobs:
                knob.set_wire_value(unit.params.get(f"{knob.param}State"))
        if unit and self.dropdown:
            names = [t[0] for t in self.types]
            if unit.type in names:
                self.dropdown.set_selected(names.index(unit.type))
        self._syncing = False

    def _rebuild_params(self, unit) -> None:
        for knob in self.param_knobs:
            self.knobs.remove(knob)
            self.window.bindings.pop((self.unit, knob.param), None)
        self.param_knobs = []
        self.current_type = unit.type
        for key, value in unit.params.items():
            param = key.removesuffix("State")
            if param in HIDDEN_PARAMS or not isinstance(value, float):
                continue
            knob = Knob(PARAM_LABELS.get(param, param),
                        lambda v, p=param: self.window.worker.set_param(self.unit, p, v), self.window.steps)
            knob.param = param
            knob.set_wire_value(value)
            self.knobs.append(knob)
            self.param_knobs.append(knob)
            self.window.bind((self.unit, param), knob.set_wire_value)


class THRWindow(Adw.ApplicationWindow):
    def __init__(self, app, on_first_state=None):
        super().__init__(application=app, title="THR-II", default_width=1320, default_height=700)
        self.prefs = settings.load()
        self.steps = StepSetting(float(self.prefs.get("knob_step", 2)))
        self.bindings: dict = {}
        self._syncing = False
        self._built = False
        self._on_first_state = on_first_state
        self.state: AmpState | None = None
        self.monitor: LevelMonitor | None = None
        self._meter_timer = 0
        self._connected = False
        self.transport = "USB"
        self.presets_dialog: PresetsDialog | None = None
        self.original_tone: dict | None = None

        self.add_css_class("thr2-window")
        if self.prefs.get("debug") and not log.debug_enabled():
            log.enable_debug(True)
        self.console: ConsoleWindow | None = None
        self.log = log.get("app")
        theme_id = self.prefs.get("theme", "adwaita")
        themes.manager().apply(theme_id)
        theme_action = Gio.SimpleAction.new_stateful(
            "theme", GLib.VariantType.new("s"), GLib.Variant("s", themes.current().id))
        theme_action.connect("change-state", self._theme_changed)
        self.add_action(theme_action)

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title="THR-II", subtitle="Looking for the amp")
        header.set_title_widget(self.title_widget)

        usb_box = Gtk.Box(spacing=6)
        usb_label = Gtk.Label(label="Record")
        usb_label.add_css_class("dim-label")
        self.usb_toggle = Adw.ToggleGroup(tooltip_text="What the computer records over USB")
        self.usb_toggle.add(Adw.Toggle(name="amp", label="Amp", tooltip="Record the amp's processed sound over USB"))
        self.usb_toggle.add(Adw.Toggle(name="dry", label="Dry", tooltip="Record the dry guitar signal over USB"))
        self.usb_toggle.connect("notify::active-name", self._usb_changed)
        self.usb_toggle.set_sensitive(False)
        usb_box.append(usb_label)
        usb_box.append(self.usb_toggle)
        links = Gtk.Box(spacing=2)
        self.link_bt = LinkLight("bluetooth")
        self.link_usb = LinkLight("usb")
        links.append(self.link_bt)
        links.append(self.link_usb)
        header.pack_end(links)
        header.pack_end(usb_box)

        menu = Gio.Menu()
        amps, looks = Gio.Menu(), Gio.Menu()
        for theme in themes.THEMES:
            item = Gio.MenuItem.new(theme.name, None)
            item.set_action_and_target_value("win.theme", GLib.Variant("s", theme.id))
            (amps if theme.id in ("cream", "white", "black") else looks).append_item(item)
        menu.append_section("Amp finishes", amps)
        menu.append_section("Other looks", looks)
        theme_button = Gtk.MenuButton(icon_name="applications-graphics-symbolic", menu_model=menu,
                                      tooltip_text="Theme")
        header.pack_end(theme_button)
        console_button = Gtk.Button(icon_name="utilities-terminal-symbolic",
                                    tooltip_text="Console: connection log and debug output")
        console_button.connect("clicked", self._show_console)
        header.pack_end(console_button)

        step_box = Gtk.Box(spacing=6)
        step_label = Gtk.Label(label="Knob step")
        step_label.add_css_class("dim-label")
        self.step_toggle = Adw.ToggleGroup(
            tooltip_text="How far one scroll notch or arrow key moves a knob. Hold Shift to move by 1.")
        for value in STEPS:
            self.step_toggle.add(Adw.Toggle(name=value, label=value))
        current = str(int(self.steps.step))
        self.step_toggle.set_active_name(current if current in STEPS else "2")
        self.step_toggle.connect("notify::active-name", self._step_changed)
        step_box.append(step_label)
        step_box.append(self.step_toggle)
        presets_button = Gtk.Button(child=Adw.ButtonContent(icon_name="view-list-bullet-symbolic", label="Presets"),
                                    tooltip_text="Browse, load, and save presets")
        presets_button.connect("clicked", self._show_presets)
        header.pack_start(presets_button)
        header.pack_start(step_box)
        view.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.waiting = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="Connect your THR-II",
            description="Turn the amp on and connect it with a USB cable, or connect a THR-II Wireless in "
                        "Bluetooth settings. This window finds it automatically.",
        )
        bt_button = Gtk.Button(label="Connect over Bluetooth", halign=Gtk.Align.CENTER)
        bt_button.add_css_class("pill")
        bt_button.add_css_class("suggested-action")
        bt_button.connect("clicked", self._connect_bluetooth)
        self.waiting.set_child(bt_button)
        self.stack.add_named(self.waiting, "waiting")
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                           vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self.scroller.add_css_class("thr2-scroller")
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.START,
                             margin_top=14, margin_bottom=16, margin_start=16, margin_end=16)
        self.scroller.set_child(self.panel)
        self.stack.add_named(self.scroller, "amp")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self.worker = AmpWorker(self._on_state, self._on_event, self._on_status, self._on_error, self._on_result)
        self._update_links()
        GLib.timeout_add_seconds(2, self._update_links)
        self.connect("close-request", self._on_close)
        self.worker.start()

    def bind(self, key, update) -> None:
        self.bindings.setdefault(key, []).append(update)

    def is_connected(self) -> bool:
        return self._connected and self.state is not None

    def _show_presets(self, _button) -> None:
        self.original_tone = None
        self.presets_dialog = PresetsDialog(self)
        self.presets_dialog.connect("closed", lambda *_: setattr(self, "presets_dialog", None))
        self.presets_dialog.present(self)

    def load_preset(self, preset: dict, name: str) -> None:
        hold = {}
        if self.prefs.get("preset_keep_master", True):
            hold[("Amp", "Master")] = self.amp_knobs["Master"].value / 100.0
        if self.prefs.get("preset_keep_gain", False):
            hold[("Amp", "Drive")] = self.amp_knobs["Drive"].value / 100.0
        self.worker.submit("load_preset", preset, name, self.original_tone is None, hold)

    def restore_original(self) -> None:
        if self.original_tone:
            self.worker.submit("load_preset", self.original_tone, "your original tone", False)
            self.original_tone = None

    def save_preset(self, path, name: str) -> None:
        self.worker.submit("save_preset", path, name)

    def _on_result(self, kind: str, *args) -> None:
        if kind == "loaded":
            _name, backup, _skipped = args
            if backup is not None:
                self.original_tone = backup
                thrl6p.write(backup, library.CACHE.parent / "last-tone-before-load.thrl6p")
                if self.presets_dialog:
                    self.presets_dialog.show_original_saved()
        elif kind == "saved" and self.presets_dialog:
            self.presets_dialog.saved(args[0])

    def _update_links(self) -> bool:
        try:
            find_thr_midi()
            usb_up = True
        except (DeviceNotFound, OSError):
            usb_up = False
        try:
            from ..ble import find_thr
            info = find_thr()
            bt_up = bool(info and info["connected"])
        except Exception:
            bt_up = False
        active = self.transport if self._connected else None
        self.link_usb.set_state(usb_up or active == "USB", active == "USB")
        self.link_bt.set_state(bt_up or active == "Bluetooth", active == "Bluetooth")
        return GLib.SOURCE_CONTINUE

    def _show_console(self, _button) -> None:
        if self.console is None:
            self.console = ConsoleWindow(self._debug_changed)
            self.console.connect("close-request", lambda *_: setattr(self, "console", None) or False)
        self.console.present()

    def _debug_changed(self, on: bool) -> None:
        self.prefs["debug"] = on
        settings.save(self.prefs)

    def _connect_bluetooth(self, _button) -> None:
        self.waiting.set_description("Connecting over Bluetooth...")
        self.worker.connect_bluetooth()

    def _on_close(self, *_args):
        if self.console:
            self.console.close()
        self._stop_meter()
        self.worker.stop()
        return False

    def _theme_changed(self, action, value) -> None:
        action.set_state(value)
        theme = themes.manager().apply(value.get_string())
        self.log.info("Theme: %s", theme.name)
        self.prefs["theme"] = theme.id
        settings.save(self.prefs)

    def _step_changed(self, group, _pspec) -> None:
        name = group.get_active_name()
        if name:
            self.steps.step = float(name)
            self.prefs["knob_step"] = int(name)
            settings.save(self.prefs)

    def _build(self) -> None:
        top = Gtk.Box(spacing=14)
        top.append(self._build_amp())
        top.append(self._build_levels())
        self.panel.append(top)

        effects = Gtk.Box(spacing=14)
        self.slots = [EffectSlot(self, *slot) for slot in SLOTS]
        for slot in self.slots:
            effects.append(slot.widget)
        self.panel.append(effects)

        bottom = Gtk.Box(spacing=14)
        bottom.append(self._build_gate())
        bottom.append(self._build_memories())
        self.panel.append(bottom)
        self._built = True

    def _build_amp(self) -> Gtk.Widget:
        self.category = Gtk.DropDown.new_from_strings(CATEGORIES)
        self.category.update_property([Gtk.AccessibleProperty.LABEL], ["Amp type"])
        self.category.connect("notify::selected", self._amp_changed)
        self.character = Adw.ToggleGroup()
        for name in CHARACTERS:
            self.character.add(Adw.Toggle(name=name, label=name))
        self.character.connect("notify::active-name", self._amp_changed)
        outer, body = card("Amp", self.category, self.character)
        outer.set_hexpand(True)

        line = Gtk.Box(spacing=8)
        cab_label = Gtk.Label(label="Cabinet")
        cab_label.add_css_class("dim-label")
        self.cab = Gtk.DropDown.new_from_strings(CABINETS)
        self.cab.update_property([Gtk.AccessibleProperty.LABEL], ["Cabinet"])
        self.cab.connect("notify::selected", self._cab_changed)
        self.keep_knobs = Gtk.CheckButton(
            label="Keep knobs when changing amps", active=bool(self.prefs.get("keep_knobs", True)),
            tooltip_text="Otherwise the amp resets gain, master, and tone to 50 when you pick a new amp",
            hexpand=True, halign=Gtk.Align.END)
        self.keep_knobs.connect("toggled", self._keep_changed)
        line.append(cab_label)
        line.append(self.cab)
        line.append(self.keep_knobs)
        body.append(line)
        self.bind(("GuitarProc", "SpkSimType"), self._set_cab)

        knobs = knob_row()
        self.amp_knobs = {}
        for param, label in AMP_KNOBS:
            tooltip = "Also sets the recording level" if param == "Master" else None
            knob = Knob(label, lambda v, p=param: self.worker.set_param("Amp", p, v), self.steps, tooltip=tooltip,
                        size=64)
            knobs.append(knob)
            self.amp_knobs[param] = knob
            self.bind(("Amp", param), knob.set_wire_value)
        body.append(knobs)
        return outer

    def _build_levels(self) -> Gtk.Widget:
        self.clip_button = Gtk.Button(label="Clipped", visible=False,
                                      tooltip_text="The recording hit full scale. Click to reset.")
        self.clip_button.add_css_class("destructive-action")
        self.clip_button.add_css_class("pill")
        self.clip_button.connect("clicked", lambda b: b.set_visible(False))
        self.peak_label = Gtk.Label(label="Peak --", xalign=1, width_chars=13)
        self.peak_label.add_css_class("numeric")
        self.peak_label.add_css_class("dim-label")
        outer, body = card("Recording level", self.clip_button, self.peak_label,
                           tooltip="What the computer records over USB. Aim for peaks between -12 and -6 dB.")
        outer.set_size_request(440, -1)
        self.meter = LevelMeter()
        body.append(self.meter)
        hint = Gtk.Label(label="Set the recording with Master. Guitar only changes what you hear.",
                         xalign=0, wrap=True)
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        body.append(hint)

        row = Gtk.Box(spacing=12)
        knobs = knob_row()
        self.guitar_vol = Knob("Guitar", lambda v: self.worker.set_param("global", "GuitarVolume", v), self.steps,
                               tooltip="Guitar level in the headphones and speakers. Doesn't change the recording.")
        self.audio_vol = Knob("Computer", lambda v: self.worker.set_param("global", "AudioVolume", v), self.steps,
                              tooltip="Level of computer and Bluetooth playback through the amp")
        knobs.append(self.guitar_vol)
        knobs.append(self.audio_vol)
        self.bind(("global", "GuitarVolume"), self.guitar_vol.set_wire_value)
        self.bind(("global", "AudioVolume"), self.audio_vol.set_wire_value)
        row.append(knobs)
        stereo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER, hexpand=True,
                         halign=Gtk.Align.END)
        self.stereo_switch = Gtk.Switch(halign=Gtk.Align.CENTER,
                                        tooltip_text="Widens the reverb and computer or Bluetooth playback")
        self.stereo_switch.update_property([Gtk.AccessibleProperty.LABEL], ["Extended stereo"])
        self.stereo_switch.connect("notify::active", self._stereo_changed)
        stereo_label = Gtk.Label(label="Extended stereo")
        stereo_label.add_css_class("caption")
        stereo.append(self.stereo_switch)
        stereo.append(stereo_label)
        row.append(stereo)
        body.append(row)
        return outer

    def _build_gate(self) -> Gtk.Widget:
        self.gate_switch = Gtk.Switch()
        self.gate_switch.update_property([Gtk.AccessibleProperty.LABEL], ["Noise gate on or off"])
        self.gate_switch.connect("notify::active", self._gate_changed)
        outer, body = card("Noise gate", self.gate_switch,
                           tooltip="A high threshold can cut off the ends of notes and sound choppy")
        outer.set_size_request(260, -1)
        self.bind(("GuitarProc", "GateEnable"), self._set_gate)
        knobs = knob_row()
        self.thresh = Knob("Threshold", lambda v: self.worker.set_param("GuitarProc", "Thresh", v), self.steps,
                           lower=-96, upper=0, raw=True)
        self.release = Knob("Release", lambda v: self.worker.set_param("GuitarProc", "Decay", v), self.steps)
        knobs.append(self.thresh)
        knobs.append(self.release)
        self.bind(("GuitarProc", "Thresh"), self.thresh.set_wire_value)
        self.bind(("GuitarProc", "Decay"), self.release.set_wire_value)
        body.append(knobs)
        return outer

    def _build_memories(self) -> Gtk.Widget:
        outer, body = card("User memories", tooltip="Loading a memory replaces your current settings")
        outer.set_hexpand(True)
        row = Gtk.Box(spacing=8, homogeneous=True, vexpand=True, valign=Gtk.Align.CENTER)
        hint = Gtk.Label(label="Loading a memory replaces your current settings.", xalign=0)
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        body.append(hint)
        self.memory_buttons = []
        for i in range(5):
            button = Gtk.Button(tooltip_text="Load this memory. It replaces your current settings.")
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6)
            number = Gtk.Label(label=str(i + 1))
            number.add_css_class("title-3")
            name = Gtk.Label(label=f"Memory {i + 1}", ellipsize=Pango.EllipsizeMode.END, max_width_chars=16)
            name.add_css_class("caption")
            content.append(number)
            content.append(name)
            button.set_child(content)
            button.name_label = name
            button.connect("clicked", lambda _b, n=i: self.worker.submit("recall", n))
            row.append(button)
            self.memory_buttons.append(button)
        body.append(row)
        return outer

    def _start_meter_polling(self) -> None:
        if not self._meter_timer:
            self._meter_timer = GLib.timeout_add_seconds(2, self._ensure_meter)
        self._ensure_meter()

    def _ensure_meter(self) -> bool:
        if not self._connected:
            self._meter_timer = 0
            return GLib.SOURCE_REMOVE
        if self.monitor is None:
            node = find_capture_node()
            if node:
                self.log.info("Level meter watching %s", node)
                self.monitor = LevelMonitor(node, self._on_level, self._on_meter_stopped)
        return GLib.SOURCE_CONTINUE

    def _on_level(self, peaks, holds) -> None:
        self.meter.set_levels(peaks, holds)
        hold = max(holds) if holds else DB_MIN
        self.peak_label.set_label(f"Peak {hold:.1f} dB" if hold > DB_MIN else "Peak below -60 dB")
        if max(peaks, default=DB_MIN) >= CLIP_DB:
            self.clip_button.set_visible(True)

    def _on_meter_stopped(self) -> None:
        self.monitor = None
        self.meter.reset()
        self.peak_label.set_label("Peak --")

    def _stop_meter(self) -> None:
        if self.monitor:
            self.monitor.stop()
        if self._built:
            self._on_meter_stopped()

    def _on_status(self, connected: bool, message: str) -> None:
        self._connected = connected
        if connected:
            self.transport = message or "USB"
            self.title_widget.set_subtitle(f"Connecting over {self.transport}")
            self._update_links()
            return
        self._stop_meter()
        self._update_links()
        self.stack.set_visible_child_name("waiting")
        self.usb_toggle.set_sensitive(False)
        self.title_widget.set_title("THR-II")
        self.title_widget.set_subtitle("Not connected")
        if message:
            self.waiting.set_description(message)

    def _on_error(self, message: str) -> None:
        self.log.warning("Shown to user: %s", message)
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def _on_state(self, state: AmpState) -> None:
        if not self._built:
            self._build()
        self.state = state
        self._syncing = True
        patch = state.patch
        model = MODELS.get(state.identity.get("model"), "THR-II")
        edited = ", edited" if state.system.get("user_setting_changed") else ""
        self.title_widget.set_title(patch.name or model)
        self.title_widget.set_subtitle(f"{model}, firmware {state.firmware}, {self.transport}{edited}")

        amp = patch.find("Amp")
        if amp:
            pair = AMP_NAMES.get(amp.type, "").split(" / ")
            if len(pair) == 2:
                self.category.set_selected(CATEGORIES.index(pair[0]))
                self.character.set_active_name(pair[1])
            for param, knob in self.amp_knobs.items():
                knob.set_wire_value(amp.params.get(f"{param}State"))
        proc = patch.find("GuitarProc")
        if proc:
            self._set_cab(proc.params.get("SpkSimTypeState"))
            self.gate_switch.set_active(bool(proc.params.get("GateEnableState")))
            self.thresh.set_wire_value(proc.params.get("ThreshState"))
            self.release.set_wire_value(proc.params.get("DecayState"))
        for slot in self.slots:
            slot.apply(patch)

        self.guitar_vol.set_wire_value(state.globals.get("GuitarVolume"))
        self.audio_vol.set_wire_value(state.globals.get("AudioVolume"))
        self.stereo_switch.set_active(bool(state.system.get("extended_stereo")))
        self.usb_toggle.set_active_name("dry" if state.system.get("guitar_di_mode") else "amp")
        self.usb_toggle.set_sensitive(True)

        active = state.system.get("user_setting")
        for i, button in enumerate(self.memory_buttons):
            button.name_label.set_label(state.memory_names[i] or f"Memory {i + 1}")
            if i == active:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")
        self._syncing = False
        self.stack.set_visible_child_name("amp")
        self._start_meter_polling()
        if self._on_first_state:
            callback, self._on_first_state = self._on_first_state, None
            callback(self)

    def _on_event(self, event) -> None:
        self._syncing = True
        for update in self.bindings.get((event.unit, event.param), []):
            update(event.value)
        self._syncing = False
        if self.state and not self.state.system.get("user_setting_changed"):
            self.state.system["user_setting_changed"] = 1
            self.title_widget.set_subtitle(self.title_widget.get_subtitle() + ", edited")

    def _amp_changed(self, *_args) -> None:
        if self._syncing:
            return
        category = CATEGORIES[self.category.get_selected()]
        character = self.character.get_active_name()
        symbol = AMP_GRID.get((category, character))
        if symbol:
            self.worker.submit("unit_type", "Amp", symbol, self.keep_knobs.get_active())

    def _keep_changed(self, button) -> None:
        self.prefs["keep_knobs"] = button.get_active()
        settings.save(self.prefs)

    def _set_cab(self, value) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= int(value) < len(CABINETS):
            syncing, self._syncing = self._syncing, True
            self.cab.set_selected(int(value))
            self._syncing = syncing

    def _cab_changed(self, dropdown, _pspec) -> None:
        if not self._syncing:
            self.worker.set_param("GuitarProc", "SpkSimType", float(dropdown.get_selected()))

    def _set_gate(self, value) -> None:
        syncing, self._syncing = self._syncing, True
        self.gate_switch.set_active(bool(value))
        self._syncing = syncing

    def _gate_changed(self, switch, _pspec) -> None:
        if not self._syncing:
            self.worker.set_param("GuitarProc", "GateEnable", 1.0 if switch.get_active() else 0.0)

    def _stereo_changed(self, switch, _pspec) -> None:
        if not self._syncing:
            self.worker.submit("system", "extended_stereo", 1 if switch.get_active() else 0)

    def _usb_changed(self, group, _pspec) -> None:
        if not self._syncing and group.get_sensitive():
            self.worker.submit("system", "guitar_di_mode", 1 if group.get_active_name() == "dry" else 0)
