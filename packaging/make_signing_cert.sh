#!/usr/bin/env bash
# Create a stable self-signed code-signing certificate in the login keychain
# (SPEC §18.1).
#
# This script is run once to create a certificate named "KoeKichi Self-Signed".
# Subsequent builds can reuse this certificate, preserving TCC permissions
# across rebuilds.
#
# Usage: bash packaging/make_signing_cert.sh
#
# The script will prompt for the login keychain password once if creating a
# new certificate (macOS security requirement for importing into the keychain).

set -euo pipefail

CERT_NAME="KoeKichi Self-Signed"
KEYCHAIN="${HOME}/Library/Keychains/login.keychain-db"

echo "==> Checking for existing code-signing certificate: $CERT_NAME"

if security find-certificate -c "$CERT_NAME" >/dev/null 2>&1; then
  echo "✓ Certificate already exists. Nothing to do."
  exit 0
fi

echo "==> Certificate not found. Creating new self-signed certificate..."
echo "    (You will be prompted for your login keychain password once)"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

CERT_KEY="$TMPDIR/cert.key"
CERT_CRT="$TMPDIR/cert.crt"
CERT_P12="$TMPDIR/cert.p12"

# Generate a private key and self-signed certificate with code signing extensions
# CN = certificate name, X.509 extensions: extendedKeyUsage=codeSigning, keyUsage=digitalSignature
openssl req -new -x509 -days 36500 -nodes \
  -out "$CERT_CRT" -keyout "$CERT_KEY" \
  -subj "/CN=$CERT_NAME" \
  -addext "extendedKeyUsage=codeSigning" \
  -addext "keyUsage=digitalSignature"

# Convert to PKCS#12 (.p12) format for keychain import (empty password)
openssl pkcs12 -export -in "$CERT_CRT" -inkey "$CERT_KEY" \
  -out "$CERT_P12" -name "$CERT_NAME" -passout pass:

# Import into login keychain (prompts for keychain password)
security import "$CERT_P12" -k "$KEYCHAIN" -T /usr/bin/codesign

# Verify the certificate is now available for code signing
echo "==> Verifying certificate was imported successfully..."
if security find-identity -v -p codesigning 2>/dev/null | grep -q "$CERT_NAME"; then
  echo "✓ Certificate '$CERT_NAME' is now available for code signing."
  exit 0
else
  echo "✗ Failed to verify certificate import." >&2
  exit 1
fi
