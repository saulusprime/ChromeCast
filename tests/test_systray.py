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


@unittest.skipUnless(HAS_QT, "PyQt5 is not installed")
class FailureReasonTests(unittest.TestCase):
    """Covers the tray repeating why an attempt failed.

    "Try Again..." is bad advice when the answer is that another program holds
    the port, and under a .desktop launcher the explanation we print goes to
    the journal, where nobody looks.
    """

    def make_tray(self):
        stub = mock.Mock(spec=systray.menubar)
        stub.pcastfailure = systray._DEFAULT_FAILURE
        # Reading back the device we cast to is not what these are about, and
        # it depends on a file left in /tmp by any earlier run.
        stub._player = mock.Mock(cast=None)
        self.enterContext(mock.patch.object(systray.os.path, "exists",
                                            autospec=True, return_value=False))
        return stub

    def testTheReasonIsKeptForTheNotification(self):
        stub = self.make_tray()
        reason = "Port 5000 is already in use by another program."

        systray.menubar.pcastready(stub, f"_play_cast_ failed: {reason}")

        self.assertEqual(stub.pcastfailure, reason)
        self.assertTrue(stub.pcastfailed)

    def testAFailureWithoutAReasonKeepsTheGenericMessage(self):
        stub = self.make_tray()

        systray.menubar.pcastready(stub, "_play_cast_ failed")

        self.assertEqual(stub.pcastfailure, systray._DEFAULT_FAILURE)

    def testSuccessForgetsThePreviousReason(self):
        stub = self.make_tray()
        stub.pcastfailure = "Port 5000 is already in use by another program."

        systray.menubar.pcastready(stub, "_play_cast_ success")

        self.assertEqual(stub.pcastfailure, systray._DEFAULT_FAILURE)
        self.assertFalse(stub.pcastfailed)


@unittest.skipUnless(HAS_QT, "PyQt5 is not installed")
class SliderValueTests(unittest.TestCase):
    """Covers the value handed to the volume slider.

    Qt sliders take ints.  `round(x, 1)` returns a float even when the result
    is whole, so opening the volume control raised
    `TypeError: setValue(self, a0: int): argument 1 has unexpected type
    'float'` as soon as it ran against a real device.
    """

    def testTheValueIsAlwaysAnInt(self):
        for level in (0.0, 0.01, 0.5, 0.65, 0.999, 1.0):
            with self.subTest(level=level):
                value = systray.slider_value(level, 100)

                self.assertIsInstance(value, int)
                self.assertNotIsInstance(value, float)

    def testTheEndsOfTheRangeMap(self):
        self.assertEqual(systray.slider_value(0.0, 100), 0)
        self.assertEqual(systray.slider_value(1.0, 100), 100)

    def testTheValueIsRoundedToTheNearest(self):
        self.assertEqual(systray.slider_value(0.654, 100), 65)
        self.assertEqual(systray.slider_value(0.656, 100), 66)


@unittest.skipUnless(HAS_QT, "PyQt5 is not installed")
class StopAndExitTests(unittest.TestCase):
    """Covers tearing a cast down, and leaving.

    stop_cast() called read_config(), a method the config refactor deleted
    while leaving this one caller behind.  Both the Stop entry and Quit went
    through here, so both raised AttributeError halfway: the cast was never
    torn down, and Quit never reached app.quit().
    """

    def setUp(self):
        self.enterContext(mock.patch.object(systray, "checkmktmp",
                                            autospec=True))
        self.enterContext(mock.patch.object(systray, "del_tmp", autospec=True))
        # Would put a real notification on the desktop of whoever runs this.
        self.enterContext(mock.patch.object(systray, "linux_notify",
                                            autospec=True))

    def make_tray(self):
        stub = mock.Mock(spec=systray.menubar)
        stub.cast = mock.Mock()
        stub.stopped = False
        stub.pcastfailed = False
        stub.exiting = False
        stub.config = mock.Mock(notifications=False)
        # Assigned in __init__, so it is not part of the class spec.
        stub.app = mock.Mock()
        return stub

    def testStoppingRereadsTheConfig(self):
        stub = self.make_tray()

        systray.menubar.stop_cast(stub)

        stub.config.load_and_validate.assert_called_once_with()

    def testStoppingFromTheMenuLooksForDevicesAgain(self):
        stub = self.make_tray()

        systray.menubar.stop_cast(stub)

        stub.search_cast.assert_called_once_with()

    def testQuittingDoesNotStartASearch(self):
        """The search the user saw start when they asked to leave."""
        stub = self.make_tray()
        stub.exiting = True

        systray.menubar.stop_cast(stub)

        stub.search_cast.assert_not_called()

    def testQuittingReachesTheEnd(self):
        stub = self.make_tray()
        stub.stopped = True

        systray.menubar.exit_all(stub)

        stub.stop_cast.assert_called_once_with()
        stub.app.quit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
