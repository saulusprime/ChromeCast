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
import subprocess

import mkchromecast
from mkchromecast.audio_devices import inputint, outputint
from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import utils
from mkchromecast.cast import Casting
from mkchromecast.constants import OpMode


# How many times a dead node server is restarted before we stop trying.  The
# original code restarted it by spawning a fresh copy of this very process,
# which made every restart a new child of the previous one: a node that failed
# on startup turned that into an unbounded chain of processes.  Restarting in
# place, a bounded number of times, is what that path was meant to do.
NODE_RECONNECT_ATTEMPTS = 3

# Seconds given to a freshly started node server before we consider it up.
NODE_RESTART_GRACE_SECONDS = 2.0

# A server that stayed up this long counts as having worked: whatever kills it
# afterwards is a new failure, not a continuation of the one we just recovered
# from, so the attempt budget starts over.  Without this, a long tray session
# would run out of attempts days apart and then stop reconnecting for good.
NODE_HEALTHY_UPTIME_SECONDS = 60.0


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

    if webcast is None:
        return

    with open("/tmp/mkchromecast.pid", "rb") as f:
        pidnumber = int(pickle.load(f))
    print(colors.options("PID of main process:") + " " + str(pidnumber))

    localpid = os.getpid()
    print(colors.options("PID of streaming process: ") + str(localpid))

    attempt = 0
    while attempt <= NODE_RECONNECT_ATTEMPTS:
        if attempt:
            print(colors.warning(
                f"Reconnecting node streaming "
                f"(attempt {attempt} of {NODE_RECONNECT_ATTEMPTS})..."))
            notify_reconnecting(mkcc)
            time.sleep(NODE_RESTART_GRACE_SECONDS * attempt)

        started_at = time.monotonic()
        p = subprocess.Popen(webcast)

        if mkcc.debug is True:
            print(":::node::: node command: %s." % webcast)

        if attempt:
            # The device is still pointed at the server that just died, so it
            # has to be told to read the new one -- but only once node has
            # survived long enough to be listening.
            time.sleep(NODE_RESTART_GRACE_SECONDS)
            if p.poll() is None:
                recasting()

        watch_until_exit(p, pidnumber, localpid)

        if time.monotonic() - started_at >= NODE_HEALTHY_UPTIME_SECONDS:
            attempt = 0
        attempt += 1

    print(colors.error(
        "The node streaming server keeps failing; giving up after "
        f"{NODE_RECONNECT_ATTEMPTS} attempts."))
    return


def watch_until_exit(p: subprocess.Popen, pidnumber: int, localpid: int) -> None:
    """Blocks until the node server exits.

    Also acts as a watchdog on the main process: if that one is gone, the audio
    devices are restored and this process tears itself down instead of leaving
    a stream running with nobody to stop it.
    """
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


def notify_reconnecting(mkcc: mkchromecast.Mkchromecast) -> None:
    """Tells the user through the macOS notifier that node is being restarted."""
    if mkcc.debug is True:
        print(
            ":::node::: platform, tray, notifications: %s, %s, %s."
            % (mkcc.platform, mkcc.tray, mkcc.notifications)
        )

    if not (mkcc.platform == "Darwin"
            and mkcc.operation == OpMode.TRAY
            and mkcc.notifications):
        return

    if os.path.exists("images/google.icns") is True:
        noticon = "images/google.icns"
    else:
        noticon = "google.icns"

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
        print(":::node::: reconnecting notifier command: %s." % reconnecting)


class multi_proc(object):
    def __init__(self):
        self._mkcc = mkchromecast.Mkchromecast()
        self.proc = multiprocessing.Process(target=streaming, args=(self._mkcc,))
        self.proc.daemon = False

    def start(self):
        self.proc.start()


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
