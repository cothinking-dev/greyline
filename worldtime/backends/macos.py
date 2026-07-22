"""macOS backend (beta, untested) — set the desktop picture via ``osascript``.

macOS sets the desktop through System Events; ``apply()`` shells out to
``osascript`` (no dependency). The catch: WindowServer caches the wallpaper by
file *path*, so re-setting the same path does not refresh the screen. greyline
re-renders to a fixed ``<output>.png`` each tick, so we copy that render to a
freshly-named sibling file on every apply — a path macOS has not seen before —
and point the desktop at that, deleting the previous copies to avoid piling up.

Single combined desktop for now (per-space / per-display targeting is deferred).

Status: written without a Mac to test on. See the README's
"Windows & macOS (beta, untested)" section.
"""
import glob
import os
import subprocess
import sys
import tempfile

# Marker in the rotated filename so old copies can be found and pruned.
_ROTATE_PREFIX = ".greyline-wp-"


def available():
    return sys.platform == "darwin"


def outputs():
    """A single combined output (1920x1080 fallback).

    macOS reports displays via ``system_profiler SPDisplaysDataType``, but a single
    ``osascript`` call sets every desktop at once, so one output is enough here.
    """
    return [{"name": "default", "width": 1920, "height": 1080, "scale": 1.0}]


def _rotate(png_path):
    """Copy png_path to a uniquely-named sibling and remove earlier copies.

    Returns the new path. The unique name defeats WindowServer's path-based cache.
    """
    d = os.path.dirname(png_path) or "."
    # Prune previous rotations so the runtime dir does not grow without bound.
    for old in glob.glob(os.path.join(d, f"{_ROTATE_PREFIX}*.png")):
        try:
            os.remove(old)
        except OSError:
            pass
    fd, new = tempfile.mkstemp(dir=d, prefix=_ROTATE_PREFIX, suffix=".png")
    with os.fdopen(fd, "wb") as dst, open(png_path, "rb") as src:
        dst.write(src.read())
    return new


def apply(name, png_path):
    target = _rotate(png_path)
    script = (
        'tell application "System Events" to set picture of every desktop '
        f'to POSIX file "{target}"'
    )
    subprocess.run(["osascript", "-e", script],
                   capture_output=True, text=True, check=True)
