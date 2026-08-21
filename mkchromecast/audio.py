# This file is part of mkchromecast.

"""
Google Cast device has to point out to http://ip:5000/stream
"""

import os
import re
import shutil
from typing import Union

import mkchromecast
from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import pipeline_builder
from mkchromecast import stream_infra
from mkchromecast import utils
from mkchromecast.constants import OpMode
import mkchromecast.messages as msg

# The macOS .app bundle is launched with a minimal PATH that does not include
# Homebrew, so on Darwin we look there too before giving up.  On Linux we
# deliberately honour only the user's PATH.
DARWIN_EXTRA_BACKEND_PATH = (
    "./bin:./nodejs/bin:/usr/local/bin:/usr/local/sbin:/opt/homebrew/bin:"
    "/opt/X11/bin:/usr/X11/bin"
)


backend = stream_infra.BackendInfo()

# TODO(xsdg): Encapsulate this so that we don't do this work on import.
_mkcc = mkchromecast.Mkchromecast()
command: Union[str, list[str]]
media_type: str

# We make local copies of these attributes because they are sometimes modified.
# TODO(xsdg): clean this up more when we refactor this file.
host = _mkcc.host
port = _mkcc.port
platform = _mkcc.platform

ip = utils.get_effective_ip(platform, host_override=host, fallback_ip="0.0.0.0")

frame_size = 32 * _mkcc.chunk_size
buffer_size = 2 * _mkcc.chunk_size**2

encode_settings = pipeline_builder.EncodeSettings(
        codec=_mkcc.codec,
        adevice=_mkcc.adevice,
        bitrate=_mkcc.bitrate,
        frame_size=frame_size,
        samplerate=str(_mkcc.samplerate),
        segment_time=_mkcc.segment_time
    )

debug = _mkcc.debug

if debug is True:
    print(
        ":::audio::: chunk_size, frame_size, buffer_size: %s, %s, %s"
        % (_mkcc.chunk_size, frame_size, buffer_size)
    )

# This is to take the youtube URL
if _mkcc.operation == OpMode.YOUTUBE:
    print(colors.options("The Youtube URL chosen: ") + _mkcc.youtube_url)

    try:
        import urlparse

        url_data = urlparse.urlparse(_mkcc.youtube_url)
        query = urlparse.parse_qs(url_data.query)
    except ImportError:
        import urllib.parse

        url_data = urllib.parse.urlparse(_mkcc.youtube_url)
        query = urllib.parse.parse_qs(url_data.query)
    video = query["v"][0]
    print(colors.options("Playing video:") + " " + video)
    command = ["yt-dlp", "-o", "-", _mkcc.youtube_url]
    media_type = "audio/mp4"
else:
    backend.name = _mkcc.backend

    # Resolve through the user's PATH in every mode.  This used to run only in
    # tray mode; everywhere else backend.path was left as the bare name, and a
    # backend that could not be found surfaced much later as an encoder
    # started with no input.
    backend.path = shutil.which(backend.name)
    if backend.path is None and platform == "Darwin":
        backend.path = shutil.which(backend.name,
                                    path=DARWIN_EXTRA_BACKEND_PATH)

    if debug:
        print(f"Resolved backend {backend.name} to {repr(backend.path)}")

    if encode_settings.codec == "mp3":
        media_type = "audio/mpeg"
    else:
        media_type = f"audio/{encode_settings.codec}"

    print(colors.options("Selected backend:") + f" {backend}")
    print(colors.options("Selected audio codec:") + f" {encode_settings.codec}")

    if backend.name != "node":
        encode_settings.bitrate = utils.clamp_bitrate(encode_settings.codec,
                                                      encode_settings.bitrate)

        if encode_settings.bitrate != "None":
            print(colors.options("Using bitrate:") + f" {encode_settings.bitrate}")

        if encode_settings.codec in constants.QUANTIZED_SAMPLE_RATE_CODECS:
            encode_settings.samplerate = str(utils.quantize_sample_rate(
                encode_settings.codec,
                int(encode_settings.samplerate))
            )

        print(colors.options("Using sample rate:") + f" {encode_settings.samplerate}Hz")

    builder = pipeline_builder.Audio(backend, platform, encode_settings)
    command = builder.command

if debug is True:
    print(":::audio::: command " + str(command))


def _flask_init():
    # TODO(xsdg): Update init_audio to take an EncodeSettings.
    stream_infra.FlaskServer.init_audio(
        adevice=encode_settings.adevice,
        backend=backend,
        bitrate=encode_settings.bitrate,
        buffer_size=buffer_size,
        codec=encode_settings.codec,
        command=command,
        media_type=media_type,
        platform=platform,
        samplerate=encode_settings.samplerate)


def main() -> bool:
    """Starts the streaming server.  Returns whether it came up."""
    if backend.name is not None and backend.path is None:
        print(colors.error(
            f"Could not find the {backend.name!r} backend on your PATH."))
        print(colors.options("Hint:")
              + " install it, or pick another one with --encoder-backend.")
        return False

    pipeline = stream_infra.PipelineProcess(_flask_init, ip, port, platform)
    pipeline.start()
    if not pipeline.wait_until_serving():
        print(colors.error("The streaming server failed to start."))
        return False

    return True
