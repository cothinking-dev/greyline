"""Configuration loading + system timezone detection (stdlib only: tomllib).

Merges the shipped default-config.toml with the user's
~/.config/greyline/config.toml (XDG-aware). Resolves the home timezone
("auto" => system tz) and flags the matching city as home.
"""
import os
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_PKG_DIR = os.path.dirname(__file__)
DEFAULT_CONFIG = os.path.join(_PKG_DIR, "default-config.toml")


def _xdg_config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def user_config_path():
    return os.path.join(_xdg_config_home(), "greyline", "config.toml")


def system_timezone():
    """Best-effort IANA name of the system timezone, or None.

    Order: $TZ, then the /etc/localtime symlink target (e.g. NixOS points it at
    .../zoneinfo/Asia/Kuala_Lumpur).
    """
    tz = os.environ.get("TZ")
    if tz:
        try:
            ZoneInfo(tz)
            return tz
        except (ZoneInfoNotFoundError, ValueError):
            pass
    try:
        target = os.path.realpath("/etc/localtime")
        marker = "/zoneinfo/"
        if marker in target:
            name = target.split(marker, 1)[1]
            ZoneInfo(name)  # validate
            return name
    except (OSError, ZoneInfoNotFoundError, ValueError):
        pass
    return None


def _deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    """Return the merged config dict, with home cities flagged.

    `path` overrides the user config location (else the XDG path is used if present).
    """
    with open(DEFAULT_CONFIG, "rb") as f:
        cfg = tomllib.load(f)

    user_path = path or user_config_path()
    if os.path.isfile(user_path):
        with open(user_path, "rb") as f:
            user = tomllib.load(f)
        # A user-provided city list replaces the defaults wholesale.
        cities = user.pop("city", None)
        cfg = _deep_merge(cfg, user)
        if cities is not None:
            cfg["city"] = cities

    # Resolve home timezone and flag matching cities.
    home_tz = cfg.get("home", {}).get("tz", "auto")
    if home_tz == "auto":
        home_tz = system_timezone()
    for c in cfg.get("city", []):
        c["home"] = bool(home_tz) and c.get("tz") == home_tz

    return cfg


def render_kwargs(cfg):
    """Map a loaded config dict to render.render() keyword arguments."""
    tw = cfg.get("twilight", {})
    home = cfg.get("home", {})
    return {
        "theme": cfg.get("theme", "dark"),
        "fmt": cfg.get("format", "24h"),
        "twilight_bands": bool(tw.get("bands", True)),
        "darkness": tw.get("darkness", "subtle"),
        "column_highlight": bool(home.get("column_highlight", True)),
        "home_color": home.get("color"),
        "font_scale": float(cfg.get("font_scale", 1.0)),
        "label_bg_alpha": int(
            cfg.get("label_bg_alpha", 130 if cfg.get("label_background", True) else 0)
        ),
        "map_style": cfg.get("map_style", "vector"),  # vector (default) | raster (bring your own art)
        "logo": bool(cfg.get("logo", True)),  # draw the bottom-left corner logo
        "logo_path": cfg.get("logo_path"),  # custom logo image (default: bundled Tux)
        "logo_color": cfg.get("logo_color"),  # hex → flat-colour (e.g. all-white) logo
        "logo_invert": bool(cfg.get("logo_invert", False)),  # recolour dark pixels to light
        "logo_scale": float(cfg.get("logo_scale", 1.0)),  # size the corner logo (1.0 = default)
        "bar_height": int(cfg.get("bar_height", 0)),  # px reserved at bottom for a status bar
        "desaturate": bool(cfg.get("desaturate", False)),  # grayscale the raster map
    }
