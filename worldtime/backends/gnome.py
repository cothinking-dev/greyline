"""GNOME backend — set the shared desktop background through gsettings.

GNOME exposes one wallpaper setting rather than per-output geometry.  The two
output names alternate each minute so GNOME reloads the newly rendered PNG
instead of reusing a cached file at the same URI.
"""
import os
from pathlib import Path
import shutil
import subprocess
import time


def _is_gnome_session():
    desktops = ":".join(
        os.environ.get(name, "")
        for name in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")
    )
    return any("gnome" in desktop.lower() for desktop in desktops.split(":"))


def available():
    return _is_gnome_session() and shutil.which("gsettings") is not None


def outputs():
    # GNOME scales one shared background rather than exposing output geometry.
    # Alternate paths because replacing an image at the same URI may be cached.
    return [{
        "name": f"gnome-{int(time.time() // 60) % 2}",
        "width": 1920,
        "height": 1080,
        "scale": 1.0,
    }]


def apply(name, png_path):
    uri = Path(png_path).resolve().as_uri()
    for key in ("picture-uri", "picture-uri-dark"):
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", key, uri],
            capture_output=True,
            text=True,
            check=True,
        )
