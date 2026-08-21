# This file is part of mkchromecast.

import unittest
from unittest import mock

from mkchromecast import node
from mkchromecast.constants import OpMode


class NodeReconnectTests(unittest.TestCase):
    """Covers restarting the node server after it dies.

    That path used to restart node by spawning a fresh copy of this very
    process, so every restart nested one process inside the previous one; it
    was left raising `Internal error: Never worked` rather than risk the chain
    running away.  Restarting happens in place now, a bounded number of times.
    """

    def setUp(self):
        self.enterContext(mock.patch.object(node.time, "sleep", autospec=True))
        self.enterContext(
            mock.patch.object(node.shutil, "which", autospec=True,
                              return_value="/usr/bin/node"))
        self.enterContext(mock.patch.object(node.pickle, "load",
                                            autospec=True, return_value="4242"))
        self.enterContext(mock.patch("builtins.open", mock.mock_open()))

        self.popen = self.enterContext(
            mock.patch.object(node.subprocess, "Popen", autospec=True))
        self.watch = self.enterContext(
            mock.patch.object(node, "watch_until_exit", autospec=True))
        self.recasting = self.enterContext(
            mock.patch.object(node, "recasting", autospec=True))

        self.mkcc = mock.Mock()
        self.mkcc.backend = "node"
        self.mkcc.codec = "mp3"
        self.mkcc.bitrate = 192
        self.mkcc.samplerate = 44100
        self.mkcc.youtube_url = None
        self.mkcc.notifications = False
        self.mkcc.debug = False
        self.mkcc.port = 5000
        self.mkcc.platform = "Linux"
        self.mkcc.operation = OpMode.AUDIOCAST

    def testServerIsRestartedABoundedNumberOfTimes(self):
        # Node comes up every time and then exits: watch_until_exit returning
        # is what "the server died" looks like from here.
        self.popen.return_value.poll.return_value = None

        node.streaming(self.mkcc)

        self.assertEqual(node.NODE_RECONNECT_ATTEMPTS + 1,
                         self.popen.call_count)
        self.assertEqual(node.NODE_RECONNECT_ATTEMPTS,
                         self.recasting.call_count)

    def testServerThatNeverComesUpIsNotRecastTo(self):
        # poll() returning an exit status means node died on startup, so
        # pointing the device at it would only produce silence.
        self.popen.return_value.poll.return_value = 1

        node.streaming(self.mkcc)

        self.assertEqual(node.NODE_RECONNECT_ATTEMPTS + 1,
                         self.popen.call_count)
        self.recasting.assert_not_called()

    def testABudgetSpentOnAHealthyServerIsGivenBack(self):
        # A server that ran for a while and then died is a fresh failure, not a
        # continuation of the previous one, so the attempts start over.  Here
        # two runs last long enough to count as healthy and three do not:
        # 2 healthy + 3 failing = 5 starts before we give up.
        self.popen.return_value.poll.return_value = None
        healthy = [0.0, node.NODE_HEALTHY_UPTIME_SECONDS + 1]
        failing = [0.0, 0.0]
        self.enterContext(mock.patch.object(
            node.time, "monotonic", autospec=True,
            side_effect=healthy * 2 + failing * 3))

        node.streaming(self.mkcc)

        self.assertEqual(5, self.popen.call_count)

    def testMissingNodeIsNotRestarted(self):
        node.shutil.which.return_value = None

        node.streaming(self.mkcc)

        self.popen.assert_not_called()

    def testPortComesFromSettings(self):
        self.mkcc.port = 5001
        self.popen.return_value.poll.return_value = None

        node.streaming(self.mkcc)

        command = self.popen.call_args_list[0].args[0]
        self.assertIn("-p", command)
        self.assertEqual("5001", command[command.index("-p") + 1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
