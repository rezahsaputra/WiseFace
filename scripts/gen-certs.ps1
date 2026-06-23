# Generate a self-signed TLS cert for Nginx on Windows (dev / internal use).
# Requires OpenSSL on PATH (ships with Git for Windows: /usr/bin/openssl).
$ErrorActionPreference = "Stop"
$certDir = Join-Path $PSScriptRoot "..\nginx\certs"
New-Item -ItemType Directory -Force -Path $certDir | Out-Null

openssl req -x509 -nodes -newkey rsa:2048 `
  -keyout "$certDir\server.key" `
  -out "$certDir\server.crt" `
  -days 825 `
  -subj "/CN=face-compare.internal" `
  -addext "subjectAltName=DNS:face-compare.internal,DNS:localhost,IP:127.0.0.1"

Write-Host "Wrote $certDir\server.crt and server.key"
