#!/usr/bin/env bash
# Build dist/0xTHR-II-<version>-x86_64.AppImage.
#
# The AppImage carries the pure-Python thr2 package, its icon, desktop entry, and AppStream
# metadata, and runs on the system's Python, PyGObject, GTK 4, libadwaita, and GStreamer
# (AppRun checks for them and explains what to install). appimagetool is downloaded into
# build/ on first use.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_ID=io.github.averagenative.thr2
VERSION="$(python3 -c 'import thr2; print(thr2.__version__)')"
APPDIR=build/AppDir
TOOL=build/appimagetool-x86_64.AppImage
OUT="dist/0xTHR-II-${VERSION}-x86_64.AppImage"
ICONS="$APPDIR/usr/share/icons/hicolor"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/thr2" "$ICONS/scalable/apps" "$ICONS/256x256/apps" \
    "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo" dist

cp -r thr2 "$APPDIR/usr/lib/thr2/"
find "$APPDIR/usr/lib/thr2" -name __pycache__ -prune -exec rm -rf {} +

cp "data/$APP_ID.svg" "$ICONS/scalable/apps/$APP_ID.svg"
rsvg-convert -w 256 -h 256 "data/$APP_ID.svg" -o "$ICONS/256x256/apps/$APP_ID.png"
cp "data/$APP_ID.svg" "$APPDIR/$APP_ID.svg"
cp "$ICONS/256x256/apps/$APP_ID.png" "$APPDIR/.DirIcon"

cat > "$APPDIR/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=THR-II Control
Comment=Control a Yamaha THR-II amp over USB or Bluetooth
Exec=thr2-gui
Icon=$APP_ID
Categories=AudioVideo;Audio;Music;
Keywords=guitar;amp;yamaha;thr;
StartupWMClass=$APP_ID
Terminal=false
X-AppImage-Version=$VERSION
DESKTOP
cp "$APPDIR/$APP_ID.desktop" "$APPDIR/usr/share/applications/"
desktop-file-validate "$APPDIR/$APP_ID.desktop"

sed -e "s/@VERSION@/$VERSION/" -e "s/@DATE@/$(date +%F)/" \
    "data/$APP_ID.metainfo.xml.in" > "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"

install -m 755 packaging/AppRun "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi

rm -f "$OUT"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
(cd dist && sha256sum "$(basename "$OUT")")
echo "Built $OUT"
