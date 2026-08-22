# This file is part of mkchromecast.

import socket
import unittest
from unittest import mock

from mkchromecast import stream_infra


class PortIsFreeTests(unittest.TestCase):
    def testABoundPortIsNotFree(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen(1)
            port = taken.getsockname()[1]

            self.assertFalse(stream_infra.port_is_free("127.0.0.1", port))

    def testAnUnusedPortIsFree(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        self.assertTrue(stream_infra.port_is_free("127.0.0.1", port))


class PipelineProcessStartTests(unittest.TestCase):
    """Covers what a busy port does to the caller.

    It used to be a SystemExit.  The CLI turned that into exit 1, but the tray
    calls this from a Qt worker slot, and PyQt aborts the process on anything
    that escapes one: the whole application vanished a second after the user
    picked a device.  A plain exception lets each caller decide.
    """

    def make_pipeline(self, port):
        with mock.patch.object(stream_infra.multiprocessing, "Process",
                               autospec=True):
            return stream_infra.PipelineProcess(
                mock.Mock(), "127.0.0.1", port, "Linux")

    def testABusyPortRaisesStreamServerError(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen(1)
            port = taken.getsockname()[1]
            pipeline = self.make_pipeline(port)

            with self.assertRaises(stream_infra.StreamServerError) as caught:
                pipeline.start()

        self.assertNotIsInstance(caught.exception, SystemExit)
        self.assertIn(str(port), str(caught.exception))
        # The message has to carry the way out, since for a tray user it is
        # the whole of what they get to see.
        self.assertIn(f"--port {port + 1}", str(caught.exception))

    def testABusyPortStartsNothing(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen(1)
            pipeline = self.make_pipeline(taken.getsockname()[1])

            with self.assertRaises(stream_infra.StreamServerError):
                pipeline.start()

        pipeline._proc.start.assert_not_called()

    def testAFreePortStartsTheServer(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        pipeline = self.make_pipeline(port)
        pipeline.start()

        pipeline._proc.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
