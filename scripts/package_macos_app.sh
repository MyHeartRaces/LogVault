#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
BINARY="${2:-dist/LogVault}"
RELEASE_DIR="${3:-release}"
APP_DIR="$ROOT/build/macos-app/LogVault.app"
DMG_ROOT="$ROOT/build/macos-dmg"

if [[ ! -f "$BINARY" ]]; then
  echo "Binary not found: $BINARY" >&2
  exit 1
fi

rm -rf "$ROOT/build/macos-app" "$DMG_ROOT"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$ROOT/$RELEASE_DIR"
rm -f "$ROOT/$RELEASE_DIR/LogVault-macos-arm64.app.zip" "$ROOT/$RELEASE_DIR/LogVault-macos-arm64.dmg"
install -m 755 "$BINARY" "$APP_DIR/Contents/MacOS/LogVault"
install -m 644 "$ROOT/assets/logvault.svg" "$APP_DIR/Contents/Resources/logvault.svg"
install -m 644 "$ROOT/assets/logvault.icns" "$APP_DIR/Contents/Resources/logvault.icns"

cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>LogVault</string>
  <key>CFBundleIdentifier</key>
  <string>com.logvault.app</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>LogVault</string>
  <key>CFBundleDisplayName</key>
  <string>LogVault</string>
  <key>CFBundleIconFile</key>
  <string>logvault.icns</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$VERSION</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF

echo "APPL????" > "$APP_DIR/Contents/PkgInfo"

codesign --force --deep --options runtime --sign - "$APP_DIR"
codesign --verify --deep --strict --verbose=2 "$APP_DIR"

mkdir -p "$DMG_ROOT"
COPYFILE_DISABLE=1 cp -R "$APP_DIR" "$DMG_ROOT/LogVault.app"
ln -s /Applications "$DMG_ROOT/Applications"
hdiutil create -volname LogVault -srcfolder "$DMG_ROOT" -ov -format UDZO "$ROOT/$RELEASE_DIR/LogVault-macos-arm64.dmg"
codesign --force --sign - "$ROOT/$RELEASE_DIR/LogVault-macos-arm64.dmg"
codesign --verify --verbose=2 "$ROOT/$RELEASE_DIR/LogVault-macos-arm64.dmg"

echo "Built: $ROOT/$RELEASE_DIR/LogVault-macos-arm64.dmg"
