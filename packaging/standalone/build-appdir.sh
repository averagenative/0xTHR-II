#!/usr/bin/env bash
# Runs inside the thr2-appimage-builder container. Assembles a self-contained AppDir with
# Python, PyGObject, GTK 4, libadwaita, and GStreamer (the meter's four plugins), then writes
# /out/0xTHR-II-<version>-x86_64.AppImage.
set -euo pipefail
cd /src

APP_ID=io.github.averagenative.thr2
VERSION="$(python3 -c 'import thr2; print(thr2.__version__)')"
PYVER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
ARCHLIB=/usr/lib/x86_64-linux-gnu
APPDIR=/tmp/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR"/usr/{bin,lib,share} "$APPDIR/usr/lib/thr2" "$APPDIR/usr/lib/python3/dist-packages" \
    "$APPDIR/usr/lib/gstreamer-1.0" "$APPDIR/usr/libexec/gstreamer-1.0" "$APPDIR/usr/share/icons/Adwaita"

echo "== Python $PYVER and PyGObject"
cp "/usr/bin/python$PYVER" "$APPDIR/usr/bin/python3"
cp -a "/usr/lib/python$PYVER" "$APPDIR/usr/lib/"
rm -rf "$APPDIR/usr/lib/python$PYVER"/{test,idlelib,tkinter,turtledemo,ensurepip,pydoc_data,lib2to3,config-*}
rm -f "$APPDIR/usr/lib/python$PYVER"/lib-dynload/{_test*,xxlimited*,xxsubtype*,_xxtestfuzz*,_tkinter*}
cp -a /usr/lib/python3/dist-packages/{gi,cairo} "$APPDIR/usr/lib/python3/dist-packages/"
cp -a thr2 "$APPDIR/usr/lib/thr2/"
find "$APPDIR/usr/lib" -name __pycache__ -prune -exec rm -rf {} +

echo "== GObject type data"
mkdir -p "$APPDIR/usr/lib/girepository-1.0"
cp "$ARCHLIB"/girepository-1.0/*.typelib "$APPDIR/usr/lib/girepository-1.0/"

echo "== GStreamer"
for plugin in coreelements audioconvert level pipewire; do
    cp "$ARCHLIB/gstreamer-1.0/libgst$plugin.so" "$APPDIR/usr/lib/gstreamer-1.0/"
done
cp "$ARCHLIB/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner" "$APPDIR/usr/libexec/gstreamer-1.0/"
# libpipewire itself comes from the host (linuxdeploy's excludelist), so its modules must too.

echo "== Icons, desktop entry, metadata"
cp -a /usr/share/icons/Adwaita/{index.theme,symbolic,scalable} "$APPDIR/usr/share/icons/Adwaita/"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
    "$APPDIR/usr/share/applications" "$APPDIR/usr/share/metainfo"
cp /usr/share/icons/hicolor/index.theme "$APPDIR/usr/share/icons/hicolor/"
# gdk-pixbuf picks an image loader by MIME type through GIO, so SVG icons need the compiled
# shared-mime-info database. Hosts nearly always have one; this covers those that don't.
mkdir -p "$APPDIR/usr/share/mime"
cp /usr/share/mime/{mime.cache,globs,globs2,magic,aliases,subclasses,types,icons,generic-icons,XMLnamespaces,treemagic,version} \
    "$APPDIR/usr/share/mime/"
cp "data/$APP_ID.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
rsvg-convert -w 256 -h 256 "data/$APP_ID.svg" -o "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp "data/$APP_ID.svg" "$APPDIR/$APP_ID.svg"
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

echo "== linuxdeploy: shared libraries, GTK modules, pixbuf loaders, schemas"
export DEPLOY_GTK_VERSION=4
cp /opt/tools/linuxdeploy-plugin-gtk.sh /tmp/
LIBS=(libadwaita-1.so.0 libgtk-4.so.1 libgirepository-1.0.so.1 libgraphene-1.0.so.0 libpangocairo-1.0.so.0
      libgstreamer-1.0.so.0 libgstbase-1.0.so.0 libgstaudio-1.0.so.0 libgdk_pixbuf-2.0.so.0 librsvg-2.so.2)
ARGS=()
for lib in "${LIBS[@]}"; do ARGS+=(--library "$ARCHLIB/$lib"); done
for dir in "usr/lib/python$PYVER/lib-dynload" usr/lib/python3/dist-packages usr/lib/gstreamer-1.0 \
           usr/libexec/gstreamer-1.0; do
    ARGS+=(--deploy-deps-only "$APPDIR/$dir")
done
PATH=/tmp:$PATH linuxdeploy --appdir "$APPDIR" --plugin gtk --executable "$APPDIR/usr/bin/python3" "${ARGS[@]}" \
    --custom-apprun packaging/standalone/AppRun > /out/linuxdeploy.log 2>&1 || { tail -40 /out/linuxdeploy.log; exit 1; }

cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png" "$APPDIR/.DirIcon"
chmod 755 "$APPDIR/AppRun"
du -sh "$APPDIR"

echo "== appimagetool"
OUT="/out/0xTHR-II-$VERSION-x86_64.AppImage"
rm -f "$OUT"
ARCH=x86_64 appimagetool --no-appstream "$APPDIR" "$OUT" 2>&1 | grep -E "^Success|rror" || true
ls -la "$OUT"
