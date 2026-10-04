#!/usr/bin/env bash
# Prove the AppImage is self-contained: run it in a container with only the desktop base
# libraries (no Python, GTK, libadwaita, GStreamer, or PyGObject), sharing only the Wayland
# display, and render the window in demo mode to dist/standalone-test.png. The container has no
# GPU, so GTK uses its software renderer (GSK_RENDERER=cairo), as on a machine without drivers.
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=thr2-desktop-base
podman image exists "$IMAGE" || podman build --arch amd64 -t "$IMAGE" -f packaging/standalone/Containerfile.desktop-base packaging/standalone
VERSION="$(python3 -c 'import thr2; print(thr2.__version__)')"
APPIMAGE="0xTHR-II-$VERSION-x86_64.AppImage"
[ -n "${WAYLAND_DISPLAY:-}" ] || { echo "Needs a Wayland session" >&2; exit 1; }

podman run --rm --arch amd64 --userns=keep-id --security-opt label=disable \
    -e WAYLAND_DISPLAY -e XDG_RUNTIME_DIR=/run/user/host -e APPIMAGE_EXTRACT_AND_RUN=1 -e HOME=/tmp/home -e GSK_RENDERER=cairo \
    -v "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/run/user/host/$WAYLAND_DISPLAY" \
    -v "$PWD/dist:/dist" -w /tmp "$IMAGE" bash -c "
        set -e
        mkdir -p /tmp/home
        echo '== What the container has:'
        for lib in libgtk-4.so.1 libadwaita-1.so.0 libgstreamer-1.0.so.0; do
            ls /usr/lib64/\$lib >/dev/null 2>&1 && echo \"  \$lib: present\" || echo \"  \$lib: absent\"
        done
        command -v python3 >/dev/null && echo '  python3: present' || echo '  python3: absent'
        echo '== AppImage:'
        /dist/$APPIMAGE --version
        /dist/$APPIMAGE cli paths | head -2
        timeout 40 /dist/$APPIMAGE --demo --screenshot /dist/standalone-test.png 2>&1 2>&1 | tail -12 || true
        ls -la /dist/standalone-test.png
    "
