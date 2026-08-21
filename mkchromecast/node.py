# This file is part of mkchromecast.
"""
These functions are used to get up the streaming server using node.

To call them:
    from mkchromecast.node import *
    name()
"""

# This file is audio-only for node.  Video via node is (currently) handled
# completely within video.py.

import multiprocessing
import os
import pickle
import psutil
import shutil
import time
import re
import sys
import signal
import subprocess

import mkchromecast
from mkchromecast.audio_devices import inputint, outputint
from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import utils
from mkchromecast.cast import Casting
from mkchromecast.constants import OpMode


def streaming(mkcc: mkchromecast.Mkchromecast):
    print(colors.options("Selected backend:") + " " + mkcc.backend)

    if mkcc.debug is True:
        print(
            ":::node::: variables %s, %s, %s, %s, %s"
            % (mkcc.backend, mkcc.codec, mkcc.bitrate, mkcc.samplerate, mkcc.notifications)
        )

    # These were only annotated, never assigned, so the first read below
    # raised UnboundLocalError and the node backend could never run.
    bitrate: int = mkcc.bitrate
    samplerate: int = mkcc.samplerate

    if mkcc.youtube_url is None and mkcc.backend == "node":
        bitrate = utils.clamp_bitrate(mkcc.codec, bitrate)
        print(colors.options("Using bitrate: ") + f"{bitrate}k.")

        if mkcc.codec in constants.QUANTIZED_SAMPLE_RATE_CODECS:
            samplerate = utils.quantize_sample_rate(mkcc.codec, samplerate)

        print(colors.options("Using sample rate:") + f" {samplerate}Hz.")

    """
    Node section
    """
    # Look on the user's PATH first: the previous hardcoded list only covered
    # /usr/local/bin/node, so a distro node (/usr/bin/node on Debian and
    # Ubuntu) was reported as "not installed".
    node_bin = shutil.which("node") or shutil.which("nodejs")
    if node_bin is None:
        for bundled in ["./bin/node", "./nodejs/bin/node"]:
            if os.path.exists(bundled):
                node_bin = bundled
                break

    if node_bin is None:
        webcast = None
        print(colors.warning("Node is not installed..."))
        print(
            colors.warning("Use your package manager or their official " "installer...")
        )
    else:
        webcast = [
            node_bin,
            "./nodejs/node_modules/webcast-osx-audio/bin/webcast.js",
            "-b",
            str(bitrate),
            "-s",
            str(samplerate),
            # Was hardcoded to 5000, which broke --port: cast.py builds the
            # media URL from mkcc.port, so the device asked for a port nothing
            # was listening on.
            "-p",
            str(mkcc.port),
            "-u",
            "stream",
        ]

    if webcast is not None:
        p = subprocess.Popen(webcast)

        if mkcc.debug is True:
            print(":::node::: node command: %s." % webcast)

        f = open("/tmp/mkchromecast.pid", "rb")
        pidnumber = int(pickle.load(f))
        print(colors.options("PID of main process:") + " " + str(pidnumber))

        localpid = os.getpid()
        print(colors.options("PID of streaming process: ") + str(localpid))

        while p.poll() is None:
            try:
                time.sleep(0.5)
                # With this I ensure that if the main app fails, everything
                # will get back to normal
                if psutil.pid_exists(pidnumber) is False:
                    inputint()
                    outputint()
                    parent = psutil.Process(localpid)
                    # or parent.children() for recursive=False
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
            except KeyboardInterrupt:
                print("Ctrl-c was requested")
                sys.exit(0)
            except IOError:
                print("I/O Error")
                sys.exit(0)
            except OSError:
                print("OSError")
                sys.exit(0)
        else:
            print(colors.warning("Reconnecting node streaming..."))
            if mkcc.platform == "Darwin" and mkcc.notifications:
                if os.path.exists("images/google.icns") is True:
                    noticon = "images/google.icns"
                else:
                    noticon = "google.icns"
            if mkcc.debug is True:
                print(
                    ":::node::: platform, tray, notifications: %s, %s, %s."
                    % (mkcc.platform, mkcc.tray, mkcc.notifications)
                )

            if mkcc.platform == "Darwin" and mkcc.operation == OpMode.TRAY and mkcc.notifications:
                reconnecting = [
                    "./notifier/terminal-notifier.app/Contents/MacOS/terminal-notifier",
                    "-group",
                    "cast",
                    "-contentImage",
                    noticon,
                    "-title",
                    "mkchromecast",
                    "-subtitle",
                    "node server failed",
                    "-message",
                    "Reconnecting...",
                ]
                subprocess.Popen(reconnecting)

                if mkcc.debug is True:
                    print(
                        ":::node::: reconnecting notifier command: %s." % reconnecting
                    )

            # This could potentially cause forkbomb-like behavior where each new
            # child process would create a new child process, ad infinitum.
            raise Exception("Internal error: Never worked; needs to be fixed.")

            relaunch(stream_audio, recasting, kill)
        return


class multi_proc(object):
    def __init__(self):
        self._mkcc = mkchromecast.Mkchromecast()
        self.proc = multiprocessing.Process(target=streaming, args=(self._mkcc,))
        self.proc.daemon = False

    def start(self):
        self.proc.start()


def kill():
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM)
    return


def relaunch(func1, func2, func3):
    func1()
    func2()
    func3()
    return


def recasting():
    mkcc = mkchromecast.Mkchromecast()
    start = Casting(mkcc)
    start.initialize_cast()
    start.get_devices()
    start.play_cast()
    return


def stream_audio():
    st = multi_proc()
    st.start()
