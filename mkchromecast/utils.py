# This file is part of mkchromecast.

import json
import os
import pickle
import psutil
import socket
import subprocess
import sys
from typing import List, Optional
from urllib.parse import urlparse

from mkchromecast import colors
from mkchromecast import constants
from mkchromecast import messages


def quantize_sample_rate(codec: str,
                         sample_rate: int,
                         limit_to_48k: bool = False) -> int:
    """Takes an arbitrary sample rate and aligns it to a standard value.

    It does this by rounding up to the next standard value, while staying below
    a reasonable maximum for the specified codec.

    Args:
        codec: The name of the codec in use.
        sample_rate: The original sample rate.

    Returns:
        An integer sample rate that has been aligned to the closest standard
        value.
    """
    # The behavior as implemented here differs from the legacy behavior.
    # The audio.py legacy behavior excluding no96k codecs was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100   Sample rates < 44100 would jump to 48000.
    #  43000 < x <= 72000  --> 48000
    #  72000 < x <= 90000  --> 88200
    #  90000 < x <= 96000  --> 96000
    #  96000 < x <= 176000 --> 176000
    # 176000 < x           --> 192000
    #
    # For no96k codecs (ogg and mp3), it was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100
    #  43000 < x <= 72000  --> 48000
    #  72000 < x <= 90000  --> 88200   Illegal sample rate for ogg or mp3.
    #  90000 < x <= 96000  --> 48000
    #  96000 < x <= 176000 --> 48000
    # 176000 < x           --> 48000
    #
    # The node.py legacy behavior was as follows:
    #  22000 < x <= 27050  --> 22050
    #  27050 < x <= 36000  --> 32000
    #  36000 < x <= 43000  --> 44100
    #  43000 < x <= 72000  --> 48000
    #  72000 < x           --> 48000 for no96k, x (unbounded) otherwise.

    # Target rates must be sorted in increasing order.
    target_rates: List[int]
    if limit_to_48k:
        target_rates = constants.MAX_48K_SAMPLE_RATES
    else:
        target_rates = constants.sample_rates_for_codec(codec)

    if sample_rate in target_rates:
        return sample_rate

    for target_rate in target_rates:
        if sample_rate < target_rate:
            # Because we're traversing in increasing order, the first time we
            # find a target_rate that's greater than the sample rate, we know
            # that's the next-largest value, so we can return that immediately.
            messages.print_samplerate_warning(codec)
            return target_rate

    # If we make it to this point, sample_rate is above the max target_rate, so
    # we just clamp to the max target_rate.
    messages.print_samplerate_warning(codec)
    print(colors.warning("Sample rate set to maximum!"))
    return target_rates[-1]


def clamp_bitrate(codec: str, bitrate: Optional[int]) -> int:
    # Legacy logic (also used str for bitrate rather than int):
    # if bitrate == "192" -> "192k"
    # elif bitrate == "None" -> pass
    # else
    #   if codec == "mp3" and bitrate > 320 -> "320" + warning
    #   elif codec == "ogg" and bitrate > 500 -> "500" + warning
    #   elif codec == "aac" and bitrate < 500 -> "500" + warning
    #   else -> bitrate + "k"

    if bitrate is None:
        print(colors.warning("Setting bitrate to default of "
                             f"{constants.DEFAULT_BITRATE}"))
        return constants.DEFAULT_BITRATE

    if bitrate <= 0:
        print(colors.warning(f"Bitrate of {bitrate} was invalid; setting to "
                             f"{constants.DEFAULT_BITRATE}"))
        return constants.DEFAULT_BITRATE

    max_bitrate_for_codec: dict[str, int] = {
        "mp3": 320,
        "ogg": 500,
        "aac": 500,
    }
    max_bitrate: Optional[int] = max_bitrate_for_codec.get(codec, None)

    if max_bitrate is None:
        # codec bitrate is unlimited.
        return bitrate

    if bitrate > max_bitrate:
        print(colors.warning(
            f"Configured bitrate {bitrate} exceeds max {max_bitrate} for "
            f"{codec} codec; setting to max."
        ))
        return max_bitrate

    return bitrate


def kill_children() -> None:
    """Stops our child processes, escalating to SIGKILL only if needed."""
    parent = psutil.Process(os.getpid())
    children = parent.children(recursive=True)

    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass

    _, still_alive = psutil.wait_procs(children, timeout=3)
    for child in still_alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass


def terminate(exit_code: int = 0) -> None:
    """Kills our children and exits the process.  Does not return.

    We exit via os._exit rather than sys.exit because this is also called
    from non-main threads, where sys.exit would unwind only that thread.
    That skips atexit handlers, so callers are responsible for any
    application-level cleanup (removing sinks, restoring audio devices)
    beforehand.

    The previous implementation SIGKILLed its own process, which discarded
    whatever was still sitting in stdout's buffer.  Anything printed before
    terminate() was therefore lost whenever output was redirected, and the
    exit status was always 137.
    """
    del_tmp()
    kill_children()

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)


def del_tmp(debug: bool = False) -> None:
    """Delete files created in /tmp/"""
    delete_me = ["/tmp/mkchromecast.tmp", "/tmp/mkchromecast.pid"]

    if debug:
        print(colors.important("Cleaning up /tmp/..."))

    for f in delete_me:
        if os.path.exists(f):
            os.remove(f)

    if debug:
        print(colors.success("[Done]"))


def is_installed(name, path, debug) -> bool:
    PATH = path
    iterate = PATH.split(":")
    for item in iterate:
        verifyif = str(item + "/" + name)
        if os.path.exists(verifyif) is False:
            continue
        else:
            if debug is True:
                print("Program %s found in %s." % (name, verifyif))
            return True
    return False


def version_tuple(version: str) -> tuple[int, ...]:
    """Turns a version string such as "v0.3.10" into a comparable tuple.

    Comparing the strings directly, as the updater used to, ranks "0.3.9"
    above "0.3.10".
    """
    numbers: list[int] = []
    for chunk in version.strip().lstrip("vV").split("."):
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        numbers.append(int(digits) if digits else 0)

    return tuple(numbers)


def check_url(url):
    """Check if a URL is correct"""
    try:
        result = urlparse(url)
        return True if [result.scheme, result.netloc, result.path] else False
    except Exception as e:
        return False


def writePidFile() -> None:
    pid_filename = "/tmp/mkchromecast.pid"
    # This is to verify that pickle tmp file exists
    if os.path.exists(pid_filename):
        os.remove(pid_filename)

    pid = str(os.getpid())
    with open(pid_filename, "wb") as pid_file:
        pickle.dump(pid, pid_file)


def checkmktmp() -> None:
    # This is to verify that pickle tmp file exists
    if os.path.exists("/tmp/mkchromecast.tmp"):
        os.remove("/tmp/mkchromecast.tmp")


def check_file_info(name, what=None):
    """Check things about files"""

    command = [
        "ffprobe",
        "-show_format",
        "-show_streams",
        "-loglevel", "quiet",
        "-print_format", "json",
        name,
    ]

    info = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    info_out, info_error = info.communicate()
    d = json.loads(info_out)

    if what == "bit-depth":
        bit_depth = d["streams"][0]["pix_fmt"]
        return bit_depth
    elif what == "resolution":
        resolution = d["streams"][0]["height"]
        resolution = str(resolution) + "p"
        return resolution


def get_effective_ip(platform, host_override=None, fallback_ip="127.0.0.1"):
    if host_override is None:
        return resolve_ip(platform, fallback_ip=fallback_ip)
    else:
        return host_override


def resolve_ip(platform, fallback_ip):
    if platform == "Linux":
        resolved_ip = _resolve_ip_linux()
    else:
        resolved_ip = _resolve_ip_nonlinux()
    if resolved_ip is None:
        resolved_ip = fallback_ip
    return resolved_ip


def _resolve_ip_linux():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.connect(("8.8.8.8", 80))
    except socket.error:
        return None
    return s.getsockname()[0]


def _resolve_ip_nonlinux():
    try:
        return socket.gethostbyname(f"{socket.gethostname()}.local")
    except socket.gaierror:
        return _get_first_network_ip_by_netifaces()


def _get_first_network_ip_by_netifaces():
    import netifaces

    interfaces = netifaces.interfaces()
    for interface in interfaces:
        if interface == "lo":
            continue
        iface = netifaces.ifaddresses(interface).get(netifaces.AF_INET)
        if iface != None and iface[0]["addr"] != "127.0.0.1":
            for e in iface:
                return str(e["addr"])
