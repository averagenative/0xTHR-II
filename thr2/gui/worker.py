"""Background thread that owns the amp connection so the GTK main loop never blocks.

The window submits commands; the worker runs them in order, reads the amp's change
reports between commands, and hands results back to the main loop with GLib.idle_add.
Slider drags are coalesced: only the latest value per parameter is sent.
"""

from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field

import traceback

from gi.repository import GLib

from .. import log

LOG = log.get("worker")

from .. import thrl6p
from ..client import THR, THRError
from ..device import DeviceNotFound

AMP_KNOBS = ("Bass", "Mid", "Treble", "Drive", "Master")


@dataclass
class AmpState:
    identity: dict
    firmware: str
    patch: object
    globals: dict = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    memory_names: list = field(default_factory=list)


class AmpWorker(threading.Thread):
    def __init__(self, on_state, on_event, on_status, on_error, on_result=None):
        super().__init__(name="thr2-worker", daemon=True)
        self._on_result = on_result or (lambda *args: None)
        self._on_state = on_state
        self._on_event = on_event
        self._on_status = on_status
        self._on_error = on_error
        self._commands: queue.Queue = queue.Queue()
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._force_bluetooth = False
        self._refresh_requested = False
        self.thr: THR | None = None
        self.last_patch = None
        self.saved_memories: set = set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def connect_bluetooth(self) -> None:
        """Ask BlueZ to connect a paired amp on the next attempt, then try right away."""
        self._force_bluetooth = True
        self._wake.set()

    def set_param(self, unit: str, param: str, value: float) -> None:
        with self._lock:
            self._pending[(unit, param)] = value

    def submit(self, name: str, *args) -> None:
        self._commands.put((name, args))

    def run(self) -> None:
        while not self._stop.is_set():
            if self.thr is None:
                if not self._connect():
                    self._wake.wait(2.0)
                    self._wake.clear()
                    continue
            try:
                self._flush_params()
                self._run_commands()
                self._pump_events()
                if self._refresh_requested:
                    self._refresh_requested = False
                    self._refresh()
            except (OSError, THRError) as err:
                LOG.warning("%s", err)
                if self._device_gone():
                    self._disconnect(str(err))
                else:
                    GLib.idle_add(self._on_error, str(err))
            except Exception as err:
                LOG.error("Unexpected error, reconnecting:\n%s", traceback.format_exc())
                GLib.idle_add(self._on_error, f"Unexpected error: {err}. Reconnecting; see Console.")
                self._disconnect(f"Reconnecting after an error: {err}")
        if self.thr:
            self.thr.close()

    def _connect(self) -> bool:
        via, self._force_bluetooth = ("bluetooth" if self._force_bluetooth else "auto"), False
        try:
            self.thr = THR.open(via=via)
        except (DeviceNotFound, THRError, OSError) as err:
            self.thr = None
            if str(err) != getattr(self, "_last_error", None):
                LOG.info("Not connected: %s", err)
                self._last_error = str(err)
            GLib.idle_add(self._on_status, False, str(err))
            return False
        except Exception as err:
            self.thr = None
            LOG.error("Unexpected error while connecting:\n%s", traceback.format_exc())
            GLib.idle_add(self._on_status, False, f"Connection error: {err}. See Console.")
            return False
        self._last_error = None
        self.thr.saved_memories = self.saved_memories
        LOG.info("Connected over %s", self.thr.midi.kind)
        GLib.idle_add(self._on_status, True, self.thr.midi.kind)
        self._refresh()
        return True

    def _device_gone(self) -> bool:
        return self.thr is None or not self.thr.midi.alive()

    def _disconnect(self, reason: str) -> None:
        LOG.info("Disconnected: %s", reason)
        try:
            if self.thr:
                self.thr.close()
        except Exception:
            pass
        self.thr = None
        GLib.idle_add(self._on_status, False, reason)

    def _refresh(self) -> None:
        thr = self.thr
        state = AmpState(identity=thr.identity, firmware=thr.firmware_text, patch=thr.dump())
        self.last_patch = state.patch
        for name in ("GuitarVolume", "AudioVolume"):
            state.globals[name] = thr.get_global(name)
        for name in ("guitar_di_mode", "extended_stereo", "user_setting", "user_setting_changed"):
            state.system[name] = thr.system(name)[1]
        state.memory_names = [thr.patch_name(i) for i in range(5)]
        GLib.idle_add(self._on_state, state)

    def _flush_params(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for (unit, param), value in pending.items():
            if not self.thr.set_param(unit, param, value):
                GLib.idle_add(self._on_error, f"The amp didn't accept {param}.")

    def _run_commands(self) -> None:
        while True:
            try:
                name, args = self._commands.get_nowait()
            except queue.Empty:
                return
            getattr(self, f"_cmd_{name}")(*args)

    def _cmd_refresh(self) -> None:
        self._refresh_requested = True

    def _cmd_unit_type(self, unit: str, type_name: str, keep_knobs: bool) -> None:
        thr = self.thr
        knobs = {}
        if keep_knobs:
            amp = thr.dump().find(unit)
            knobs = {k: amp.params[f"{k}State"] for k in AMP_KNOBS if amp and f"{k}State" in amp.params}
        if not thr.set_unit_type(unit, type_name):
            GLib.idle_add(self._on_error, f"The amp didn't accept {type_name}.")
        for key, value in knobs.items():
            thr.set_param(unit, key, value)
        self._refresh_requested = True

    def _cmd_system(self, name: str, value: int) -> None:
        if not self.thr.set_system(name, value):
            GLib.idle_add(self._on_error, "The amp didn't accept that setting.")
        self._refresh_requested = True

    def _cmd_load_preset(self, preset: dict, name: str, keep_backup: bool, hold: dict | None = None) -> None:
        backup = None
        current = self.last_patch
        if keep_backup or current is None:
            current = self.thr.dump()
            if keep_backup:
                backup = thrl6p.from_patch(current, "Tone before presets", firmware=self.thr.firmware)
        LOG.info("Loading preset %r%s", name, f", keeping {sorted(p for _, p in hold)}" if hold else "")
        def progress(done: int, total: int) -> None:
            GLib.idle_add(self._on_result, "progress", name, done, total)

        try:
            skipped = thrl6p.apply(self.thr, preset, hold, current, progress)
        except Exception:
            GLib.idle_add(self._on_result, "failed", name)
            raise
        if skipped:
            LOG.debug("Not accepted: %s", skipped)
        self._refresh_requested = True
        GLib.idle_add(self._on_result, "loaded", name, backup, skipped)

    def _cmd_store_memory(self, index: int, name: str) -> None:
        from ..patch import rename_dump
        try:
            dump = self.thr.dump_raw()
            if name:
                dump = rename_dump(dump, name)
            ok = self.thr.store_memory(index, dump)
        except THRError as err:
            GLib.idle_add(self._on_result, "stored", index, False, str(err))
            return
        except Exception as err:
            GLib.idle_add(self._on_result, "stored", index, False, str(err))
            raise
        self._refresh_requested = True
        GLib.idle_add(self._on_result, "stored", index, ok, None)

    def _cmd_store_preset(self, preset: dict, name: str, index: int, hold: dict | None, restore: bool) -> None:
        from ..patch import rename_dump
        if index in self.saved_memories:
            GLib.idle_add(self._on_result, "stored", index, False,
                          f"Memory {index + 1} was already saved. Turn the amp off and on before saving it again.")
            return
        try:
            before = self.thr.dump()
            backup = thrl6p.from_patch(before, "Tone before saving", firmware=self.thr.firmware) if restore else None

            def progress(done: int, total: int) -> None:
                GLib.idle_add(self._on_result, "progress", name, done, total)

            thrl6p.apply(self.thr, preset, hold, before, progress)
            dump = rename_dump(self.thr.dump_raw(), name)
            ok = self.thr.store_memory(index, dump)
            if backup is not None:
                LOG.info("Restoring the tone from before saving")
                thrl6p.apply(self.thr, backup)
        except Exception as err:
            GLib.idle_add(self._on_result, "stored", index, False, str(err))
            raise
        self._refresh_requested = True
        GLib.idle_add(self._on_result, "stored", index, ok, None)

    def _track(self, event) -> None:
        """Keep the cached settings in step with knob changes made on the amp."""
        unit = self.last_patch.find(event.unit) if self.last_patch is not None else None
        if unit is None or event.param is None:
            return
        value = event.value
        if event.param.endswith("Enable"):
            value = bool(value)
        elif event.param == "SpkSimType" and isinstance(value, float):
            value = int(value)
        unit.params[f"{event.param}State"] = value

    def _cmd_save_preset(self, path, name: str) -> None:
        preset = thrl6p.from_patch(self.thr.dump(), name, firmware=self.thr.firmware)
        GLib.idle_add(self._on_result, "saved", str(thrl6p.write(preset, path)))

    def _cmd_recall(self, index: int) -> None:
        if not self.thr.recall(index):
            GLib.idle_add(self._on_error, f"The amp didn't load user memory {index + 1}.")
        self._refresh_requested = True

    def _pump_events(self) -> None:
        for event in self.thr.poll_events(timeout=0.04):
            if event.opcode == 0x03 or (event.opcode == 0x02 and event.param == "recalled"):
                self._refresh_requested = True
            elif event.opcode == 0x04:
                self._track(event)
                GLib.idle_add(self._on_event, event)
