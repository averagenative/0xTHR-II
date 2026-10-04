#!/usr/bin/env bash
# Tag v<version>, push it, and publish a GitHub release with the wheel, source archive,
# AppImage, and SHA256SUMS. Release notes come from that version's CHANGELOG.md section.
# Run through `make release`, which builds and tests first.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="$1"
TAG="v$VERSION"
FILES=("dist/thr2-$VERSION-py3-none-any.whl" "dist/thr2-$VERSION.tar.gz" "dist/0xTHR-II-$VERSION-x86_64.AppImage")

for f in "${FILES[@]}"; do [ -f "$f" ] || { echo "Missing $f" >&2; exit 1; }; done
if [ -n "$(git status --porcelain)" ]; then
    echo "Commit your changes before releasing." >&2
    exit 1
fi

(cd dist && sha256sum "${FILES[@]##*/}" > SHA256SUMS)
NOTES="$(mktemp)"
awk -v v="## $VERSION " 'index($0, v) == 1 {f=1; next} /^## /{f=0} f' CHANGELOG.md > "$NOTES"
[ -s "$NOTES" ] || { echo "No CHANGELOG.md section for $VERSION" >&2; exit 1; }

git rev-parse "$TAG" >/dev/null 2>&1 || git tag -a "$TAG" -m "0xTHR-II $VERSION"
git push -q origin HEAD "$TAG"
if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" "${FILES[@]}" dist/SHA256SUMS --clobber
else
    gh release create "$TAG" --title "0xTHR-II $VERSION" --notes-file "$NOTES" "${FILES[@]}" dist/SHA256SUMS
fi
rm -f "$NOTES"
gh release view "$TAG" --json url -q .url
