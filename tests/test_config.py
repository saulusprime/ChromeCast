# this file is part of mkchromecast.

import configparser
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from mkchromecast import config
from mkchromecast import constants

class ClampBitrateTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(os, "environ", autospec=True))
        self.enterContext(mock.patch.object(configparser, "ConfigParser", autospec=True))
        self.enterContext(mock.patch("builtins.open", autospec=True))

    def testInstantiateNewConfig(self):
        mock_parser = configparser.ConfigParser()
        config_path = pathlib.PurePath("/fake_dir/fake_path.txt")
        conf = config.Config(platform="Linux", config_path=config_path)
        with conf:
            mock_parser.read.assert_called_once_with(config_path)

        mock_parser.write.assert_called_once()

    def testInstantiateNewReadOnlyConfig(self):
        mock_parser = configparser.ConfigParser()
        config_path = pathlib.PurePath("/fake_dir/fake_path.txt")
        conf = config.Config(
            platform="Darwin", config_path=config_path, read_only=True)
        with conf:
            mock_parser.read.assert_called_once_with(config_path)

        mock_parser.write.assert_not_called()

    def testPropertyGetters(self):
        config_path = pathlib.PurePath("/fake_dir/fake_path.txt")
        conf = config.Config("Linux", config_path)
        mock_parser = configparser.ConfigParser.return_value
        props = {
            "codec": str,
            "bitrate": int,
            "samplerate": int,
            "notifications": bool,
            "colors": str,
            "search_at_launch": bool,
            "alsa_device": str,
            "port": int}

        for prop_name, prop_type in props.items():
            with self.subTest(prop=prop_name):
                mock_parser.reset_mock()
                _ = getattr(conf, prop_name)

                if prop_type == str:
                    mock_parser.get.assert_called_once_with(
                        config.SETTINGS, prop_name)
                    mock_parser.getboolean.assert_not_called()
                    mock_parser.getint.assert_not_called()
                elif prop_type == int:
                    mock_parser.get.assert_not_called()
                    mock_parser.getint.assert_called_once_with(
                        config.SETTINGS, prop_name)
                    mock_parser.getboolean.assert_not_called()
                elif prop_type == bool:
                    mock_parser.get.assert_not_called()
                    mock_parser.getint.assert_not_called()
                    mock_parser.getboolean.assert_called_once_with(
                        config.SETTINGS, prop_name)

    def testPropertySetters(self):
        config_path = pathlib.PurePath("/fake_dir/fake_path.txt")
        conf = config.Config("Linux", config_path)
        mock_parser = configparser.ConfigParser.return_value
        props = {
            "backend": str,
            "codec": str,
            "bitrate": int,
            "samplerate": int,
            "notifications": bool,
            "colors": str,
            "search_at_launch": bool,
            "alsa_device": str,
            "port": int}

        for prop_name, prop_type in props.items():
            with self.subTest(prop=prop_name):
                mock_parser.reset_mock()
                value = prop_type()
                setattr(conf, prop_name, value)

                mock_parser.set.assert_called_once_with(
                    config.SETTINGS, prop_name, str(value))

    def testEmptyAlsaDevice(self):
        config_path = pathlib.PurePath("/fake_dir/fake_path.txt")
        conf = config.Config("Linux", config_path)
        mock_parser = configparser.ConfigParser.return_value
        none_str = "None"

        conf.alsa_device = None
        mock_parser.set.assert_called_once_with(
            config.SETTINGS, config.ALSA_DEVICE, none_str)

        mock_parser.get.return_value = none_str
        self.assertIsNone(conf.alsa_device)

        mock_parser.get.return_value = "some value"
        self.assertEqual("some value", conf.alsa_device)


class OnDiskConfigTests(unittest.TestCase):
    """Covers a config file as it actually ends up on disk.

    The port lives here because the tray has no command line to take it from,
    and 5000 is a busy address: shairport-sync on Linux, AirPlay Receiver on
    macOS.
    """

    def setUp(self):
        self.config_path = pathlib.Path(
            self.enterContext(tempfile.TemporaryDirectory())) / "conf.cfg"

    def read_back(self) -> config.Config:
        conf = config.Config(platform="Linux", config_path=self.config_path,
                             read_only=True)
        conf.load_and_validate()
        return conf

    def testAFreshConfigGetsTheDefaultPort(self):
        with config.Config(platform="Linux", config_path=self.config_path):
            pass

        self.assertEqual(self.read_back().port, constants.DEFAULT_PORT)

    def testAnOlderConfigGainsThePortWithoutLosingAnything(self):
        """A config written before the port existed still has to load."""
        self.config_path.write_text(
            "[settings]\nbackend = parec\ncodec = flac\nbitrate = 320\n"
            "samplerate = 48000\nnotifications = True\ncolors = white\n"
            "search_at_launch = True\nalsa_device = None\n")

        with config.Config(platform="Linux", config_path=self.config_path):
            pass

        conf = self.read_back()
        self.assertEqual(conf.port, constants.DEFAULT_PORT)
        self.assertEqual(conf.codec, "flac")
        self.assertEqual(conf.bitrate, 320)

    def testAChosenPortSurvivesARoundTrip(self):
        with config.Config(platform="Linux",
                           config_path=self.config_path) as conf:
            conf.port = 5100

        self.assertEqual(self.read_back().port, 5100)

    def testResettingPutsEverythingBack(self):
        """The "Reset Settings" button, which used to raise instead."""
        with config.Config(platform="Linux",
                           config_path=self.config_path) as conf:
            conf.port = 5100
            conf.codec = "flac"

        conf = config.Config(platform="Linux", config_path=self.config_path)
        conf.load_and_validate()
        conf.write_defaults()

        restored = self.read_back()
        self.assertEqual(restored.port, constants.DEFAULT_PORT)
        self.assertEqual(restored.codec, "mp3")
