"""Preset sources: the community collection on GitHub and the user's own folder.

The community collection is github.com/f3sty/Yamaha_THRII_presets (234 song and artist
tones gathered from a shared spreadsheet). It has no license, so this project doesn't
redistribute it; it downloads the collection's zip on request into the user's cache.
"""

from __future__ import annotations

import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import thrl6p

COMMUNITY_REPO = "f3sty/Yamaha_THRII_presets"
COMMUNITY_ZIP = f"https://raw.githubusercontent.com/{COMMUNITY_REPO}/HEAD/presets/0_All_Presets.zip"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "thr2" / "community"


def _music_dir() -> Path:
    """The desktop's Music folder (localized names included), falling back to ~/Music."""
    try:
        from gi.repository import GLib
        music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
        if music:
            return Path(music)
    except Exception:
        pass
    return Path.home() / "Music"


USER_DIR = _music_dir() / "THR-II Presets"


@dataclass
class Entry:
    name: str
    path: Path
    source: str
    amp: str = ""
    effects: tuple = ()
    note: str = ""


def community_ready() -> bool:
    return CACHE.is_dir() and any(CACHE.glob("*.thrl6p"))


def download_community(timeout: float = 30.0) -> int:
    """Download and unpack the community collection. Returns the number of presets."""
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / "all.zip"
    request = urllib.request.Request(COMMUNITY_ZIP, headers={"User-Agent": "thr2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        archive.write_bytes(response.read())
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            name = Path(member).name
            if name.endswith(".thrl6p") and not name.startswith("."):
                (CACHE / name).write_bytes(zf.read(member))
                count += 1
    archive.unlink(missing_ok=True)
    return count


def _entries(folder: Path, source: str) -> list[Entry]:
    entries = []
    for path in sorted(folder.glob("*.thrl6p"), key=lambda p: p.name.lower()):
        try:
            info = thrl6p.summary(thrl6p.read(path))
        except thrl6p.PresetError:
            continue
        entries.append(Entry(info["name"] or path.stem, path, source, info["amp"], tuple(info["effects"]),
                             info["source"]))
    return entries


def community() -> list[Entry]:
    return _entries(CACHE, "Community") if CACHE.is_dir() else []


def user() -> list[Entry]:
    return _entries(USER_DIR, "Yours") if USER_DIR.is_dir() else []


def find(query: str) -> list[Entry]:
    """Presets whose name contains ``query``, case-insensitively; an exact match wins."""
    pool = user() + community()
    exact = [e for e in pool if e.name.lower() == query.lower() or e.path.stem.lower() == query.lower()]
    return exact or [e for e in pool if query.lower() in e.name.lower()]
