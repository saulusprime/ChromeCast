# This file is part of mkchromecast.

import os
import socket

import mkchromecast
from mkchromecast import audio
from mkchromecast import cast
from mkchromecast import colors
from mkchromecast import config
from mkchromecast import node
from mkchromecast import utils
from mkchromecast.audio_devices import inputdev, outputdev
# Imported directly: the `cast` global below gets rebound to a Chromecast
# instance, so `cast.CastError` is not reliable inside _play_cast_.
from mkchromecast.cast import CastError
from mkchromecast.constants import OpMode
from mkchromecast.pulseaudio import (check_sink, create_sink,
                                     PulseAudioNotAvailable)
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


# TODO(xsdg): Encapsulate this so that we don't do this work on import.
_mkcc = mkchromecast.Mkchromecast()


class Search(QObject):
    finished = pyqtSignal()
    intReady = pyqtSignal(list)

    @pyqtSlot()
    def _search_cast_(self):
        # This should fix the error socket.gaierror making the system tray to
        # be closed.
        try:
            cc = cast.Casting(_mkcc)
            cc.initialize_cast()
            self.intReady.emit(cc.available_devices)
            self.finished.emit()
        except socket.gaierror:
            if _mkcc.debug is True:
                print(colors.warning(
                    ":::Threading::: Socket error, failed to search for devices"))
            self.intReady.emit([])
            self.finished.emit()


class Player(QObject):
    pcastfinished = pyqtSignal()
    pcastready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # The device we are currently playing to, for the tray to read back.
        # This used to be a module-level global that _play_cast_ rebound from
        # the `cast` module to a Chromecast instance, which broke every
        # subsequent `cast.Casting(...)` lookup in this same function.
        self.cast = None

    @pyqtSlot()
    def _play_cast_(self):
        config_ = config.Config(platform=_mkcc.platform,
                                read_only=True,
                                debug=_mkcc.debug)
        with config_:
            if config_.backend == "node":
                node.stream_audio()
            else:
                # TODO(xsdg): Drop this reload stuff.
                try:
                    reload(mkchromecast.audio)
                except NameError:
                    from importlib import reload

                    reload(mkchromecast.audio)
                if not mkchromecast.audio.main():
                    self.pcastready.emit("_play_cast_ failed")
                    self.pcastfinished.emit()
                    return
        if _mkcc.platform == "Linux" and _mkcc.adevice is None:
            # We create the sink only if it is not available
            try:
                if not check_sink():
                    create_sink()
            except PulseAudioNotAvailable as e:
                print(colors.error(str(e)))
                self.pcastready.emit("_play_cast_ failed")
                self.pcastfinished.emit()
                return

        start = cast.Casting(_mkcc)
        start.initialize_cast()
        try:
            start.get_devices()
            start.play_cast()
            self.cast = start.cast
            # Let's change inputs at the end to avoid muting sound too early.
            # For Linux it does not matter given that user has to select sink
            # in pulse audio.  Therefore the sooner it is available, the
            # better.
            if _mkcc.platform == "Darwin":
                inputdev()
                outputdev()
            self.pcastready.emit("_play_cast_ success")
        except (AttributeError, CastError) as e:
            if _mkcc.debug is True:
                print(colors.warning(f":::Threading::: play_cast failed: {e}"))
            self.pcastready.emit("_play_cast_ failed")
        self.pcastfinished.emit()


url = "https://api.github.com/repos/muammar/mkchromecast/releases/latest"

class Updater(QObject):
    """This class is employed to check for new mkchromecast versions"""

    upcastfinished = pyqtSignal()
    updateready = pyqtSignal(str)

    @pyqtSlot()
    def _updater_(self):
        chk = cast.Casting(_mkcc)
        # `or None` here was a no-op: the left operand is always the result.
        if chk.ip == "127.0.0.1":  # We verify the local IP.
            self.updateready.emit("None")
        else:
            import requests

            try:
                from mkchromecast.version import __version__

                # Was scraped out of the raw response with str.strip, which
                # removes a *set of characters* rather than a prefix.
                latest = requests.get(url, timeout=10).json()["tag_name"]

                if (utils.version_tuple(latest)
                        > utils.version_tuple(__version__)):
                    print("Version %s is available to download" % latest)
                    self.updateready.emit(latest)
                else:
                    print("You are up to date.")
                    self.updateready.emit("False")
            except (requests.exceptions.RequestException,
                    ValueError, KeyError, TypeError):
                self.updateready.emit("error1")

        self.upcastfinished.emit()
