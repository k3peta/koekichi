#!/usr/bin/env bash
# Build KoeKichi-<ver>-mac-arm64.dmg from dist/KoeKichi.app (SPEC §18.4).
#
# Stages KoeKichi.app plus an /Applications symlink in a temp directory,
# then uses `hdiutil create -format UDZO` to produce a compressed DMG.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_PATH="dist/KoeKichi.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "dist/KoeKichi.app not found. Run packaging/build_mac.sh first." >&2
  exit 1
fi

VERSION="$(uv run python -c 'from koekichi import __version__; print(__version__)')"
DMG_NAME="KoeKichi-${VERSION}-mac-arm64.dmg"
DMG_PATH="dist/${DMG_NAME}"

STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

echo "==> Staging DMG contents in ${STAGING_DIR}"
cp -R "$APP_PATH" "$STAGING_DIR/KoeKichi.app"
ln -s /Applications "$STAGING_DIR/Applications"

rm -f "$DMG_PATH"

echo "==> Building ${DMG_PATH}"
hdiutil create -volname "KoeKichi ${VERSION}" \
  -srcfolder "$STAGING_DIR" \
  -format UDZO \
  -ov \
  "$DMG_PATH"

echo "==> Built ${DMG_PATH}"
du -sh "$DMG_PATH"
