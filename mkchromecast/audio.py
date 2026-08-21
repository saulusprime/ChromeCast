# This file is part of mkchromecast.

"""
Google Cast device has to point out to http://ip:5000/stream
"""

import dataclasses
import shutil
import urllib.parse
from typing import Optional, Union

import mkchromecast
from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import pipeline_builder
from mkchromecast import stream_infra
from mkchromecast import utils
from mkchromecast.constants import OpMode

# The macOS .app bundle is launched with a minimal PATH that does not include
# Homebrew, so on Darwin we look there too before giving up.  On Linux we
# deliberately honour only the user's PATH.
DARWIN_EXTRA_BACKEND_PATH = (
    "./bin:./nodejs/bin:/usr/local/bin:/usr/local/sbin:/opt/homebrew/bin:"
    "/opt/X11/bin:/usr/X11/bin"
)


@dataclasses.dataclass
class AudioConfig:
    """Everything the streaming server needs in order to serve audio."""
    backend: stream_infra.BackendInfo
    buffer_size: int
    command: Union[str, list[str]]
    encode_settings: pipeline_builder.EncodeSettings
    ip: str
    media_type: str
    platform: str
    port: int


_config: Optional[AudioConfig] = None


def get_config() -> AudioConfig:
    """Returns the streaming configuration, building it once per process.

    All of this used to run at import time.  multiprocessing defaults to
    forkserver from Python 3.14 on, so the streaming process imports this
    module afresh instead of inheriting it, and the work ran a second time
    there -- printing every choice twice.
    """
    global _config
    if _config is None:
        _config = _build_config()

    return _config


def reload_settings() -> None:
    """Drops cached settings so the next call re-reads them from disk.

    The tray needs this after the preferences dialog, because the config
    file is read when Mkchromecast is built.  It replaces a reload() of
    this module, which only worked because the module did its work on
    import.
    """
    global _config
    _config = None
    mkchromecast.Mkchromecast.discard_shared_instance()


def _build_config() -> AudioConfig:
    mkcc = mkchromecast.Mkchromecast()

    frame_size = 32 * mkcc.chunk_size
    buffer_size = 2 * mkcc.chunk_size**2

    if mkcc.debug:
        print(":::audio::: chunk_size, frame_size, buffer_size: %s, %s, %s"
              % (mkcc.chunk_size, frame_size, buffer_size))

    encode_settings = pipeline_builder.EncodeSettings(
        codec=mkcc.codec,
        adevice=mkcc.adevice,
        bitrate=mkcc.bitrate,
        frame_size=frame_size,
        samplerate=str(mkcc.samplerate),
        segment_time=mkcc.segment_time,
    )

    backend = stream_infra.BackendInfo()
    command: Union[str, list[str]]
    media_type: str

    if mkcc.operation == OpMode.YOUTUBE:
        command = ["yt-dlp", "-o", "-", mkcc.youtube_url]
        media_type = "audio/mp4"
    else:
        backend.name = mkcc.backend

        # Resolve through the user's PATH in every mode, so that a backend
        # which is not installed is reported here rather than surfacing as an
        # encoder started with no input.
        backend.path = shutil.which(backend.name)
        if backend.path is None and mkcc.platform == "Darwin":
            backend.path = shutil.which(backend.name,
                                        path=DARWIN_EXTRA_BACKEND_PATH)

        if mkcc.debug:
            print(f"Resolved backend {backend.name} to {repr(backend.path)}")

        if encode_settings.codec == "mp3":
            media_type = "audio/mpeg"
        else:
            media_type = f"audio/{encode_settings.codec}"

        if backend.name != "node":
            encode_settings.bitrate = utils.clamp_bitrate(
                encode_settings.codec, encode_settings.bitrate)

            if encode_settings.codec in constants.QUANTIZED_SAMPLE_RATE_CODECS:
                encode_settings.samplerate = str(utils.quantize_sample_rate(
                    encode_settings.codec, int(encode_settings.samplerate)))

        command = pipeline_builder.Audio(
            backend, mkcc.platform, encode_settings).command

    if mkcc.debug:
        print(":::audio::: command " + str(command))

    return AudioConfig(
        backend=backend,
        buffer_size=buffer_size,
        command=command,
        encode_settings=encode_settings,
        ip=utils.get_effective_ip(mkcc.platform,
                                  host_override=mkcc.host,
                                  fallback_ip="0.0.0.0"),
        media_type=media_type,
        platform=mkcc.platform,
        port=mkcc.port,
    )


def _report(config: AudioConfig) -> None:
    """Prints the settings we picked.  Only the main process does this."""
    mkcc = mkchromecast.Mkchromecast()

    if mkcc.operation == OpMode.YOUTUBE:
        print(colors.options("The Youtube URL chosen: ") + mkcc.youtube_url)

        # The previous code indexed query["v"] unconditionally, which raised
        # KeyError on any URL without it, youtu.be short links included.
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(mkcc.youtube_url).query)
        if "v" in query:
            print(colors.options("Playing video:") + " " + query["v"][0])

        return

    print(colors.options("Selected backend:") + f" {config.backend}")
    print(colors.options("Selected audio codec:")
          + f" {config.encode_settings.codec}")

    if config.backend.name != "node":
        print(colors.options("Using bitrate:")
              + f" {config.encode_settings.bitrate}")
        print(colors.options("Using sample rate:")
              + f" {config.encode_settings.samplerate}Hz")


def _flask_init():
    config = get_config()

    # TODO(xsdg): Update init_audio to take an EncodeSettings.
    stream_infra.FlaskServer.init_audio(
        adevice=config.encode_settings.adevice,
        backend=config.backend,
        bitrate=config.encode_settings.bitrate,
        buffer_size=config.buffer_size,
        codec=config.encode_settings.codec,
        command=config.command,
        media_type=config.media_type,
        platform=config.platform,
        samplerate=config.encode_settings.samplerate)


def main() -> bool:
    """Starts the streaming server.  Returns whether it came up."""
    config = get_config()
    _report(config)

    if config.backend.name is not None and config.backend.path is None:
        print(colors.error("Could not find the "
                           f"{config.backend.name!r} backend on your PATH."))
        print(colors.options("Hint:")
              + " install it, or pick another one with --encoder-backend.")
        return False

    pipeline = stream_infra.PipelineProcess(
        _flask_init, config.ip, config.port, config.platform)
    pipeline.start()
    if not pipeline.wait_until_serving():
        print(colors.error("The streaming server failed to start."))
        return False

    return True
