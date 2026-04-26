#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINARY="${1:-$ROOT/dist/LogVault}"

if [[ ! -f "$BINARY" ]]; then
  echo "Binary not found: $BINARY" >&2
  echo "Build it first with ./scripts/build_unix.sh or pass a downloaded binary path." >&2
  exit 1
fi

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"
install -m 755 "$BINARY" "$BIN_DIR/LogVault"

if [[ -f "$ROOT/assets/logvault.svg" ]]; then
  install -m 644 "$ROOT/assets/logvault.svg" "$ICON_DIR/logvault.svg"
elif [[ -f "$SCRIPT_DIR/logvault.svg" ]]; then
  install -m 644 "$SCRIPT_DIR/logvault.svg" "$ICON_DIR/logvault.svg"
else
  cat > "$ICON_DIR/logvault.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="24" fill="#171717"/>
  <path d="M28 28h72v72H28z" fill="#2b2b2b"/>
  <path d="M40 40h48v10H40zm0 20h48v10H40zm0 20h28v10H40z" fill="#f0c05a"/>
  <path d="M92 80l12 12-12 12-12-12z" fill="#6bb6ff"/>
  <path d="M28 28h72v72H28z" fill="none" stroke="#f0c05a" stroke-width="6"/>
</svg>
EOF
fi

cat > "$APP_DIR/logvault.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=LogVault
Comment=Download Warcraft Logs reports
Exec=$BIN_DIR/LogVault
Icon=logvault
Terminal=false
Categories=Game;Utility;
StartupNotify=true
EOF

chmod 644 "$APP_DIR/logvault.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed LogVault binary: $BIN_DIR/LogVault"
echo "Installed desktop entry: $APP_DIR/logvault.desktop"
echo "If your desktop menu does not update immediately, log out and back in."
