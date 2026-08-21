# this file is part of mkchromecast.

import unittest
from unittest import mock

from mkchromecast import utils

class ClampBitrateTests(unittest.TestCase):
    def setUp(self):
        self.mock_print = self.enterContext(mock.patch("builtins.print", autospec=True))

    def testMissingBitrate(self):
        utils.clamp_bitrate("codec", None)

        self.mock_print.assert_called_once()
        print_str = self.mock_print.call_args.args[0]
        self.assertNotIn("invalid", print_str)
        self.assertIn("default", print_str)

    def testInvalidBitrate(self):
        for bitrate in -192, -1, 0:
            with self.subTest(bitrate=bitrate):
                self.mock_print.reset_mock()
                utils.clamp_bitrate("codec", bitrate)

                self.mock_print.assert_called_once()
                print_str = self.mock_print.call_args.args[0]
                self.assertIn("invalid", print_str)
                self.assertIn("192", print_str)

    def testNoClamp(self):
        # Codecs other than mp3, ogg, or aac shouldn't have an upper bound.
        cases = {"mp3": 320, "ogg": 500, "aac": 500, "opus": 1048576}
        for codec, bitrate in cases.items():
            with self.subTest(codec=codec):
                self.mock_print.reset_mock()
                self.assertEqual(bitrate, utils.clamp_bitrate(codec, bitrate))
                self.mock_print.assert_not_called()

    def testClamp(self):
        cases = {"mp3": 321, "ogg": 501, "aac": 501}
        for codec, bitrate in cases.items():
            with self.subTest(codec=codec):
                self.mock_print.reset_mock()
                self.assertEqual(bitrate - 1,
                                 utils.clamp_bitrate(codec, bitrate))

                self.mock_print.assert_called_once()
                print_str = self.mock_print.call_args.args[0]
                self.assertIn(codec, print_str)
                self.assertIn(str(bitrate), print_str)
                self.assertIn(str(bitrate - 1), print_str)


class VersionTupleTests(unittest.TestCase):
    def testOrdersNumerically(self):
        # String comparison used to rank 0.3.9 above 0.3.10.
        self.assertGreater(utils.version_tuple("0.3.10"),
                           utils.version_tuple("0.3.9"))
        self.assertGreater(utils.version_tuple("0.4.0"),
                           utils.version_tuple("0.3.99"))

    def testStripsLeadingV(self):
        self.assertEqual(utils.version_tuple("v1.2.3"),
                         utils.version_tuple("1.2.3"))

    def testHandlesExtraComponentsAndSuffixes(self):
        self.assertEqual((0, 3, 8, 1), utils.version_tuple("0.3.8.1"))
        self.assertEqual((1, 2, 0), utils.version_tuple("1.2.0rc1"))

    def testEqualVersionsAreNotNewer(self):
        self.assertFalse(
            utils.version_tuple("0.3.9") > utils.version_tuple("0.3.9"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
