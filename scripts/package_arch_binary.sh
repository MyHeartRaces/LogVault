#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
BINARY="${2:-dist/LogVault}"
RELEASE_DIR="${3:-release}"
PKGNAME="logvault-bin"
PKGREL="1"
ARCH="x86_64"
PKGROOT="$ROOT/build/arch-binary/pkg"
PKGFILE="$ROOT/$RELEASE_DIR/${PKGNAME}-${VERSION}-${PKGREL}-${ARCH}.pkg.tar.zst"

if [[ ! -f "$BINARY" ]]; then
  echo "Binary not found: $BINARY" >&2
  exit 1
fi

rm -rf "$PKGROOT"
mkdir -p \
  "$PKGROOT/usr/bin" \
  "$PKGROOT/usr/share/applications" \
  "$PKGROOT/usr/share/icons/hicolor/scalable/apps" \
  "$PKGROOT/usr/share/licenses/$PKGNAME" \
  "$ROOT/$RELEASE_DIR"

install -m 755 "$BINARY" "$PKGROOT/usr/bin/LogVault"
install -m 644 "$ROOT/assets/logvault.svg" "$PKGROOT/usr/share/icons/hicolor/scalable/apps/logvault.svg"
install -m 644 "$ROOT/LICENSE" "$PKGROOT/usr/share/licenses/$PKGNAME/LICENSE"

cat > "$PKGROOT/usr/share/applications/logvault.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=LogVault
Comment=Download Warcraft Logs reports
Exec=LogVault
Icon=logvault
Terminal=false
Categories=Game;Utility;
StartupNotify=true
EOF

SIZE="$(du -sb "$PKGROOT/usr" | awk '{print $1}')"
BUILDDATE="$(date +%s)"
cat > "$PKGROOT/.PKGINFO" <<EOF
pkgname = $PKGNAME
pkgbase = $PKGNAME
xdata = pkgtype=pkg
pkgver = $VERSION-$PKGREL
pkgdesc = GUI downloader/exporter for Warcraft Logs reports
url = https://github.com/MyHeartRaces/LogVault
builddate = $BUILDDATE
packager = LogVault GitHub Actions
size = $SIZE
arch = $ARCH
license = MIT
depend = glibc
EOF

tar --sort=name --owner=0 --group=0 --numeric-owner -C "$PKGROOT" -I 'zstd -19 -T0' -cf "$PKGFILE" .PKGINFO usr
echo "Built: $PKGFILE"
