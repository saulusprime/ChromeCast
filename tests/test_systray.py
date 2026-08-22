# This file is part of mkchromecast.

import sys
import unittest
from unittest import mock

try:
    # Importing systray pulls in PyQt5, which is optional for everything but
    # the tray itself.  No widget is built here, so no display is needed.
    sys.argv = ["mkchromecast"]
    from mkchromecast import systray
    from mkchromecast import theme
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PyQt5 is not installed")
class TrayIconColorTests(unittest.TestCase):
    """Covers picking the icon variant, without building any widget.

    The artwork is black on transparent, so on a dark panel the icon was very
    nearly invisible until someone found the setting.
    """

    def setUp(self):
        # Building a real QIcon needs a QGuiApplication, and this is about
        # which file gets chosen rather than about Qt.
        self.qicon = self.enterContext(
            mock.patch.object(systray.QtGui, "QIcon", autospec=True))

    def chosen_icon_file(self):
        """The path handed to QIcon by the last call."""
        return self.qicon.call_args.args[0]

    def make_tray(self, configured):
        """A stand-in carrying only what the methods under test touch."""
        tray = mock.Mock(spec=["setIcon"])

        stub = mock.Mock(spec=systray.menubar)
        stub.config = mock.Mock(colors=configured)
        stub.tray = tray
        stub.google = {"black": "google", "blue": "google_b",
                       "white": "google_w"}
        stub.google_working = {"black": "google_working",
                               "blue": "google_working_b",
                               "white": "google_working_w"}

        # These call each other, and a Mock would answer with another Mock,
        # so both have to reach the real methods.
        stub._icon_color = lambda: systray.menubar._icon_color(stub)
        stub._set_generic_icon = (
            lambda icon_set: systray.menubar._set_generic_icon(stub, icon_set))
        return stub

    def icon_color(self, stub):
        return systray.menubar._icon_color(stub)

    def set_icon(self, stub, icon_set):
        systray.menubar._set_generic_icon(stub, icon_set)

    def testDarkDesktopGetsTheWhiteIcon(self):
        stub = self.make_tray(theme.AUTO_COLOR)
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            self.assertEqual("white", self.icon_color(stub))

    def testLightDesktopGetsTheBlackIcon(self):
        stub = self.make_tray(theme.AUTO_COLOR)
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=False):
            self.assertEqual("black", self.icon_color(stub))

    def testAnExplicitSettingStillWins(self):
        stub = self.make_tray("blue")
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            self.assertEqual("blue", self.icon_color(stub))

    def testSettingAnIconRemembersWhatIsShown(self):
        stub = self.make_tray(theme.AUTO_COLOR)
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            self.set_icon(stub, stub.google_working)

        self.assertEqual(stub.google_working, stub._icon_set)
        self.assertEqual("white", stub._icon_color_shown)
        stub.tray.setIcon.assert_called_once()
        self.assertTrue(
            self.chosen_icon_file().endswith("google_working_w.png"),
            self.chosen_icon_file())

    def testTheIconFollowsTheDesktopSwitchingToDark(self):
        stub = self.make_tray(theme.AUTO_COLOR)
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=False):
            self.set_icon(stub, stub.google)
        stub.tray.setIcon.reset_mock()

        # The user turns the desktop dark while the tray is running.
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            systray.menubar._follow_desktop_theme(stub)

        self.assertEqual("white", stub._icon_color_shown)
        # Still the state it was showing, in the other colour.
        self.assertEqual(stub.google, stub._icon_set)
        stub.tray.setIcon.assert_called_once()
        self.assertTrue(self.chosen_icon_file().endswith("google_w.png"),
                        self.chosen_icon_file())

    def testAnUnchangedThemeRedrawsNothing(self):
        stub = self.make_tray(theme.AUTO_COLOR)
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            self.set_icon(stub, stub.google)
            stub.tray.setIcon.reset_mock()

            systray.menubar._follow_desktop_theme(stub)

        stub.tray.setIcon.assert_not_called()

    def testEveryStateHasAWhiteVariant(self):
        # A missing key would raise at the moment the tray changes state.
        for icon_set in ("google", "google_working", "google_nodev"):
            for color in theme.ICON_COLORS:
                self.assertTrue(
                    systray.icon_path(
                        f"{icon_set}_{color[0]}" if color != "black"
                        else icon_set).endswith(".png"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
