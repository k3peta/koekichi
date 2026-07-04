#!/usr/bin/env bash
# Build KoeKichi.app for macOS (SPEC §18.4).
#
# arm64 only — this script refuses to run under Rosetta/Intel because the
# resulting .app must be ad-hoc signed as arm64 (SPEC §18.1); it does not
# cross-build.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_mac.sh must be run on macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "build_mac.sh must be run on Apple Silicon (arm64); no cross-build support." >&2
  exit 1
fi

echo "==> uv sync"
uv sync

if [[ ! -f packaging/icon.icns ]]; then
  echo "==> Generating icons (packaging/make_icons.py)"
  QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py
fi

echo "==> Cleaning previous build output"
rm -rf build dist

echo "==> Running PyInstaller"
uv run pyinstaller packaging/koekichi-mac.spec --noconfirm

# Sign the app with a stable identity if available (SPEC §18.1).
# Preference order:
#   1. $KOEKICHI_SIGN_IDENTITY (name or SHA-1 hash, explicit override)
#   2. "KoeKichi Self-Signed" (created by packaging/make_signing_cert.sh)
#   3. Any "Apple Development" identity (e.g. from Xcode) — selected by
#      SHA-1 hash to avoid shell encoding issues with non-ASCII names.
echo "==> Signing the app (SPEC §18.1)"
IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
SIGN_ID="${KOEKICHI_SIGN_IDENTITY:-}"
if [[ -z "$SIGN_ID" ]] && grep -q "KoeKichi Self-Signed" <<<"$IDENTITIES"; then
  SIGN_ID="KoeKichi Self-Signed"
fi
if [[ -z "$SIGN_ID" ]]; then
  SIGN_ID="$(grep "Apple Development" <<<"$IDENTITIES" | head -1 | awk '{print $2}')"
fi

if [[ -n "$SIGN_ID" ]]; then
  echo "==> Signing with stable identity: $SIGN_ID"
  codesign --force --deep --identifier jp.koekichi.app --sign "$SIGN_ID" dist/KoeKichi.app
  # Verify signature
  if codesign -dvv dist/KoeKichi.app 2>&1 | grep -q "Signature=adhoc"; then
    echo "⚠ Warning: still ad-hoc signature. This should not happen."
    exit 1
  fi
  echo "✓ Signed with stable identity: TCC permissions will persist across rebuilds"
else
  echo "⚠ Stable signing certificate not found. Using ad-hoc signature."
  echo "⚠ WARNING: Ad-hoc signature changes with every rebuild."
  echo "⚠ This means macOS will forget the 'Input Monitoring' and 'Accessibility'"
  echo "⚠ permissions every time you rebuild. To avoid this:"
  echo ""
  echo "  bash packaging/make_signing_cert.sh"
  echo ""
  echo "⚠ Run the above command once, then rebuild. Permissions will persist thereafter."
fi

echo "==> Build complete: dist/KoeKichi.app"
du -sh dist/KoeKichi.app
