"""Main window: amp, effects, gate, output, and user memories, kept in sync with the amp."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..client import AMP_NAMES, CABINETS  # noqa: E402
from .worker import AmpState, AmpWorker  # noqa: E402

MODELS = {0: "THR10II", 1: "THR10II Wireless", 2: "THR30II Wireless", 3: "THR30IIA Wireless"}
CATEGORIES = ["Clean", "Crunch", "Lead", "Hi Gain", "Special", "Bass", "Acoustic", "Flat"]
CHARACTERS = ["Modern", "Boutique", "Classic"]
AMP_GRID = {tuple(v.split(" / ")): k for k, v in AMP_NAMES.items()}

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


class SliderRow(Adw.ActionRow):
    """A row with a horizontal slider. Values on the wire are 0.0 to 1.0 unless ``raw``."""

    def __init__(self, title: str, on_change, lower=0.0, upper=100.0, raw=False, unit=""):
        super().__init__(title=title)
        self._on_change = on_change
        self._raw = raw
        self._syncing = False
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lower, upper, 1)
        self.scale.set_hexpand(False)
        self.scale.set_size_request(320, -1)
        self.scale.set_valign(Gtk.Align.CENTER)
        self.scale.set_draw_value(True)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale.set_format_value_func(lambda _s, v: f"{v:.0f}{unit}")
        self.scale.add_css_class("thr-slider")
        self.scale.update_property([Gtk.AccessibleProperty.LABEL], [title])
        self.scale.connect("value-changed", self._changed)
        self.add_suffix(self.scale)

    def _changed(self, scale) -> None:
        if not self._syncing:
            value = scale.get_value()
            self._on_change(value if self._raw else value / 100.0)

    def set_wire_value(self, value) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        self._syncing = True
        self.scale.set_value(value if self._raw else value * 100.0)
        self._syncing = False


class EffectSlot:
    """One effect unit: an expander with an on/off switch, a model picker, mix, and settings."""

    def __init__(self, window: THRWindow, unit: str, title: str, hint: str):
        self.window = window
        self.unit = unit
        self.types = EFFECT_TYPES[unit]
        self.current_type = None
        self.param_rows: list[SliderRow] = []
        self._syncing = False

        self.row = Adw.ExpanderRow(title=title, subtitle=hint, show_enable_switch=True)
        self.row.connect("notify::enable-expansion", self._enable_changed)

        self.type_row = None
        if len(self.types) > 1:
            self.type_row = Adw.ComboRow(title="Model", model=Gtk.StringList.new([t[1] for t in self.types]))
            self.type_row.connect("notify::selected", self._type_changed)
            self.row.add_row(self.type_row)

        self.mix_row = SliderRow("Mix", lambda v: window.worker.set_param("GuitarProc", f"{unit}Mix", v))
        self.row.add_row(self.mix_row)
        window.bindings[("GuitarProc", f"{unit}Mix")] = self.mix_row.set_wire_value
        window.bindings[("GuitarProc", f"{unit}Enable")] = self.set_enabled

    def _enable_changed(self, row, _pspec) -> None:
        if not self._syncing:
            self.window.worker.set_param("GuitarProc", f"{self.unit}Enable", 1.0 if row.get_enable_expansion() else 0.0)

    def _type_changed(self, row, _pspec) -> None:
        if self._syncing:
            return
        symbol = self.types[row.get_selected()][0]
        if symbol != self.current_type:
            self.window.worker.submit("unit_type", self.unit, symbol, False)

    def set_enabled(self, value) -> None:
        self._syncing = True
        self.row.set_enable_expansion(bool(value))
        self._syncing = False

    def apply(self, patch) -> None:
        proc = patch.find("GuitarProc")
        unit = patch.find(self.unit)
        self._syncing = True
        if proc:
            self.row.set_enable_expansion(bool(proc.params.get(f"{self.unit}EnableState")))
            self.mix_row.set_wire_value(proc.params.get(f"{self.unit}MixState"))
        if unit and unit.type != self.current_type:
            self._rebuild_params(unit)
        elif unit:
            for row in self.param_rows:
                row.set_wire_value(unit.params.get(f"{row.param}State"))
        if unit and self.type_row:
            names = [t[0] for t in self.types]
            if unit.type in names:
                self.type_row.set_selected(names.index(unit.type))
        self._syncing = False

    def _rebuild_params(self, unit) -> None:
        for row in self.param_rows:
            self.row.remove(row)
            self.window.bindings.pop((self.unit, row.param), None)
        self.param_rows = []
        self.current_type = unit.type
        for key, value in unit.params.items():
            param = key.removesuffix("State")
            if param in HIDDEN_PARAMS or not isinstance(value, float):
                continue
            row = SliderRow(PARAM_LABELS.get(param, param),
                            lambda v, p=param: self.window.worker.set_param(self.unit, p, v))
            row.param = param
            row.set_wire_value(value)
            self.row.add_row(row)
            self.param_rows.append(row)
            self.window.bindings[(self.unit, param)] = row.set_wire_value
        if len(self.types) > 1:
            self.row.set_subtitle(dict(self.types).get(unit.type, unit.type))


class THRWindow(Adw.ApplicationWindow):
    def __init__(self, app, on_first_state=None):
        super().__init__(application=app, title="THR-II", default_width=720, default_height=900)
        self.bindings: dict = {}
        self._syncing = False
        self._built = False
        self._on_first_state = on_first_state
        self.state: AmpState | None = None

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title="THR-II", subtitle="Looking for the amp")
        header.set_title_widget(self.title_widget)

        usb_box = Gtk.Box(spacing=6)
        usb_label = Gtk.Label(label="USB")
        usb_label.add_css_class("dim-label")
        self.usb_toggle = Adw.ToggleGroup()
        self.usb_toggle.add(Adw.Toggle(name="amp", label="Amp", tooltip="Record the amp's processed sound over USB"))
        self.usb_toggle.add(Adw.Toggle(name="dry", label="Dry", tooltip="Record the dry guitar signal over USB"))
        self.usb_toggle.connect("notify::active-name", self._usb_changed)
        self.usb_toggle.set_sensitive(False)
        usb_box.append(usb_label)
        usb_box.append(self.usb_toggle)
        header.pack_end(usb_box)
        view.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.waiting = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="Connect your THR-II",
            description="Turn the amp on and connect it with a USB cable. This window finds it automatically.",
        )
        self.stack.add_named(self.waiting, "waiting")
        self.page = Adw.PreferencesPage()
        self.stack.add_named(self.page, "amp")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        self.worker = AmpWorker(self._on_state, self._on_event, self._on_status, self._on_error)
        self.connect("close-request", self._on_close)
        self.worker.start()

    def _on_close(self, *_args):
        self.worker.stop()
        return False

    def _build(self) -> None:
        amp = Adw.PreferencesGroup(title="Amp")
        self.category_row = Adw.ComboRow(title="Amp", model=Gtk.StringList.new(CATEGORIES))
        self.category_row.connect("notify::selected", self._amp_changed)
        amp.add(self.category_row)

        self.character_row = Adw.ActionRow(title="Character")
        self.character = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        for name in CHARACTERS:
            self.character.add(Adw.Toggle(name=name, label=name))
        self.character.connect("notify::active-name", self._amp_changed)
        self.character_row.add_suffix(self.character)
        amp.add(self.character_row)

        self.keep_knobs = Adw.SwitchRow(
            title="Keep knob settings when changing amps",
            subtitle="Otherwise the amp resets gain, master, and tone to 50",
            active=True,
        )
        amp.add(self.keep_knobs)

        self.cab_row = Adw.ComboRow(title="Cabinet", model=Gtk.StringList.new(CABINETS))
        self.cab_row.connect("notify::selected", self._cab_changed)
        amp.add(self.cab_row)
        self.bindings[("GuitarProc", "SpkSimType")] = self._set_cab

        self.amp_rows = {}
        for param, label in AMP_KNOBS:
            row = SliderRow(label, lambda v, p=param: self.worker.set_param("Amp", p, v))
            amp.add(row)
            self.amp_rows[param] = row
            self.bindings[("Amp", param)] = row.set_wire_value
        self.page.add(amp)

        effects = Adw.PreferencesGroup(
            title="Effects",
            description="Switch an effect off here or by turning its knob on the amp fully counterclockwise.",
        )
        self.slots = [EffectSlot(self, *slot) for slot in SLOTS]
        for slot in self.slots:
            effects.add(slot.row)
        self.page.add(effects)

        gate = Adw.PreferencesGroup(
            title="Noise gate",
            description="A high threshold can cut off the ends of notes and sound choppy.",
        )
        self.gate_row = Adw.SwitchRow(title="Noise gate")
        self.gate_row.connect("notify::active", self._gate_changed)
        gate.add(self.gate_row)
        self.bindings[("GuitarProc", "GateEnable")] = self._set_gate
        self.thresh_row = SliderRow("Threshold", lambda v: self.worker.set_param("GuitarProc", "Thresh", v),
                                    lower=-96, upper=0, raw=True, unit=" dB")
        self.decay_row = SliderRow("Release", lambda v: self.worker.set_param("GuitarProc", "Decay", v))
        gate.add(self.thresh_row)
        gate.add(self.decay_row)
        self.bindings[("GuitarProc", "Thresh")] = self.thresh_row.set_wire_value
        self.bindings[("GuitarProc", "Decay")] = self.decay_row.set_wire_value
        self.page.add(gate)

        output = Adw.PreferencesGroup(title="Output")
        self.guitar_vol = SliderRow("Guitar volume", lambda v: self.worker.set_param("global", "GuitarVolume", v))
        self.audio_vol = SliderRow("Computer and Bluetooth audio",
                                   lambda v: self.worker.set_param("global", "AudioVolume", v))
        output.add(self.guitar_vol)
        output.add(self.audio_vol)
        self.bindings[("global", "GuitarVolume")] = self.guitar_vol.set_wire_value
        self.bindings[("global", "AudioVolume")] = self.audio_vol.set_wire_value
        self.stereo_row = Adw.SwitchRow(title="Extended stereo",
                                        subtitle="Widens the reverb and computer or Bluetooth playback")
        self.stereo_row.connect("notify::active", self._stereo_changed)
        output.add(self.stereo_row)
        self.page.add(output)

        self.memories = Adw.PreferencesGroup(
            title="User memories",
            description="Loading a memory replaces your current settings.",
        )
        self.memory_rows = []
        for i in range(5):
            row = Adw.ActionRow(title=f"Memory {i + 1}")
            button = Gtk.Button(label="Load", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, n=i: self.worker.submit("recall", n))
            row.add_suffix(button)
            self.memories.add(row)
            self.memory_rows.append(row)
        self.page.add(self.memories)
        self._built = True

    def _on_status(self, connected: bool, message: str) -> None:
        if connected:
            self.title_widget.set_subtitle("Connecting")
            return
        self.stack.set_visible_child_name("waiting")
        self.usb_toggle.set_sensitive(False)
        self.title_widget.set_title("THR-II")
        self.title_widget.set_subtitle("Not connected")
        if message and "No THR-II" not in message:
            self.waiting.set_description(f"{message}\nRetrying every few seconds.")

    def _on_error(self, message: str) -> None:
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
        self.title_widget.set_subtitle(f"{model}, firmware {state.firmware}{edited}")

        amp = patch.find("Amp")
        if amp:
            pair = AMP_NAMES.get(amp.type, "").split(" / ")
            if len(pair) == 2:
                self.category_row.set_selected(CATEGORIES.index(pair[0]))
                self.character.set_active_name(pair[1])
            for param, row in self.amp_rows.items():
                row.set_wire_value(amp.params.get(f"{param}State"))
        proc = patch.find("GuitarProc")
        if proc:
            self._set_cab(proc.params.get("SpkSimTypeState"))
            self.gate_row.set_active(bool(proc.params.get("GateEnableState")))
            self.thresh_row.set_wire_value(proc.params.get("ThreshState"))
            self.decay_row.set_wire_value(proc.params.get("DecayState"))
        for slot in self.slots:
            slot.apply(patch)

        self.guitar_vol.set_wire_value(state.globals.get("GuitarVolume"))
        self.audio_vol.set_wire_value(state.globals.get("AudioVolume"))
        self.stereo_row.set_active(bool(state.system.get("extended_stereo")))
        self.usb_toggle.set_active_name("dry" if state.system.get("guitar_di_mode") else "amp")
        self.usb_toggle.set_sensitive(True)

        active = state.system.get("user_setting")
        for i, row in enumerate(self.memory_rows):
            row.set_title(state.memory_names[i] or f"Memory {i + 1}")
            row.set_subtitle("Active" + (", edited" if edited else "") if i == active else "")
        self._syncing = False
        self.stack.set_visible_child_name("amp")
        if self._on_first_state:
            callback, self._on_first_state = self._on_first_state, None
            callback(self)

    def _on_event(self, event) -> None:
        update = self.bindings.get((event.unit, event.param))
        if update:
            self._syncing = True
            update(event.value)
            self._syncing = False
        if self.state and not self.state.system.get("user_setting_changed"):
            self.state.system["user_setting_changed"] = 1
            self.title_widget.set_subtitle(self.title_widget.get_subtitle() + ", edited")

    def _amp_changed(self, *_args) -> None:
        if self._syncing:
            return
        category = CATEGORIES[self.category_row.get_selected()]
        character = self.character.get_active_name()
        symbol = AMP_GRID.get((category, character))
        if symbol:
            self.worker.submit("unit_type", "Amp", symbol, self.keep_knobs.get_active())

    def _set_cab(self, value) -> None:
        if isinstance(value, (int, float)) and 0 <= int(value) < len(CABINETS):
            syncing, self._syncing = self._syncing, True
            self.cab_row.set_selected(int(value))
            self._syncing = syncing

    def _cab_changed(self, row, _pspec) -> None:
        if not self._syncing:
            self.worker.set_param("GuitarProc", "SpkSimType", float(row.get_selected()))

    def _set_gate(self, value) -> None:
        syncing, self._syncing = self._syncing, True
        self.gate_row.set_active(bool(value))
        self._syncing = syncing

    def _gate_changed(self, row, _pspec) -> None:
        if not self._syncing:
            self.worker.set_param("GuitarProc", "GateEnable", 1.0 if row.get_active() else 0.0)

    def _stereo_changed(self, row, _pspec) -> None:
        if not self._syncing:
            self.worker.submit("system", "extended_stereo", 1 if row.get_active() else 0)

    def _usb_changed(self, group, _pspec) -> None:
        if not self._syncing and group.get_sensitive():
            self.worker.submit("system", "guitar_di_mode", 1 if group.get_active_name() == "dry" else 0)
