# This file is part of mkchromecast.
"""Tells whether the desktop is running a dark theme.

The tray artwork is black on a transparent background, which all but
disappears against a dark panel.  A white variant of every icon has always
shipped, but choosing it was a manual preference, so the icon stayed black
until the user went looking for the setting.
"""

import os
import platform as platform_module
import subprocess
from typing import Optional


# The icon variants the config file can name, plus the value that means
# "ask the desktop".
ICON_COLORS = ("black", "blue", "white")
AUTO_COLOR = "auto"

DARK_ICON = "white"
LIGHT_ICON = "black"


def _command_output(command: list[str]) -> Optional[str]:
    """Returns the command's output, or None if it could not be asked."""
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def _linux_prefers_dark() -> Optional[bool]:
    """Reads the preference from the desktop's interface settings."""
    # GNOME, and everything that follows its settings, keeps the answer here.
    # "default" means the user never chose, so it is not an answer.
    scheme = _command_output(
        ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    if scheme:
        if "prefer-dark" in scheme:
            return True
        if "prefer-light" in scheme:
            return False

    # Falling back to the theme name catches the desktops that never adopted
    # color-scheme, and the sessions that left it at "default".
    gtk_theme = _command_output(
        ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"])
    if gtk_theme:
        return "dark" in gtk_theme.lower()

    # Set when a theme is forced for one application rather than session-wide.
    forced = os.environ.get("GTK_THEME")
    if forced:
        return "dark" in forced.lower()

    return None


def _darwin_prefers_dark() -> Optional[bool]:
    """Reads the appearance from the global domain."""
    # The key is simply absent, and `defaults` exits non-zero, when the
    # appearance is light.
    style = _command_output(["defaults", "read", "-g", "AppleInterfaceStyle"])
    if style is None:
        return False

    return "dark" in style.lower()


def prefers_dark(system: Optional[str] = None) -> Optional[bool]:
    """Whether the desktop is dark, or None when it does not say."""
    system = system or platform_module.system()

    if system == "Darwin":
        return _darwin_prefers_dark()

    return _linux_prefers_dark()


def icon_color(configured: str, system: Optional[str] = None) -> str:
    """Resolves a configured colour into the name of an icon variant.

    An explicit choice is honoured as it always was.  Anything else -- the
    "auto" default, or whatever a hand-edited config file happens to hold --
    asks the desktop, and falls back to black when it gives no answer, which
    is what the icon was before any of this existed.
    """
    if configured in ICON_COLORS:
        return configured

    return DARK_ICON if prefers_dark(system) else LIGHT_ICON
