# This file is part of mkchromecast.

import subprocess
import unittest
from unittest import mock

from mkchromecast import theme


def gsettings_returning(**answers):
    """Fakes gsettings, answering only for the keys given.

    Args:
        answers: key name -> what gsettings prints, quotes included as it
            really prints them.  A key that is not listed fails, which is what
            a desktop that does not have that setting does.
    """
    def run(command, **kwargs):
        key = command[-1]
        if key in answers:
            return subprocess.CompletedProcess(command, 0, answers[key], "")
        return subprocess.CompletedProcess(command, 1, "", "")

    return run


class LinuxThemeTests(unittest.TestCase):

    def setUp(self):
        # A forced theme would otherwise leak in from the machine running the
        # tests.
        self.enterContext(mock.patch.dict("os.environ", {}, clear=True))

    def patch_run(self, side_effect):
        """Replaces subprocess.run for one assertion, and puts it back."""
        return mock.patch.object(subprocess, "run", autospec=True,
                                 side_effect=side_effect)

    def testColorSchemeIsBelieved(self):
        with self.patch_run(
                gsettings_returning(**{"color-scheme": "'prefer-dark'"})):
            self.assertIs(True, theme.prefers_dark("Linux"))

        with self.patch_run(
                gsettings_returning(**{"color-scheme": "'prefer-light'"})):
            self.assertIs(False, theme.prefers_dark("Linux"))

    def testThemeNameAnswersWhenNoPreferenceIsSet(self):
        # "default" means the user never chose, so the theme name decides.
        with self.patch_run(gsettings_returning(**{
                "color-scheme": "'default'",
                "gtk-theme": "'Yaru-prussiangreen-dark'"})):
            self.assertIs(True, theme.prefers_dark("Linux"))

        with self.patch_run(gsettings_returning(**{
                "color-scheme": "'default'",
                "gtk-theme": "'Yaru-prussiangreen'"})):
            self.assertIs(False, theme.prefers_dark("Linux"))

    def testForcedThemeIsTheLastResort(self):
        with self.patch_run(gsettings_returning()), \
             mock.patch.dict("os.environ", {"GTK_THEME": "Adwaita:dark"}):
            self.assertIs(True, theme.prefers_dark("Linux"))

    def testSilenceIsNotAnAnswer(self):
        # No gsettings, no GTK_THEME: we do not know, and must not guess.
        with self.patch_run(gsettings_returning()):
            self.assertIsNone(theme.prefers_dark("Linux"))

    def testMissingGsettingsIsNotAnError(self):
        with self.patch_run(FileNotFoundError()):
            self.assertIsNone(theme.prefers_dark("Linux"))


class DarwinThemeTests(unittest.TestCase):

    def patch_run(self, returncode, stdout=""):
        self.enterContext(mock.patch.object(
            subprocess, "run", autospec=True,
            return_value=subprocess.CompletedProcess(
                [], returncode, stdout, "")))

    def testDarkAppearance(self):
        self.patch_run(0, "Dark\n")
        self.assertIs(True, theme.prefers_dark("Darwin"))

    def testLightAppearanceLeavesTheKeyUnset(self):
        # `defaults read` exits non-zero when the appearance is light.
        self.patch_run(1)
        self.assertIs(False, theme.prefers_dark("Darwin"))


class IconColorTests(unittest.TestCase):

    def testAnExplicitChoiceIsHonoured(self):
        # No need to ask the desktop, so nothing is run.
        with mock.patch.object(subprocess, "run", autospec=True,
                               side_effect=AssertionError("should not ask")):
            for color in theme.ICON_COLORS:
                self.assertEqual(color, theme.icon_color(color))

    def testAutoFollowsTheDesktop(self):
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=True):
            self.assertEqual("white", theme.icon_color(theme.AUTO_COLOR))

        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=False):
            self.assertEqual("black", theme.icon_color(theme.AUTO_COLOR))

    def testUnknownAndUnansweredFallBackToBlack(self):
        # Black is what the icon was before any of this existed.
        with mock.patch.object(theme, "prefers_dark", autospec=True,
                               return_value=None):
            self.assertEqual("black", theme.icon_color(theme.AUTO_COLOR))
            self.assertEqual("black", theme.icon_color("chartreuse"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
