#!/usr/bin/env bash
# Render the README screenshots in demo mode (no amp needed): the main window and every theme,
# plus a 480-pixel thumbnail of each. Settings go to a throwaway folder, so your own theme
# choice is left alone. Needs a graphical session and ImageMagick.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=docs/screenshots
mkdir -p "$OUT/thumbs"
export XDG_CONFIG_HOME="$(mktemp -d)"
trap 'rm -rf "$XDG_CONFIG_HOME"' EXIT

shot() {    # shot NAME THEME
    python3 -m thr2.gui --demo --theme "$2" --height 760 --screenshot "$OUT/$1.png" >/dev/null 2>&1
}
shot main cream
for theme in cream white black neon metal adwaita; do
    shot "theme-$theme" "$theme"
done

# Full size as lossless WebP (smallest for the textured themes), thumbnails as JPEG.
for png in "$OUT"/*.png; do
    name="$(basename "$png" .png)"
    magick "$png" -resize 480x -strip -quality 85 "$OUT/thumbs/$name.jpg"
    magick "$png" -strip -define webp:lossless=true "$OUT/$name.webp"
    rm "$png"
done
du -sh "$OUT"
