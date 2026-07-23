"""Command-backend recipes for desktops without a native backend.

Single source of truth for the GNOME/KDE/XFCE wallpaper commands `greyline init`
writes and the README documents. Each is a shell command run by the `command`
backend with {path} (the rendered PNG) substituted. Best-effort / community-verified
— the maintainers run sway and can't test these directly (see the desktop-compat
issue template).
"""

# Keyed by the lowercased token we match in $XDG_CURRENT_DESKTOP.
RECIPES = {
    # Empty-then-set defeats GNOME's "same URI => no refresh" cache; set both the
    # light and dark keys so it works whichever colour scheme is active.
    "gnome": (
        'gsettings set org.gnome.desktop.background picture-uri "" && '
        'gsettings set org.gnome.desktop.background picture-uri "file://{path}" && '
        'gsettings set org.gnome.desktop.background picture-uri-dark "file://{path}"'
    ),
    # Plasma caches the wallpaper by path and won't refresh on an unchanged filename;
    # greyline ping-pongs two buffers (see _output_path) so {path} differs each tick.
    "kde": "plasma-apply-wallpaperimage {path}",
    # The monitor segment varies by XFCE version/output name; monitor0 is the common
    # default. Users can find theirs with: xfconf-query -c xfce4-desktop -l | grep last-image
    "xfce": (
        "xfconf-query -c xfce4-desktop "
        "-p /backdrop/screen0/monitor0/workspace0/last-image -s {path}"
    ),
}


def detect_desktop(environ=None):
    """Return a RECIPES key matching $XDG_CURRENT_DESKTOP (gnome/kde/xfce), or None.

    $XDG_CURRENT_DESKTOP can be colon-separated and vary in case (e.g. "ubuntu:GNOME",
    "KDE", "X-Cinnamon"), so match each token case-insensitively.
    """
    import os
    env = environ if environ is not None else os.environ
    tokens = env.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    for key in RECIPES:
        if key in tokens:
            return key
    return None
