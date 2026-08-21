# This file is part of mkchromecast.

from dataclasses import dataclass
import errno
import flask
from functools import partial
import multiprocessing
import os
import pickle
import psutil
import socket
from subprocess import Popen, PIPE
import sys
import textwrap
import threading
import time
from typing import Callable, Optional, Union

import mkchromecast
from mkchromecast.audio_devices import inputint, outputint
from mkchromecast import colors

FlaskViewReturn = Union[str, flask.Response]


@dataclass
class BackendInfo:
    name: Optional[str] = None
    # TODO(xsdg): Switch to pathlib for this.
    path: Optional[str] = None


# TODO(xsdg): Consider porting to https://github.com/pallets-eco/flask-classful
# for a more natural approach to using Flask in an encapsulated way.
class FlaskServer:
    """Singleton Flask server for Chromecast audio and video casting.

    Given that Flask is module-based, this "class" encapsulates the state at a
    class level, and not at an instance level.
    """

    _app: Optional[flask.Flask] = None
    _video_mode: Optional[bool] = None

    _mkcc: mkchromecast.Mkchromecast
    _stream_url: str = "stream"

    # Common arguments.
    _command: Union[str, list[str]]
    _media_type: str

    # Audio arguments.
    _adevice: Optional[str]
    _backend: BackendInfo
    _bitrate: int
    _buffer_size: int
    _codec: str
    _platform: str
    _samplerate: str

    # Video arguments.
    _chunk_size: int

    @staticmethod
    def _init_common(video_mode: bool) -> None:
        if FlaskServer._app is not None or FlaskServer._video_mode is not None:
            raise Exception("Flask Server can only be initialized once.")

        FlaskServer._app = flask.Flask("mkchromecast")
        FlaskServer._app.add_url_rule("/", view_func=FlaskServer._index)

        # TODO(xsdg): Maybe just have distinct audio and video endpoints?
        if video_mode:
            FlaskServer._app.add_url_rule("/stream",
                                          view_func=FlaskServer._stream_video)
        else:
            FlaskServer._app.add_url_rule("/stream",
                                          view_func=FlaskServer._stream_audio)

        FlaskServer._video_mode = video_mode

    @staticmethod
    def init_audio(adevice: Optional[str],
                   backend: BackendInfo,
                   bitrate: int,
                   buffer_size: int,
                   codec: str,
                   command: Union[str, list[str]],
                   media_type: str,
                   platform: str,
                   samplerate: str) -> None:
        FlaskServer._init_common(video_mode=False)

        FlaskServer._adevice = adevice
        FlaskServer._backend = backend
        FlaskServer._bitrate = bitrate
        FlaskServer._buffer_size = buffer_size
        FlaskServer._codec = codec
        FlaskServer._command = command
        FlaskServer._media_type = media_type
        FlaskServer._platform = platform
        FlaskServer._samplerate = samplerate

    @staticmethod
    def init_video(chunk_size: int,
                   command: Union[str, list[str]],
                   media_type: str) -> None:
        FlaskServer._init_common(video_mode=True)

        FlaskServer._chunk_size = chunk_size
        FlaskServer._command = command
        FlaskServer._media_type = media_type

    @staticmethod
    def run(host: str, port: int) -> None:
        FlaskServer._ensure_initialized()

        # NOTE(xsdg): video.py used threaded=True and didn't specify
        # passthrough_errors.  audio.py used passthrough_errors=False and didn't
        # specify threaded.
        # I _believe_ that threaded is a bad idea, since it would potentially
        # launch multiple streaming pipelines.  I could be wrong about that,
        # though.

        # Original comment: Note that passthrough_errors=False is useful when
        # reconnecting. In that way, flask won't die.
        FlaskServer._app.run(host=host, port=port, passthrough_errors=False)

    @staticmethod
    def _ensure_initialized():
        if FlaskServer._app is None or FlaskServer._video_mode is None:
            raise Exception("Flask Server needs to be initialized first.")

    @staticmethod
    def _ensure_audio_mode():
        FlaskServer._ensure_initialized()
        if FlaskServer._video_mode == True:
            raise Exception(
                "Tried to use audio mode, but Flask Server was initialized in "
                "video mode.")

    @staticmethod
    def _ensure_video_mode():
        FlaskServer._ensure_initialized()
        if FlaskServer._video_mode == False:
            raise Exception(
                "Tried to use vidio mode, but Flask Server was initialized in "
                "audio mode.")

    @staticmethod
    def _index() -> FlaskViewReturn:
        FlaskServer._ensure_initialized()

        # TODO(xsdg): Add head and body tags?
        if FlaskServer._video_mode:
            return textwrap.dedent(f"""\
                <!doctype html>
                <title>Play {FlaskServer._stream_url}</title>
                <video controls autoplay >
                    <source src="{FlaskServer._stream_url}" type="video/mp4" >
                    Your browser does not support this video format.
                </video>
                """)
        else:
            return textwrap.dedent(f"""\
                <!doctype html>
                <title>Play {FlaskServer._stream_url}</title>
                <audio controls autoplay >
                    <source src="{FlaskServer._stream_url}" type="audio/mp3" >
                    Your browser does not support this audio format.
                </audio>
                """)

    @staticmethod
    def _stream_video() -> flask.Response:
        FlaskServer._ensure_video_mode()

        process = Popen(FlaskServer._command, stdout=PIPE, bufsize=-1)
        read_chunk = partial(os.read, process.stdout.fileno(), FlaskServer._chunk_size)
        return flask.Response(iter(read_chunk, b""), mimetype=FlaskServer._media_type)

    @staticmethod
    def _stream_audio():
        FlaskServer._ensure_audio_mode()

        if (
            FlaskServer._platform == "Linux"
            and FlaskServer._backend.name == "parec"
            and FlaskServer._backend.path is not None
        ):
            # parec negotiates 44100Hz unless told otherwise, so without
            # --rate its output silently disagreed with whatever rate we
            # then declared to the encoder.
            c_parec = [
                FlaskServer._backend.path,
                "--format=s16le",
                f"--rate={FlaskServer._samplerate}",
                "--channels=2",
                "-d", "Mkchromecast.monitor",
            ]
            parec = Popen(c_parec, stdout=PIPE)

            try:
                process = Popen(FlaskServer._command, stdin=parec.stdout, stdout=PIPE, bufsize=-1)
            except FileNotFoundError:
                print("Failed to execute {}".format(FlaskServer._command))
                message = "Have you installed lame, see https://github.com/muammar/mkchromecast#linux-1?"
                raise Exception(message)

        else:
            process = Popen(FlaskServer._command, stdout=PIPE, bufsize=-1)
        read_chunk = partial(os.read, process.stdout.fileno(), FlaskServer._buffer_size)
        return flask.Response(iter(read_chunk, b""), mimetype=FlaskServer._media_type)


def port_is_free(host: str, port: int) -> bool:
    """Returns whether we can bind a listening socket on host:port."""
    probe_host = "0.0.0.0" if host in {"", "0.0.0.0"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((probe_host, port))
            return True
        except OSError as e:
            if e.errno in {errno.EADDRINUSE, errno.EACCES}:
                return False
            raise


# Launching the pipeline command in a separate process.
class PipelineProcess:
    def __init__(self, flask_init: Callable, host: str, port: int, platform: str):
        self._host = host
        self._port = port
        self._proc = multiprocessing.Process(
            target=PipelineProcess.start_app,
            args=(flask_init, host, port, platform,)
        )
        self._proc.daemon = True

    def start(self) -> None:
        """Starts the streaming server, aborting if the port is unavailable.

        Without this check, a failed bind would only be reported on the child
        process' stdout, and we would go on to point the cast device at a port
        served by some unrelated program.
        """
        if not port_is_free(self._host, self._port):
            print(colors.error(
                f"Port {self._port} is already in use by another program."))
            print(colors.options("Hint:")
                  + f" retry with --port {self._port + 1}, or free that port. "
                  "On Ubuntu it is often taken by shairport-sync; check with "
                  "`systemctl status shairport-sync`.")
            raise SystemExit(1)

        self._proc.start()

    def wait_until_serving(self, timeout: float = 10.0) -> bool:
        """Waits until the streaming server accepts connections.

        Returns:
            True once the server is reachable, or False if the process died or
            did not come up before the timeout expired.
        """
        host = "127.0.0.1" if self._host in {"", "0.0.0.0"} else self._host
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if not self._proc.is_alive():
                return False
            try:
                with socket.create_connection((host, self._port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)

        return False

    @staticmethod
    def start_app(flask_init: Callable, host: str, port: int, platform: str):
        """Starting the streaming server."""
        monitor_daemon = ParentMonitor(platform)
        monitor_daemon.start()

        flask_init()
        FlaskServer.run(host=host, port=port)


class ParentMonitor(object):
    """Thread that terminates this process if the main process dies.

    A normal running of mkchromecast will have 2 threads in the streaming
    process when ffmpeg is used.
    """

    def __init__(self, platform: str):
        self._monitor_thread = threading.Thread(target=ParentMonitor._monitor_loop,
                                                args=(platform,))
        self._monitor_thread.daemon = True

    def start(self):
        self._monitor_thread.start()

    @staticmethod
    def _monitor_loop(platform: str):
        with open("/tmp/mkchromecast.pid", "rb") as pid_file:
            main_pid = int(pickle.load(pid_file))
        print(colors.options("PID of main process:") + f" {main_pid}")

        local_pid = os.getpid()
        print(colors.options("PID of streaming process:") + f" {os.getpid()}")

        while psutil.pid_exists(local_pid):
            try:
                time.sleep(0.5)
                # With this I ensure that if the main app fails, everything
                # will get back to normal
                if not psutil.pid_exists(main_pid):
                    if platform == "Darwin":
                        inputint()
                        outputint()
                    else:
                        from mkchromecast.pulseaudio import (get_sink_list,
                                                             remove_sink)

                        # This process does not inherit the parent's memory
                        # (multiprocessing uses forkserver from Python 3.14
                        # on), so the module has no record of the sink we
                        # created and remove_sink alone would do nothing.
                        get_sink_list()
                        remove_sink()
                    parent = psutil.Process(local_pid)
                    # TODO(xsdg): This is unlikely to finish, given that this
                    # code itself is running in one of the child processes.  We
                    # should instead signal the parent to terminate, and have it
                    # handle child cleanup on its own.
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
