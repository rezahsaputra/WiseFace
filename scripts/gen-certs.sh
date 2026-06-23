#!/usr/bin/env bash
# Generate a self-signed TLS cert for Nginx (dev / internal use).
# For production, replace with a cert from your internal CA.
set -euo pipefail

CERT_DIR="$(dirname "$0")/../nginx/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.crt" \
  -days 825 \
  -subj "/CN=face-compare.internal" \
  -addext "subjectAltName=DNS:face-compare.internal,DNS:localhost,IP:127.0.0.1"

echo "Wrote $CERT_DIR/server.crt and server.key"
