"""Read, apply, and write THR Remote preset files (.thrl6p).

A .thrl6p file is JSON. ``data.tone`` holds one group per unit: the amp, the cabinet, the
four effects (each with ``@asset`` for the model, ``@enabled``, and ``@wetDry`` for the mix),
and the noise gate. Applying a preset uses only the amp's live-edit commands (model switch,
parameter set), so it changes the current tone the way THR Remote does. To keep it, save it
to a user memory on the amp.
"""

from __future__ import annotations

import json
from pathlib import Path

from .patch import Patch

SCHEMA = "L6Preset"
FX_GROUPS = {
    "THRGroupFX1Compressor": "FX1",
    "THRGroupFX2Effect": "FX2",
    "THRGroupFX3EffectEcho": "FX3",
    "THRGroupFX4EffectReverb": "FX4",
}
PROC = "GuitarProc"


class PresetError(ValueError):
    pass


def read(path: str | Path) -> dict:
    try:
        preset = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        raise PresetError(f"Can't read {path}: {err}") from err
    return validate(preset)


def validate(preset: dict) -> dict:
    tone = preset.get("data", {}).get("tone") if isinstance(preset, dict) else None
    if not isinstance(tone, dict) or "THRGroupAmp" not in tone:
        raise PresetError("Not a THR-II preset: no data.tone.THRGroupAmp.")
    return preset


def name_of(preset: dict, fallback: str = "") -> str:
    return str(preset.get("data", {}).get("meta", {}).get("name") or fallback)


def summary(preset: dict) -> dict:
    """Short facts for listing a preset: name, amp model, enabled effects, and source note."""
    tone = preset["data"]["tone"]
    effects = [g.get("@asset", "") for key, g in tone.items() if key in FX_GROUPS and g.get("@enabled")]
    return {
        "name": name_of(preset),
        "amp": tone.get("THRGroupAmp", {}).get("@asset", ""),
        "effects": effects,
        "source": preset.get("data", {}).get("meta", {}).get("source", ""),
    }


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


MODEL_PARAMS = {
    "RedComp": ("Sustain", "Level"),
    "StereoSquareChorus": ("Freq", "Depth", "Pre", "Feedback"),
    "L6Flanger": ("Freq", "Depth"),
    "Phaser": ("Speed", "Feedback"),
    "BiasTremolo": ("Speed", "Depth"),
    "TapeEcho": ("Time", "Feedback", "Bass", "Treble"),
    "L6DigitalDelay": ("Time", "Feedback", "Bass", "Treble"),
    "StandardSpring": ("Time", "Tone"),
    "LargePlate1": ("Decay", "PreDelay", "Tone"),
    "ReallyLargeHall": ("Decay", "PreDelay", "Tone"),
    "SmallRoom1": ("Decay", "PreDelay", "Tone"),
}
AMP_PARAMS = ("Drive", "Master", "Bass", "Mid", "Treble")
SAME = 0.0005


def _current(patch: Patch | None, unit: str, param: str):
    """A setting's value in a patch dump, or None when unknown."""
    if patch is None:
        return None
    found = patch.find(unit)
    return found.params.get(f"{param}State") if found else None


def _differs(old, new: float) -> bool:
    if isinstance(old, bool):
        old = 1.0 if old else 0.0
    if not isinstance(old, (int, float)):
        return True
    return abs(float(old) - new) > SAME


def plan(preset: dict, hold: dict | None = None, current: Patch | None = None) -> list[tuple]:
    """Turn a preset into an ordered list of amp commands.

    Each step is ("type", unit, symbol) or ("param", unit, param, value). The order keeps
    the transition short and quiet: the amp model, then its knobs (selecting a model
    resets them to 0.5), then the cabinet, then each effect's model and settings, then
    mixes, switches, and the gate.

    ``hold`` maps (unit, param) to a value to keep instead of the preset's, for example
    {("Amp", "Master"): 0.3}. ``current`` is a dump of the amp's settings; when given,
    steps that wouldn't change anything are left out. Settings the chosen effect model
    doesn't use are always left out.
    """
    hold = hold or {}
    tone = validate(preset)["data"]["tone"]
    steps: list[tuple] = []

    def param(unit: str, name: str, value: float, forced: bool = False) -> None:
        if forced or current is None or _differs(_current(current, unit, name), value):
            steps.append(("param", unit, name, value))

    amp = tone.get("THRGroupAmp", {})
    asset = amp.get("@asset")
    current_amp = current.find("Amp").type if current is not None and current.find("Amp") else None
    amp_switched = bool(asset) and asset != current_amp
    if amp_switched:
        steps.append(("type", "Amp", asset))
    for name in AMP_PARAMS:
        value = hold.get(("Amp", name), _number(amp.get(name)))
        if value is not None:
            param("Amp", name, float(value), forced=amp_switched)

    cab = _number(tone.get("THRGroupCab", {}).get("SpkSimType"))
    if cab is not None:
        param(PROC, "SpkSimType", cab)

    for group, unit in FX_GROUPS.items():
        settings = tone.get(group, {})
        model = settings.get("@asset")
        current_model = current.find(unit).type if current is not None and current.find(unit) else None
        switched = bool(model) and model != current_model
        if switched:
            steps.append(("type", unit, model))
        for name in MODEL_PARAMS.get(model or current_model, ()):
            value = hold.get((unit, name), _number(settings.get(name)))
            if value is not None:
                param(unit, name, float(value), forced=switched)

    for group, unit in FX_GROUPS.items():
        settings = tone.get(group, {})
        if (mix := _number(settings.get("@wetDry"))) is not None:
            param(PROC, f"{unit}Mix", mix)
        if "@enabled" in settings:
            param(PROC, f"{unit}Enable", 1.0 if settings["@enabled"] else 0.0)

    gate = tone.get("THRGroupGate", {})
    for name in ("Thresh", "Decay"):
        if (number := _number(gate.get(name))) is not None:
            param(PROC, name, number)
    if "@enabled" in gate:
        param(PROC, "GateEnable", 1.0 if gate["@enabled"] else 0.0)
    return steps


def apply(thr, preset: dict, hold: dict | None = None, current: Patch | None = None) -> list[str]:
    """Send a preset to the amp. Returns notes about settings the amp skipped."""
    from .client import THRError

    steps = plan(preset, hold, current)
    try:
        return thr.batch(steps)
    except (AttributeError, THRError):
        pass
    skipped = []
    for step in steps:
        try:
            if step[0] == "type":
                ok = thr.set_unit_type(step[1], step[2])
            else:
                ok = thr.set_param(step[1], step[2], step[3])
        except THRError as err:
            skipped.append(f"{step[1]} {step[2]}: {err}")
            continue
        if not ok:
            skipped.append(f"{step[1]} {step[2]}: not accepted")
    return skipped


def to_patch(preset: dict, base: Patch, hold: dict | None = None) -> Patch:
    """Predict the amp's settings after applying a preset, starting from ``base``.

    The app uses this to move its knobs right away, before the amp confirms.
    """
    from copy import deepcopy

    patch = deepcopy(base)
    proc, amp = patch.find(PROC), patch.find("Amp")
    if proc is None or amp is None:
        return patch
    for step in plan(preset, hold):
        if step[0] == "type":
            unit = patch.find(step[1])
            if unit is not None:
                unit.type = step[2]
                if step[1] != "Amp":
                    unit.params = {}
            continue
        _, unit_name, name, value = step
        unit = patch.find(unit_name)
        if unit is None:
            continue
        if name.endswith("Enable"):
            unit.params[f"{name}State"] = bool(value)
        elif name == "SpkSimType":
            unit.params[f"{name}State"] = int(value)
        else:
            unit.params[f"{name}State"] = value
    return patch


def from_patch(patch: Patch, name: str, device: int = 0x240002, firmware: int = 0) -> dict:
    """Build a .thrl6p preset from a patch dump of the amp's current settings."""
    proc = patch.find(PROC)
    amp = patch.find("Amp")
    if not proc or not amp:
        raise PresetError("The settings dump has no amp or GuitarProc unit.")

    def params(unit) -> dict:
        return {k.removesuffix("State"): v for k, v in unit.params.items()
                if isinstance(v, float) and not k.startswith("SyncSelect")}

    tone = {"THRGroupAmp": {"@asset": amp.type, **params(amp)}}
    cab = proc.params.get("SpkSimTypeState")
    if isinstance(cab, (int, float)) and not isinstance(cab, bool):
        tone["THRGroupCab"] = {"@asset": "speakerSimulator", "SpkSimType": int(cab)}
    for group, unit_name in FX_GROUPS.items():
        unit = patch.find(unit_name)
        if not unit:
            continue
        entry = {"@asset": unit.type, "@enabled": bool(proc.params.get(f"{unit_name}EnableState"))}
        if unit_name != "FX1":
            entry["@wetDry"] = proc.params.get(f"{unit_name}MixState", 0.0)
        entry.update(params(unit))
        tone[group] = entry
    tone["THRGroupGate"] = {
        "@asset": "noiseGate",
        "@enabled": bool(proc.params.get("GateEnableState")),
        "Decay": proc.params.get("DecayState", 0.2),
        "Thresh": proc.params.get("ThreshState", -60.0),
    }
    tempo = patch.meta.get("tempo")
    tone["global"] = {"THRPresetParamTempo": int(tempo) if isinstance(tempo, (int, float)) and tempo else 110}
    return {
        "data": {
            "device": device,
            "device_version": firmware,
            "meta": {"name": name, "tnid": 0},
            "tone": tone,
        },
        "meta": {"original": 0, "pbn": 0, "premium": 0},
        "schema": SCHEMA,
        "version": 5,
    }


def write(preset: dict, path: str | Path) -> Path:
    path = Path(path)
    if path.suffix != ".thrl6p":
        path = path.with_suffix(".thrl6p")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preset, indent=4) + "\n", encoding="utf-8")
    return path
