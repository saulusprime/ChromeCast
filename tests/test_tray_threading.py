# This file is part of mkchromecast.

import sys
import unittest
from unittest import mock

try:
    # Importing this pulls in PyQt5, which is optional for everything but the
    # tray itself.  No widget is built here, so no display is needed.
    sys.argv = ["mkchromecast"]
    from mkchromecast import tray_threading
    from mkchromecast.stream_infra import StreamServerError
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PyQt5 is not installed")
class PlayerFailureTests(unittest.TestCase):
    """Covers a failed attempt leaving the tray running.

    A busy port used to arrive here as SystemExit, raised inside a Qt worker
    slot.  PyQt aborts the process on anything that escapes one, so choosing a
    device shut the application down about a second later, and the reason was
    only in the journal.
    """

    def setUp(self):
        self.player = tray_threading.Player()
        self.ready: list[str] = []
        self.finished: list[bool] = []
        self.player.pcastready.connect(self.ready.append)
        self.player.pcastfinished.connect(lambda: self.finished.append(True))

        self.enterContext(mock.patch.object(tray_threading.config, "Config",
                                            autospec=True))
        self.enterContext(mock.patch.object(tray_threading.audio,
                                            "reload_settings", autospec=True))

    def testABusyPortIsReportedInsteadOfRaised(self):
        reason = ("Port 5000 is already in use by another program. Retry with "
                  "--port 5001, or free that port.")
        with mock.patch.object(tray_threading.audio, "main", autospec=True,
                               side_effect=StreamServerError(reason)):
            self.player._play_cast_()

        self.assertEqual(self.ready, [f"_play_cast_ failed: {reason}"])
        self.assertEqual(self.finished, [True])

    def testAServerThatNeverCameUpIsReportedToo(self):
        with mock.patch.object(tray_threading.audio, "main", autospec=True,
                               return_value=False):
            self.player._play_cast_()

        self.assertEqual(len(self.ready), 1)
        self.assertTrue(self.ready[0].startswith("_play_cast_ failed: "))
        self.assertEqual(self.finished, [True])

    def testNothingIsCastAfterAFailure(self):
        with mock.patch.object(tray_threading.audio, "main", autospec=True,
                               return_value=False):
            with mock.patch.object(tray_threading.cast, "Casting",
                                   autospec=True) as casting:
                self.player._play_cast_()

        casting.assert_not_called()
        self.assertIsNone(self.player.cast)


if __name__ == "__main__":
    unittest.main()
