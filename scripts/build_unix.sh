#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${SSL_CERT_FILE:-}" ]]; then
  for candidate in \
    /etc/ssl/cert.pem \
    /etc/ssl/certs/ca-certificates.crt \
    /opt/homebrew/etc/ca-certificates/cert.pem \
    /opt/homebrew/etc/openssl@3/cert.pem \
    /usr/local/etc/openssl@3/cert.pem \
    /usr/local/etc/openssl/cert.pem; do
    if [[ -f "$candidate" ]]; then
      export SSL_CERT_FILE="$candidate"
      break
    fi
  done
fi

python3 -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate

python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm LogVault.spec

echo "Built: $ROOT/dist/LogVault"
