#!/bin/sh
# This file is part of mkchromecast.
#
# Builds a .deb from the working tree.
#
# It uses dpkg-deb directly rather than debhelper, so it needs nothing beyond
# dpkg-dev, which every Debian or Ubuntu system already has.  The layout it
# produces is the one the distribution package uses: the package under
# /usr/lib/python3/dist-packages, the entry point in /usr/bin, and the icons
# under /usr/share/mkchromecast/images, which is where systray.icon_path looks
# for them on an installed copy.
#
# The dependencies are the distribution's own python3-* packages, not the
# contents of requirements.txt: this package is meant to be installed with apt,
# alongside the system Python.
#
# Usage:
#     packaging/build-deb.sh [output-directory]
#
# Environment:
#     DEB_REVISION   Debian revision, default "1local1".  The default sorts
#                    above the Ubuntu package (0.3.9~git20200902+...), so apt
#                    treats this build as an upgrade rather than refusing it.

set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUTDIR="${1:-$REPO/dist}"
REVISION="${DEB_REVISION:-1local1}"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$REPO/mkchromecast/version.py")"
if [ -z "$VERSION" ]; then
    echo "Cannot read the version from mkchromecast/version.py" >&2
    exit 1
fi

FULL_VERSION="$VERSION-$REVISION"
STAGE="$REPO/build/deb"
PKGDIR="$STAGE/mkchromecast_${FULL_VERSION}_all"

rm -rf "$PKGDIR"
mkdir -p "$PKGDIR/DEBIAN" \
         "$PKGDIR/usr/bin" \
         "$PKGDIR/usr/lib/python3/dist-packages" \
         "$PKGDIR/usr/share/applications" \
         "$PKGDIR/usr/share/icons/hicolor/256x256/apps" \
         "$PKGDIR/usr/share/man/man1" \
         "$PKGDIR/usr/share/mkchromecast/images" \
         "$PKGDIR/usr/share/mkchromecast/nodejs" \
         "$PKGDIR/usr/share/doc/mkchromecast"

# The Python package, without the caches of whoever built it.  getch/ is part
# of it: bin/mkchromecast imports it for --control.
cp -r "$REPO/mkchromecast" "$PKGDIR/usr/lib/python3/dist-packages/"
PKGSRC="$PKGDIR/usr/lib/python3/dist-packages/mkchromecast"
find "$PKGSRC" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$PKGSRC" -name '*.pyc' -delete

# The entry point.  Policy wants the interpreter named outright, not looked up
# through env.
sed '1s|^#!/usr/bin/env python3$|#!/usr/bin/python3|' \
    "$REPO/bin/mkchromecast" > "$PKGDIR/usr/bin/mkchromecast"
chmod 755 "$PKGDIR/usr/bin/mkchromecast"

# Data files.  Only the tray icons: images/ also holds the README screenshots.
cp "$REPO"/images/google*.png "$PKGDIR/usr/share/mkchromecast/images/"
cp "$REPO"/nodejs/package.json \
   "$REPO"/nodejs/package-lock.json \
   "$REPO"/nodejs/html5-video-streamer.js \
   "$PKGDIR/usr/share/mkchromecast/nodejs/"
cp "$REPO/mkchromecast.desktop" "$PKGDIR/usr/share/applications/"

# The desktop entry names its icon "mkchromecast"; this is where the icon
# theme looks for it.  Installing here also fires the hicolor-icon-theme
# trigger, which refreshes the icon cache.
cp "$REPO/images/mkchromecast.png" \
   "$PKGDIR/usr/share/icons/hicolor/256x256/apps/"
gzip -9nc "$REPO/mkchromecast.1" > "$PKGDIR/usr/share/man/man1/mkchromecast.1.gz"
cp "$REPO/LICENSE" "$PKGDIR/usr/share/doc/mkchromecast/copyright"
gzip -9nc "$REPO/changelog.md" > "$PKGDIR/usr/share/doc/mkchromecast/changelog.gz"

# Whatever the umask of the machine that built this, the package carries the
# modes policy asks for.
find "$PKGDIR" -type d -exec chmod 755 {} +
find "$PKGDIR" -type f -exec chmod 644 {} +
chmod 755 "$PKGDIR/usr/bin/mkchromecast"

INSTALLED_SIZE="$(du -ks "$PKGDIR" | cut -f1)"

cat > "$PKGDIR/DEBIAN/control" <<EOF
Package: mkchromecast
Version: $FULL_VERSION
Section: sound
Priority: optional
Architecture: all
Maintainer: Muammar El Khatib <http://muammar.me/>
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.9),
 python3-pychromecast (>= 14),
 python3-flask,
 python3-psutil,
 python3-requests,
 python3-ifaddr,
 python3-pyqt5,
 pulseaudio-utils
Recommends: ffmpeg, lame, vorbis-tools, opus-tools, flac, sox
Suggests: python3-gi, pavucontrol
Homepage: http://mkchromecast.com/
Description: Cast Linux audio or video to Google Cast devices
 Mkchromecast streams what the computer is playing, or a video file, to
 Google Cast devices. Audio is captured with parec and encoded on the fly;
 mp3, ogg, opus, flac and wav are supported, with ffmpeg as an alternative
 encoder backend. A system tray menu is included.
 .
 Sonos casting is not available: that code is present but disconnected.
 .
 This package was built from the working tree with packaging/build-deb.sh,
 so it is not the distribution's own build.
EOF

cat > "$PKGDIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = "configure" ] && command -v py3compile >/dev/null 2>&1; then
    py3compile -p mkchromecast /usr/lib/python3/dist-packages/mkchromecast
fi

exit 0
EOF

cat > "$PKGDIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e

if command -v py3clean >/dev/null 2>&1; then
    py3clean -p mkchromecast || true
fi

exit 0
EOF

chmod 755 "$PKGDIR/DEBIAN/postinst" "$PKGDIR/DEBIAN/prerm"

# md5sums, as a well-formed package carries: paths relative to /, control
# files excluded.
( cd "$PKGDIR" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
  | sort -z | xargs -0 md5sum > DEBIAN/md5sums )

mkdir -p "$OUTDIR"
dpkg-deb --root-owner-group --build "$PKGDIR" "$OUTDIR" >/dev/null

echo "Built $OUTDIR/mkchromecast_${FULL_VERSION}_all.deb"
