"""hyprpaper backend (Hyprland) — preload + set per monitor via hyprctl."""
import json
import os
import shutil
import subprocess


def available():
    return (
        bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))
        and shutil.which("hyprctl") is not None
    )


def outputs():
    raw = subprocess.run(
        ["hyprctl", "monitors", "-j"], capture_output=True, text=True, check=True
    ).stdout
    result = []
    for m in json.loads(raw):
        scale = float(m.get("scale", 1.0) or 1.0)
        result.append({
            "name": m["name"],
            "width": int(m["width"]),
            "height": int(m["height"]),
            "scale": scale,
        })
    return result


def apply(name, png_path):
    # These commands are deprecated.
    # Check https://wiki.hypr.land/Hypr-Ecosystem/hyprpaper/#ipc

    # Preload the new image, then bind it; unload others to avoid leaking memory.
    # subprocess.run(["hyprctl", "hyprpaper", "preload", png_path],
    #                capture_output=True, text=True, check=True)
    
    subprocess.run(["hyprctl", "hyprpaper", "wallpaper", f"{name},{png_path},cover"],
                   capture_output=True, text=True, check=True)

    # subprocess.run(["hyprctl", "hyprpaper", "unload", "unused"],
    #                capture_output=True, text=True)
