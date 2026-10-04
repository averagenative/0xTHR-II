"""Preset mapping tests with a fake amp that records the commands it receives."""

import json
import tempfile
import unittest
from pathlib import Path

from thr2 import thrl6p
from thr2.patch import Patch, Unit

SAMPLE = {
    "data": {
        "device": 2359298,
        "device_version": 20971617,
        "meta": {"name": "Test Crunch", "tnid": 0},
        "tone": {
            "THRGroupAmp": {"@asset": "THR10C_DC30", "Bass": 0.6, "Drive": 0.55, "Master": 0.4,
                            "Mid": 0.5, "Treble": 0.7},
            "THRGroupCab": {"@asset": "speakerSimulator", "SpkSimType": 8},
            "THRGroupFX1Compressor": {"@asset": "RedComp", "@enabled": False, "Level": 0.8, "Sustain": 0.3},
            "THRGroupFX2Effect": {"@asset": "L6Flanger", "@enabled": True, "@wetDry": 0.25,
                                  "Depth": 0.4, "Freq": 0.2},
            "THRGroupFX3EffectEcho": {"@asset": "TapeEcho", "@enabled": False, "@wetDry": 0.2, "Time": 0.35},
            "THRGroupFX4EffectReverb": {"@asset": "StandardSpring", "@enabled": True, "@wetDry": 0.3,
                                        "Time": 0.5, "Tone": 0.6},
            "THRGroupGate": {"@asset": "noiseGate", "@enabled": True, "Decay": 0.2, "Thresh": -48.0},
            "global": {"THRPresetParamTempo": 110},
        },
    },
    "meta": {"original": 0, "pbn": 0, "premium": 0},
    "schema": "L6Preset",
    "version": 5,
}


class FakeTHR:
    def __init__(self):
        self.calls = []

    def set_unit_type(self, unit, symbol):
        self.calls.append(("type", unit, symbol))
        return True

    def set_param(self, unit, param, value):
        self.calls.append(("param", unit, param, value))
        return True


class PlanTest(unittest.TestCase):
    def test_amp_model_then_amp_knobs_first(self):
        steps = thrl6p.plan(SAMPLE)
        self.assertEqual(steps[0], ("type", "Amp", "THR10C_DC30"))
        self.assertEqual({s[2] for s in steps[1:6]}, {"Drive", "Master", "Bass", "Mid", "Treble"})
        for unit in ("FX1", "FX2", "FX3", "FX4"):
            switch = next(i for i, s in enumerate(steps) if s[:2] == ("type", unit))
            params = [i for i, s in enumerate(steps) if s[0] == "param" and s[1] == unit]
            self.assertTrue(all(i > switch for i in params), unit)

    def test_maps_every_group(self):
        thr = FakeTHR()
        self.assertEqual(thrl6p.apply(thr, SAMPLE), [])
        calls = set(thr.calls)
        for expected in [
            ("type", "Amp", "THR10C_DC30"),
            ("type", "FX2", "L6Flanger"),
            ("param", "Amp", "Drive", 0.55),
            ("param", "GuitarProc", "SpkSimType", 8.0),
            ("param", "GuitarProc", "FX1Enable", 0.0),
            ("param", "GuitarProc", "FX2Enable", 1.0),
            ("param", "GuitarProc", "FX2Mix", 0.25),
            ("param", "FX4", "Tone", 0.6),
            ("param", "GuitarProc", "Thresh", -48.0),
            ("param", "GuitarProc", "GateEnable", 1.0),
        ]:
            self.assertIn(expected, calls)

    def test_hold_keeps_master_right_after_model_switch(self):
        steps = thrl6p.plan(SAMPLE, hold={("Amp", "Master"): 0.2})
        self.assertNotIn(("param", "Amp", "Master", 0.4), steps)
        self.assertIn(("param", "Amp", "Master", 0.2), steps[1:6])
        self.assertIn(("param", "Amp", "Drive", 0.55), steps)

    def test_skips_settings_the_model_does_not_use(self):
        preset = json.loads(json.dumps(SAMPLE))
        preset["data"]["tone"]["THRGroupFX4EffectReverb"]["Decay"] = 0.9
        steps = thrl6p.plan(preset)
        self.assertNotIn("Decay", [s[2] for s in steps if s[1] == "FX4"])

    def test_skips_unchanged_settings(self):
        proc = Unit("GuitarProc", "Y2GuitarFlow", {
            "FX1EnableState": False, "FX2EnableState": True, "FX3EnableState": False, "FX4EnableState": True,
            "FX2MixState": 0.25, "FX3MixState": 0.2, "FX4MixState": 0.3, "GateEnableState": True,
            "ThreshState": -48.0, "DecayState": 0.2, "SpkSimTypeState": 8,
        })
        proc.units = {
            "FX1": Unit("FX1", "RedComp", {"LevelState": 0.8, "SustainState": 0.3}),
            "Amp": Unit("Amp", "THR10C_DC30", {"BassState": 0.6, "DriveState": 0.55, "MasterState": 0.4,
                                               "MidState": 0.5, "TrebleState": 0.7}),
            "FX2": Unit("FX2", "L6Flanger", {"DepthState": 0.4, "FreqState": 0.2}),
            "FX3": Unit("FX3", "TapeEcho", {"TimeState": 0.35}),
            "FX4": Unit("FX4", "StandardSpring", {"TimeState": 0.5, "ToneState": 0.6}),
        }
        current = Patch(meta={}, units={"GuitarProc": proc})
        self.assertEqual(thrl6p.plan(SAMPLE, current=current), [])
        proc.units["Amp"].params["MasterState"] = 0.9
        self.assertEqual(thrl6p.plan(SAMPLE, current=current), [("param", "Amp", "Master", 0.4)])
        self.assertEqual(thrl6p.plan(SAMPLE, hold={("Amp", "Master"): 0.9}, current=current), [])

    def test_rejects_non_presets(self):
        with self.assertRaises(thrl6p.PresetError):
            thrl6p.validate({"data": {}})


class RoundTripTest(unittest.TestCase):
    def test_patch_to_preset_and_back(self):
        proc = Unit("GuitarProc", "Y2GuitarFlow", {
            "FX1EnableState": False, "FX2EnableState": True, "FX3EnableState": False, "FX4EnableState": True,
            "FX2MixState": 0.4, "FX3MixState": 0.2, "FX4MixState": 0.3, "GateEnableState": True,
            "ThreshState": -33.0, "DecayState": 0.2, "SpkSimTypeState": 2,
        })
        proc.units = {
            "FX1": Unit("FX1", "RedComp", {"SustainState": 0.3, "LevelState": 0.83}),
            "Amp": Unit("Amp", "THR10X_Brown2", {"DriveState": 0.73, "MasterState": 0.61}),
            "FX2": Unit("FX2", "StereoSquareChorus", {"FreqState": 0.1, "SyncSelectState": 0}),
            "FX3": Unit("FX3", "TapeEcho", {"TimeState": 0.39}),
            "FX4": Unit("FX4", "ReallyLargeHall", {"DecayState": 0.15}),
        }
        preset = thrl6p.from_patch(Patch(meta={"name": "x"}, units={"GuitarProc": proc}), "Round trip",
                                   firmware=0x01400061)
        with tempfile.TemporaryDirectory() as tmp:
            path = thrl6p.write(preset, Path(tmp) / "round trip")
            self.assertEqual(path.suffix, ".thrl6p")
            loaded = thrl6p.read(path)
        self.assertEqual(loaded, json.loads(json.dumps(preset)))
        tone = loaded["data"]["tone"]
        self.assertEqual(tone["THRGroupAmp"], {"@asset": "THR10X_Brown2", "Drive": 0.73, "Master": 0.61})
        self.assertEqual(tone["THRGroupFX2Effect"]["@wetDry"], 0.4)
        self.assertNotIn("SyncSelect", tone["THRGroupFX2Effect"])
        thr = FakeTHR()
        thrl6p.apply(thr, loaded)
        self.assertIn(("param", "GuitarProc", "Thresh", -33.0), thr.calls)


if __name__ == "__main__":
    unittest.main()
