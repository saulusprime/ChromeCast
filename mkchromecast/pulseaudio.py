# This file is part of mkchromecast.

import json
import os
import re
import subprocess
from typing import Optional

SINK_NAME = "Mkchromecast"

# pactl translates its human-readable output, so parsing it only works with
# the locale pinned.  The JSON output has stable, untranslated keys, but it
# only exists since pactl 16, hence the text fallback in get_sink_list.
_PACTL_ENV = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}

_sink_num: Optional[list[int]] = None


class PulseAudioNotAvailable(RuntimeError):
    """Raised when pactl is not installed or cannot be reached."""


def _pactl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Runs pactl with a pinned locale so its output is parseable."""
    try:
        return subprocess.run(
            ["pactl", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_PACTL_ENV,
            timeout=60,
            check=check,
        )
    except FileNotFoundError as e:
        raise PulseAudioNotAvailable(
            "pactl was not found. Install it (on Debian and Ubuntu: "
            "`sudo apt install pulseaudio-utils`), or select an ALSA device "
            "with --alsa-device."
        ) from e


def create_sink() -> None:
    global _sink_num

    result = _pactl(
        "load-module",
        "module-null-sink",
        f"sink_name={SINK_NAME}",
        f"sink_properties=device.description={SINK_NAME}",
        check=False,
    )

    if result.returncode != 0:
        raise PulseAudioNotAvailable(
            "Could not create the PulseAudio sink: "
            + result.stderr.decode("utf-8", "replace").strip()
        )

    module_index = result.stdout.decode("utf-8").strip()
    if not module_index.isdigit():
        raise PulseAudioNotAvailable(
            f"pactl returned an unexpected module index: {module_index!r}")

    _sink_num = [int(module_index)]


def remove_sink() -> None:
    global _sink_num

    if not _sink_num:
        return

    for num in _sink_num:
        # Not fatal: the module may already be gone, for instance because the
        # sound server restarted underneath us.  This also runs during cleanup,
        # where raising would mask whatever we were already exiting for.
        try:
            _pactl("unload-module", str(num), check=False)
        except PulseAudioNotAvailable:
            return

    _sink_num = None


def check_sink() -> bool:
    """Returns whether our sink already exists.

    Raises:
        PulseAudioNotAvailable: if pactl is not installed.  It used to return
            None in that case, which callers testing `is False` silently read
            as "the sink exists", so no sink was ever created.
    """
    result = _pactl("list", "sinks", check=False)
    return SINK_NAME in result.stdout.decode("utf-8", "replace")


def get_sink_list() -> None:
    """Records the modules owning any leftover Mkchromecast sink.

    Used to clear residual sinks from previous failed runs.  The values saved
    to _sink_num are module indices, which can be passed to pactl.
    """
    global _sink_num

    _sink_num = _get_sink_list_json()
    if _sink_num is None:
        _sink_num = _get_sink_list_text()


def _get_sink_list_json() -> Optional[list[int]]:
    """Reads the module indices from pactl's JSON output.

    Returns None when this pactl is too old to support --format=json.
    """
    result = _pactl("--format=json", "list", "sinks", check=False)
    if result.returncode != 0:
        return None

    try:
        sinks = json.loads(result.stdout.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    try:
        return [
            int(sink["owner_module"])
            for sink in sinks
            if str(sink.get("name", "")).startswith(SINK_NAME)
        ]
    except (KeyError, TypeError, ValueError):
        return None


def _get_sink_list_text() -> list[int]:
    """Reads the module indices by parsing pactl's plain-text output."""
    result = _pactl("list", "sinks")

    pattern = re.compile(
        r"^Sink\s*#\d+\s*$(?:\n^.*?$)*?\n\s*?Name:\s*?" + SINK_NAME + r".*"
        r"\s*?$(?:\n^.*?$)*?\n^\s*?Owner Module: (?P<module>\d+?)\s*?$",
        re.MULTILINE,
    )

    # NOTE: findall's second positional argument is `pos`, not a flags value.
    # Passing re.MULTILINE there used to skip the first 8 characters of the
    # output, which hid the very first sink in the list.
    matches = pattern.findall(result.stdout.decode("utf-8", "replace"))

    return [int(i) for i in matches]
