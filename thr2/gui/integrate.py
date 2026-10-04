"""Desktop integration for the AppImage: ``--install`` and ``--uninstall``.

Copies the AppImage to ~/Applications, installs its icon into the user's hicolor theme,
and writes a desktop entry so GNOME shows THR-II Control in the app grid with its icon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ID = "io.github.averagenative.thr2"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
APPLICATIONS = Path.home() / "Applications"
DESKTOP = DATA / "applications" / f"{APP_ID}.desktop"
ICONS = {
    "scalable": DATA / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg",
    "256x256": DATA / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_ID}.png",
}


def _refresh() -> None:
    for command in (["update-desktop-database", str(DATA / "applications")],
                    ["gtk-update-icon-cache", "-q", "-t", str(DATA / "icons" / "hicolor")]):
        try:
            subprocess.run(command, check=False, capture_output=True)
        except OSError:
            pass


def install() -> int:
    appimage = os.environ.get("APPIMAGE")
    appdir = os.environ.get("THR2_APPDIR")
    if not appimage or not appdir:
        print("Run --install from the AppImage, for example: ./0xTHR-II-1.0.0-x86_64.AppImage --install")
        return 1
    from .. import __version__

    APPLICATIONS.mkdir(parents=True, exist_ok=True)
    target = APPLICATIONS / Path(appimage).name
    if Path(appimage).resolve() != target.resolve():
        shutil.copy2(appimage, target)
    target.chmod(0o755)
    for size, dest in ICONS.items():
        source = Path(appdir) / "usr" / "share" / "icons" / "hicolor" / size / "apps" / dest.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    DESKTOP.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=THR-II Control\n"
        "Comment=Control a Yamaha THR-II amp over USB or Bluetooth\n"
        f"Exec={target}\n"
        f"TryExec={target}\n"
        f"Icon={APP_ID}\n"
        "Categories=AudioVideo;Audio;Music;\n"
        "Keywords=guitar;amp;yamaha;thr;\n"
        f"StartupWMClass={APP_ID}\n"
        "Terminal=false\n"
        f"X-AppImage-Version={__version__}\n"
    )
    _refresh()
    print(f"Installed THR-II Control {__version__}: {target}")
    print("It's in the app grid now. Run the AppImage with --uninstall to remove the menu entry and icon.")
    others = [p for p in APPLICATIONS.glob("0xTHR-II-*.AppImage") if p.resolve() != target.resolve()]
    if others:
        print("Older versions in ~/Applications you can delete: " + ", ".join(p.name for p in others))
    return 0


def uninstall() -> int:
    removed = [p for p in [DESKTOP, *ICONS.values()] if p.exists()]
    for path in removed:
        path.unlink()
    _refresh()
    print("Removed the THR-II Control menu entry and icon." if removed else "Nothing to remove.")
    leftovers = sorted(APPLICATIONS.glob("0xTHR-II-*.AppImage"))
    if leftovers:
        print("The AppImage files are still in ~/Applications: " + ", ".join(p.name for p in leftovers))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["--install"]:
        return install()
    if args[:1] == ["--uninstall"]:
        return uninstall()
    print("Usage: python3 -m thr2.gui.integrate --install | --uninstall")
    return 2


if __name__ == "__main__":
    sys.exit(main())
