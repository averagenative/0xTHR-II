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


def plan(preset: dict) -> list[tuple]:
    """Turn a preset into an ordered list of amp commands.

    Model switches come first, because selecting a model resets that unit's settings.
    Each step is ("type", unit, symbol) or ("param", unit, param, value).
    """
    tone = validate(preset)["data"]["tone"]
    steps: list[tuple] = []
    amp = tone.get("THRGroupAmp", {})
    if amp.get("@asset"):
        steps.append(("type", "Amp", amp["@asset"]))
    for group, unit in FX_GROUPS.items():
        asset = tone.get(group, {}).get("@asset")
        if asset:
            steps.append(("type", unit, asset))

    for key, value in amp.items():
        if not key.startswith("@") and (number := _number(value)) is not None:
            steps.append(("param", "Amp", key, number))
    cab = _number(tone.get("THRGroupCab", {}).get("SpkSimType"))
    if cab is not None:
        steps.append(("param", PROC, "SpkSimType", cab))
    for group, unit in FX_GROUPS.items():
        settings = tone.get(group, {})
        for key, value in settings.items():
            if not key.startswith("@") and (number := _number(value)) is not None:
                steps.append(("param", unit, key, number))
        if "@wetDry" in settings and (mix := _number(settings["@wetDry"])) is not None:
            steps.append(("param", PROC, f"{unit}Mix", mix))
        if "@enabled" in settings:
            steps.append(("param", PROC, f"{unit}Enable", 1.0 if settings["@enabled"] else 0.0))
    gate = tone.get("THRGroupGate", {})
    for key in ("Thresh", "Decay"):
        if (number := _number(gate.get(key))) is not None:
            steps.append(("param", PROC, key, number))
    if "@enabled" in gate:
        steps.append(("param", PROC, "GateEnable", 1.0 if gate["@enabled"] else 0.0))
    return steps


def apply(thr, preset: dict) -> list[str]:
    """Send a preset to the amp. Returns notes about settings the amp skipped."""
    from .client import THRError

    skipped = []
    for step in plan(preset):
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
