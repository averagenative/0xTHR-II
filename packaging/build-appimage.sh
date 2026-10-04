#!/usr/bin/env bash
# Build dist/0xTHR-II-<version>-x86_64.AppImage, fully standalone: Python, PyGObject, GTK 4,
# libadwaita, GStreamer, and the PipeWire client are bundled. The build runs in a Debian 13
# container (podman) so the result runs on any distribution with glibc 2.41 or later.
# The builder image is rebuilt only when packaging/standalone/Containerfile changes.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=thr2-appimage-builder
STAMP="$(sha256sum packaging/standalone/Containerfile | cut -c1-12)"
if ! podman image exists "$IMAGE:$STAMP"; then
    podman build -t "$IMAGE:$STAMP" packaging/standalone
fi
mkdir -p dist
podman run --rm -v "$PWD:/src:ro,z" -v "$PWD/dist:/out:z" "$IMAGE:$STAMP" bash /src/packaging/standalone/build-appdir.sh
VERSION="$(python3 -c 'import thr2; print(thr2.__version__)')"
(cd dist && sha256sum "0xTHR-II-$VERSION-x86_64.AppImage")
