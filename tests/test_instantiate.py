# this file is part of mkchromecast.

import unittest
from unittest import mock

import mkchromecast
from mkchromecast import _arg_parsing
from mkchromecast import config
from mkchromecast import constants

class BasicInstantiationTest(unittest.TestCase):
    def testInstantiate(self):
        # TODO(xsdg): Do a better job of mocking the args parser.

        mock_args = mock.Mock()
        # Here we set the minimal required args for __init__ to not sys.exit.
        mock_args.encoder_backend = None
        mock_args.bitrate = constants.DEFAULT_BITRATE
        mock_args.codec = 'mp3'
        mock_args.command = None
        mock_args.resolution = None
        mock_args.chunk_size = 64
        mock_args.sample_rate = 44100
        mock_args.youtube = None
        mock_args.input_file = None
        mkcc = mkchromecast.Mkchromecast(mock_args)

    def testMP3CodecNodeBackend(self):
        """This test evaluates the assignment of the MP3 codec when the Node Backend is selected"""

        mock_args = mock.Mock()
        # Here we set the minimal required args for __init__ to not sys.exit.
        mock_args.encoder_backend = 'node'
        mock_args.bitrate = constants.DEFAULT_BITRATE
        mock_args.codec = 'mp3'
        mock_args.command = None
        mock_args.resolution = None
        mock_args.chunk_size = 64
        mock_args.sample_rate = 44100
        mock_args.youtube = None
        mock_args.input_file = None
        mkcc = mkchromecast.Mkchromecast(mock_args)

    def testTrayModeInstantiation(self):
        mock_config = mock.create_autospec(config.Config, spec_set=True)
        self.enterContext(mock.patch.object(config, "Config", return_value=mock_config))

        mock_args = mock.Mock()
        # Here we set the minimal required args for __init__ to not sys.exit.
        mock_args.encoder_backend = None
        mock_args.bitrate = constants.DEFAULT_BITRATE
        mock_args.codec = 'mp3'
        mock_args.command = None
        mock_args.resolution = None
        mock_args.chunk_size = 64
        mock_args.sample_rate = 44100
        mock_args.youtube = None
        mock_args.input_file = None

        # Now, we set the args to trigger tray mode.
        mock_args.discover = False
        mock_args.input_file = None
        mock_args.reset = False
        mock_args.screencast = False
        mock_args.source_url = None
        mock_args.tray = True

        # Setting the mock config contents.
        # Must be a real backend: it is validated against the platform.
        mock_config.backend = "ffmpeg"
        mock_config.codec = "codec"
        mock_config.bitrate = 12345
        mock_config.samplerate = 54321
        mock_config.notifications = True
        mock_config.colors = "colors"
        mock_config.search_at_launch = False
        mock_config.alsa_device = "alsa_device"

        mkcc = mkchromecast.Mkchromecast(mock_args)

        # We should find that the mock config values are returned by mkcc, even
        # when they are defined differently in args (for instance, bitrate,
        # codec, and samplerate above)
        self.assertEqual(mkcc.backend, "ffmpeg")
        self.assertEqual(mkcc.codec, "codec")
        self.assertEqual(mkcc.bitrate, 12345)
        self.assertEqual(mkcc.samplerate, 54321)
        self.assertEqual(mkcc.notifications, True)
        self.assertEqual(mkcc.colors, "colors")
        self.assertEqual(mkcc.search_at_launch, False)
        self.assertEqual(mkcc.adevice, "alsa_device")

    def testTrayModeRejectsUnsupportedBackend(self):
        """A backend from the config file that this platform cannot use.

        --encoder-backend is validated, but the config file was not, so a
        stale or hand-edited value used to be taken at face value.
        """
        mock_config = mock.create_autospec(config.Config, spec_set=True)
        self.enterContext(mock.patch.object(config, "Config", return_value=mock_config))

        mock_args = mock.Mock()
        mock_args.encoder_backend = None
        mock_args.bitrate = constants.DEFAULT_BITRATE
        mock_args.codec = 'mp3'
        mock_args.command = None
        mock_args.resolution = None
        mock_args.chunk_size = 64
        mock_args.sample_rate = 44100
        mock_args.youtube = None
        mock_args.input_file = None
        mock_args.discover = False
        mock_args.reset = False
        mock_args.screencast = False
        mock_args.source_url = None
        mock_args.tray = True
        mock_args.video = False

        mock_config.backend = "not-a-real-backend"
        mock_config.codec = "mp3"
        mock_config.bitrate = 192
        mock_config.samplerate = 44100
        mock_config.notifications = False
        mock_config.colors = "black"
        mock_config.search_at_launch = False
        mock_config.alsa_device = None

        mkcc = mkchromecast.Mkchromecast(mock_args)

        supported = constants.backend_options_for_platform(
            mkcc.platform, mock_args.video)
        self.assertIn(mkcc.backend, supported)


class SharedInstanceTest(unittest.TestCase):
    """Four modules build a Mkchromecast at import time.

    Without sharing, that meant parsing the command line and loading the
    config file once per module.
    """

    def setUp(self):
        args = mock.Mock()
        args.debug = False
        args.encoder_backend = None
        args.bitrate = constants.DEFAULT_BITRATE
        args.codec = "mp3"
        args.command = None
        args.mtype = None
        args.resolution = None
        args.chunk_size = 64
        args.sample_rate = 44100
        # Everything that selects an operating mode.
        args.discover = False
        args.input_file = None
        args.reset = False
        args.screencast = False
        args.source_url = None
        args.tray = False
        args.version = False
        args.youtube = None
        args.video = False
        self.args = args

        self.enterContext(mock.patch.object(
            _arg_parsing.Parser, "parse_args", return_value=args))
        self._reset_shared_state()
        self.addCleanup(self._reset_shared_state)

    def _reset_shared_state(self):
        mkchromecast.Mkchromecast.discard_shared_instance()
        mkchromecast.Mkchromecast._parsed_args = None

    def testSharedInstanceIsReused(self):
        self.assertIs(mkchromecast.Mkchromecast(),
                      mkchromecast.Mkchromecast())

    def testCommandLineIsParsedOnce(self):
        for _ in range(4):
            mkchromecast.Mkchromecast()

        _arg_parsing.Parser.parse_args.assert_called_once()

    def testExplicitArgsBuildASeparateObject(self):
        shared = mkchromecast.Mkchromecast()
        standalone = mkchromecast.Mkchromecast(self.args)

        self.assertIsNot(shared, standalone)
        # ...and leave the shared one alone.
        self.assertIs(shared, mkchromecast.Mkchromecast())

    def testDiscardingRebuilds(self):
        first = mkchromecast.Mkchromecast()
        mkchromecast.Mkchromecast.discard_shared_instance()

        self.assertIsNot(first, mkchromecast.Mkchromecast())


if __name__ == "__main__":
    unittest.main(verbosity=2)
