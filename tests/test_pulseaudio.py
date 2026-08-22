# This file is part of mkchromecast.

import subprocess
import unittest
from unittest import mock

from mkchromecast import pulseaudio


class PactlFailureTests(unittest.TestCase):
    """Covers pactl failing for reasons other than being absent.

    A missing pactl was already reported as PulseAudioNotAvailable; pactl that
    cannot reach the audio server, which is what an ssh login or a systemd
    unit gets, came out as a CalledProcessError traceback instead.
    """

    def run_pactl(self, side_effect):
        with mock.patch.object(subprocess, "run", autospec=True,
                               side_effect=side_effect):
            return pulseaudio._pactl("list", "sinks")

    def testMissingPactlIsReported(self):
        with self.assertRaises(pulseaudio.PulseAudioNotAvailable) as caught:
            self.run_pactl(FileNotFoundError())

        self.assertIn("pactl was not found", str(caught.exception))

    def testUnreachableServerIsReported(self):
        error = subprocess.CalledProcessError(
            1, ["pactl", "list", "sinks"],
            stderr=b"Connection failure: Connection refused\n"
                   b"pa_context_connect() failed: Connection refused\n")

        with self.assertRaises(pulseaudio.PulseAudioNotAvailable) as caught:
            self.run_pactl(error)

        message = str(caught.exception)
        self.assertIn("could not reach the audio server", message)
        self.assertIn("Connection refused", message)

    def testOtherFailuresAreLeftAlone(self):
        # A command that fails for its own reasons is not the audio server
        # being unreachable, and must not be dressed up as one.
        error = subprocess.CalledProcessError(
            1, ["pactl", "unload-module", "42"],
            stderr=b"Failure: No such entity\n")

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_pactl(error)

    def testHangIsReported(self):
        with self.assertRaises(pulseaudio.PulseAudioNotAvailable) as caught:
            self.run_pactl(subprocess.TimeoutExpired(["pactl"], 60))

        self.assertIn("did not answer", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
