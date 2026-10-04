"""Per-user app preferences in ~/.config/thr2/settings.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "thr2" / "settings.json"
DEFAULTS = {"knob_step": 2, "keep_knobs": True, "theme": "adwaita", "debug": False,
            "preset_keep_master": True, "preset_keep_gain": False}


def load() -> dict:
    try:
        return {**DEFAULTS, **json.loads(PATH.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(settings: dict) -> None:
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(settings, indent=2))
    except OSError:
        pass
