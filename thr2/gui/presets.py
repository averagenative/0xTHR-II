"""Preset browser: your folder plus the community collection, with search and audition.

Clicking a preset loads it into the amp right away, so you can try several in a row. The
tone you had before the first one is kept, and a banner offers to restore it.
"""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .. import library, thrl6p  # noqa: E402
from ..client import AMP_NAMES  # noqa: E402

EFFECT_NAMES = {
    "RedComp": "Compressor", "StereoSquareChorus": "Chorus", "L6Flanger": "Flanger", "Phaser": "Phaser",
    "BiasTremolo": "Tremolo", "TapeEcho": "Tape echo", "L6DigitalDelay": "Digital delay",
    "StandardSpring": "Spring", "LargePlate1": "Plate", "ReallyLargeHall": "Hall", "SmallRoom1": "Room",
}


def describe(entry: library.Entry) -> str:
    parts = [AMP_NAMES.get(entry.amp, entry.amp)]
    effects = [EFFECT_NAMES.get(e, e) for e in entry.effects]
    parts.append(", ".join(effects) if effects else "No effects")
    if entry.note:
        parts.append(entry.note)
    return ". ".join(p for p in parts if p)


class PresetsDialog(Adw.Dialog):
    def __init__(self, window):
        super().__init__(title="Presets", content_width=600, content_height=680)
        self.window = window
        self.rows: list[tuple[Adw.ActionRow, library.Entry]] = []

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)
        self.search = Gtk.SearchEntry(placeholder_text="Search presets", hexpand=True,
                                      margin_start=12, margin_end=12, margin_bottom=6)
        self.search.connect("search-changed", self._filter)
        view.add_top_bar(self.search)
        self.banner = Adw.Banner(title="Original tone saved. To keep a preset, hold a USER MEMORY button.",
                                 button_label="Restore original")
        self.banner.connect("button-clicked", self._restore)
        view.add_top_bar(self.banner)

        self.page = Adw.PreferencesPage()
        view.set_content(self.page)
        self.toasts.set_child(view)
        self.set_child(self.toasts)

        save = Gtk.Button(label="Save current tone", valign=Gtk.Align.CENTER)
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        open_file = Gtk.Button(label="Open file", valign=Gtk.Align.CENTER)
        open_file.connect("clicked", self._open_file)
        folder = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text=f"Open {library.USER_DIR}")
        folder.connect("clicked", self._open_folder)
        actions = Gtk.Box(spacing=6)
        actions.append(folder)
        actions.append(open_file)
        actions.append(save)
        self.user_group = Adw.PreferencesGroup(
            title="Your presets",
            description=f"Files in {library.USER_DIR.relative_to(Path.home()).as_posix()} in your home folder",
            header_suffix=actions,
        )
        update = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Download the collection again")
        update.connect("clicked", lambda _b: self._download())
        self.community_group = Adw.PreferencesGroup(
            title="Community presets",
            description=f"Song and artist tones from github.com/{library.COMMUNITY_REPO}",
            header_suffix=update,
        )
        self.page.add(self.user_group)
        self.page.add(self.community_group)
        self._populate()
        if not library.community_ready():
            self._download()

    def _clear(self, group: Adw.PreferencesGroup) -> None:
        for row, entry in list(self.rows):
            if row.get_parent() and row.get_ancestor(Adw.PreferencesGroup) is group:
                group.remove(row)
                self.rows.remove((row, entry))

    def _populate(self) -> None:
        self._clear(self.user_group)
        self._clear(self.community_group)
        for group, entries, empty in (
            (self.user_group, library.user(), "Save a tone or copy .thrl6p files here."),
            (self.community_group, library.community(), "Downloading the collection..."),
        ):
            if not entries:
                row = Adw.ActionRow(title=empty)
                row.add_css_class("dim-label")
                group.add(row)
                self.rows.append((row, None))
            for entry in entries:
                row = Adw.ActionRow(title=GLib.markup_escape_text(entry.name), subtitle=GLib.markup_escape_text(describe(entry)),
                                    activatable=True)
                row.add_suffix(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
                row.connect("activated", self._activate, entry)
                group.add(row)
                self.rows.append((row, entry))
        self._filter(self.search)

    def _filter(self, entry_widget) -> None:
        query = entry_widget.get_text().strip().lower()
        for row, entry in self.rows:
            if entry is None:
                row.set_visible(not query)
            else:
                row.set_visible(not query or query in entry.name.lower() or query in describe(entry).lower())

    def _download(self) -> None:
        def work():
            try:
                count = library.download_community()
                GLib.idle_add(self._downloaded, f"Downloaded {count} community presets.")
            except OSError as err:
                GLib.idle_add(self._downloaded, f"Couldn't download the community presets: {err}")
        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, message: str) -> None:
        self._populate()
        self.toasts.add_toast(Adw.Toast(title=message, timeout=3))

    def _activate(self, _row, entry: library.Entry) -> None:
        try:
            preset = thrl6p.read(entry.path)
        except thrl6p.PresetError as err:
            self.toasts.add_toast(Adw.Toast(title=str(err)))
            return
        self._load(preset, entry.name)

    def _load(self, preset: dict, name: str) -> None:
        if not self.window.is_connected():
            self.toasts.add_toast(Adw.Toast(title="Connect the amp to load presets."))
            return
        self.window.load_preset(preset, name)
        self.toasts.add_toast(Adw.Toast(title=f"Loaded {name}", timeout=3))

    def show_original_saved(self) -> None:
        self.banner.set_revealed(True)

    def _restore(self, _banner) -> None:
        self.window.restore_original()
        self.banner.set_revealed(False)
        self.toasts.add_toast(Adw.Toast(title="Restored your original tone.", timeout=3))

    def _open_folder(self, _button) -> None:
        library.USER_DIR.mkdir(parents=True, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(library.USER_DIR))).launch(self.window, None, None)

    def _open_file(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Open a THR-II preset")
        flt = Gtk.FileFilter(name="THR-II presets")
        flt.add_pattern("*.thrl6p")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dialog.set_filters(filters)
        dialog.set_initial_folder(Gio.File.new_for_path(str(Path.home() / "Downloads")))
        dialog.open(self.window, None, self._opened)

    def _opened(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        try:
            preset = thrl6p.read(file.get_path())
        except thrl6p.PresetError as err:
            self.toasts.add_toast(Adw.Toast(title=str(err)))
            return
        self._load(preset, thrl6p.name_of(preset, Path(file.get_path()).stem))

    def _save(self, _button) -> None:
        if not self.window.is_connected():
            self.toasts.add_toast(Adw.Toast(title="Connect the amp to save its tone."))
            return
        library.USER_DIR.mkdir(parents=True, exist_ok=True)
        dialog = Gtk.FileDialog(title="Save the current tone", initial_name="My tone.thrl6p")
        dialog.set_initial_folder(Gio.File.new_for_path(str(library.USER_DIR)))
        dialog.save(self.window, None, self._saved)

    def _saved(self, dialog, result) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        path = Path(file.get_path())
        self.window.save_preset(path, path.stem)

    def saved(self, path: str) -> None:
        self._populate()
        self.toasts.add_toast(Adw.Toast(title=f"Saved {Path(path).name}", timeout=3))
