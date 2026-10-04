"""Demo mode: the full window with sample settings and no amp, for screenshots and testing."""

from __future__ import annotations

from ..patch import Patch, Unit
from .worker import AmpState


class DemoWorker:
    """Stands in for AmpWorker: accepts commands and does nothing."""

    def __init__(self, on_state, on_event, on_status, on_error, on_result=None):
        self.on_state, self.on_status = on_state, on_status
        self.saved_memories: set = set()

    def start(self) -> None:
        from gi.repository import GLib

        GLib.idle_add(lambda: (self.on_status(True, "USB"), self.on_state(sample_state()), False)[-1])

    def stop(self) -> None:
        pass

    def is_alive(self) -> bool:
        return True

    def set_param(self, *args) -> None:
        pass

    def submit(self, *args) -> None:
        pass

    def connect_bluetooth(self) -> None:
        pass


def sample_state() -> AmpState:
    proc = Unit("GuitarProc", "Y2GuitarFlow", {
        "FX1EnableState": False, "FX2EnableState": True, "FX3EnableState": False, "FX4EnableState": True,
        "FX1MixState": 1.0, "FX2MixState": 0.35, "FX3MixState": 0.2, "FX4MixState": 0.28,
        "GateEnableState": True, "ThreshState": -48.0, "DecayState": 0.2, "SpkSimTypeState": 2,
    })
    proc.units = {
        "FX1": Unit("FX1", "RedComp", {"SustainState": 0.3, "LevelState": 0.83}),
        "Amp": Unit("Amp", "THR10C_DC30", {"DriveState": 0.62, "MasterState": 0.45, "BassState": 0.55,
                                           "MidState": 0.6, "TrebleState": 0.7}),
        "FX2": Unit("FX2", "StereoSquareChorus", {"FreqState": 0.2, "DepthState": 0.3, "PreState": 0.5,
                                                  "FeedbackState": 0.15}),
        "FX3": Unit("FX3", "TapeEcho", {"TimeState": 0.39, "FeedbackState": 0.33, "BassState": 0.5,
                                        "TrebleState": 0.26}),
        "FX4": Unit("FX4", "LargePlate1", {"DecayState": 0.35, "PreDelayState": 0.2, "ToneState": 0.6}),
    }
    return AmpState(
        identity={"model": 2}, firmware="1.40.0a (demo)", patch=Patch(meta={"name": "Demo tone"}, units={"GuitarProc": proc}),
        globals={"GuitarVolume": 0.5, "AudioVolume": 0.5},
        system={"guitar_di_mode": 0, "extended_stereo": 0, "user_setting": 0, "user_setting_changed": 0},
        memory_names=["Clean", "Crunch", "Lead", "Hi Gain", "Demo tone"],
    )
