# This file is part of mkchromecast.

import unittest
from unittest import mock

from mkchromecast import cast


class DeviceSelectionTests(unittest.TestCase):
    """Covers turning the index typed by the user into a device.

    A bad index used to reach `raise Exception("Internal error: Never worked")`,
    after having already been written to the pickle file.
    """

    def setUp(self):
        self.terminate = self.enterContext(
            mock.patch.object(cast, "terminate", autospec=True))
        self.write_pickle = self.enterContext(
            mock.patch.object(cast.Casting, "_write_index_to_pickle",
                              autospec=True))

    def make_casting(self, index, typed_next=()):
        """Builds a Casting that skips discovery, with a canned list of devices.

        Args:
            index: what the user typed first.
            typed_next: what the user types at each following prompt.
        """
        casting = cast.Casting.__new__(cast.Casting)
        casting.cclist = [[0, "Kitchen", "Gcast"], [1, "Studio", "Gcast"]]
        casting.index = index

        typed = list(typed_next)

        def select_a_device():
            casting.index = typed.pop(0)

        casting.select_a_device = select_a_device
        return casting

    def testValidIndexSelectsTheDevice(self):
        casting = self.make_casting("1")
        casting.input_device()

        self.assertEqual("Studio", casting.cast_to)
        self.terminate.assert_not_called()
        self.write_pickle.assert_called_once()

    def testOutOfRangeIndexIsRetried(self):
        casting = self.make_casting("7", typed_next=["0"])
        casting.input_device()

        self.assertEqual("Kitchen", casting.cast_to)
        self.terminate.assert_not_called()

    def testTextInsteadOfAnIndexIsRetried(self):
        casting = self.make_casting("kitchen", typed_next=["1"])
        casting.input_device()

        self.assertEqual("Studio", casting.cast_to)
        self.terminate.assert_not_called()

    def testNegativeIndexIsRetried(self):
        # "-1" reads as a mistake, not as a request for the last device.
        casting = self.make_casting("-1", typed_next=["0"])
        casting.input_device()

        self.assertEqual("Kitchen", casting.cast_to)

    def testOnlyAValidIndexIsRecorded(self):
        casting = self.make_casting("7", typed_next=["0"])
        casting.input_device()

        self.write_pickle.assert_called_once()

    def testWritingThePickleCanBeSkipped(self):
        casting = self.make_casting("0")
        casting.input_device(write_to_pickle=False)

        self.assertEqual("Kitchen", casting.cast_to)
        self.write_pickle.assert_not_called()

    def testGivesUpAfterTooManyBadIndexes(self):
        bad = ["9"] * cast.SELECTION_ATTEMPTS
        casting = self.make_casting("9", typed_next=bad)
        casting.input_device()

        self.terminate.assert_called_once_with(1)
        self.write_pickle.assert_not_called()

    def testClosedStdinEndsTheApplication(self):
        # The first prompt is issued by bin/mkchromecast, outside input_device,
        # so EOF has to be handled where the reading happens.
        casting = self.make_casting("0")
        del casting.select_a_device  # Use the real one.

        with mock.patch("builtins.input", side_effect=EOFError):
            casting.select_a_device()

        self.terminate.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
