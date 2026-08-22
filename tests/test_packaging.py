# This file is part of mkchromecast.

import configparser
import os
import struct
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def png_size(path):
    """Returns (width, height) from a PNG's header, without decoding it."""
    with open(path, "rb") as png:
        header = png.read(24)

    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")

    return struct.unpack(">II", header[16:24])


class DesktopEntryTests(unittest.TestCase):
    """Covers the desktop entry naming an icon that actually ships.

    It used to point at /usr/share/pixmaps/mkchromecast.xpm, a file no
    package installs, so the application showed up in the GNOME grid as a
    name with no icon at all.
    """

    def setUp(self):
        self.entry = configparser.ConfigParser(interpolation=None)
        self.entry.optionxform = str  # Keys are case-sensitive here.
        self.entry.read(os.path.join(REPO, "mkchromecast.desktop"))
        self.section = self.entry["Desktop Entry"]

    def testRequiredKeys(self):
        for key in ("Name", "Exec", "Type", "Icon"):
            self.assertIn(key, self.section)

    def testIconIsTypedAsANameNotAPath(self):
        # A bare name is what lets the icon theme find it at any size; a path
        # is only as good as that one file.
        icon = self.section["Icon"]
        self.assertNotIn("/", icon)
        self.assertFalse(os.path.splitext(icon)[1])

    def testTheNamedIconShips(self):
        icon = self.section["Icon"]
        path = os.path.join(REPO, "images", f"{icon}.png")

        self.assertTrue(os.path.exists(path),
                        f"{path} is missing; the grid would show no icon")

        width, height = png_size(path)
        # Icon themes expect square artwork, and the source images are not.
        self.assertEqual(width, height, f"{path} is {width}x{height}")
        self.assertGreaterEqual(width, 256)

    def testTheIconIsInstalledWhereTheThemeLooks(self):
        with open(os.path.join(REPO, "setup.py"), encoding="utf-8") as setup:
            contents = setup.read()

        icon = self.section["Icon"]
        self.assertIn("share/icons/hicolor", contents)
        self.assertIn(f"images/{icon}.png", contents)

        with open(os.path.join(REPO, "packaging", "build-deb.sh"),
                  encoding="utf-8") as script:
            deb = script.read()

        self.assertIn("share/icons/hicolor", deb)
        self.assertIn(f"images/{icon}.png", deb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
