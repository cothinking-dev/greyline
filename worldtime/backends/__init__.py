"""Display adapters: the only platform-specific code.

Each backend module exposes:
    available() -> bool                 # right environment + tool present
    outputs()   -> list[dict]           # [{name, width, height, scale}, ...]
    apply(name, png_path) -> None       # set that output's wallpaper

Auto-detection order favours the most specific compositor IPC first.
"""
import importlib

# Checked in order by detect(). The windows/macos backends are platform-gated
# (available() returns False off their OS), so they never interfere on Linux.
_ORDER = ["sway", "swww", "hyprpaper", "x11", "windows", "macos"]


def get(name):
    return importlib.import_module(f"{__name__}.{name}")


def detect():
    """Return the name of the first available backend, or None."""
    for name in _ORDER:
        try:
            if get(name).available():
                return name
        except Exception:
            continue
    return None


def resolve(name="auto"):
    """Resolve 'auto' to a concrete backend module; raise if none usable."""
    if name == "auto":
        name = detect()
        if not name:
            raise RuntimeError(
                "no supported wallpaper backend detected "
                "(sway/swww/hyprpaper/feh/windows/macos); set backend explicitly"
            )
    mod = get(name)
    if not mod.available():
        raise RuntimeError(f"backend {name!r} is not available in this environment")
    return name, mod
