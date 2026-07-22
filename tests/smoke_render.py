"""Headless render smoke test — proves the pure-Pillow core runs on any OS.

Renders the shipped default cities with ``font_path=None`` (the state of a bare
Windows/macOS box with no fontconfig) and asserts a non-empty PNG comes out. Run
directly (``python tests/smoke_render.py``); used by the cross-platform CI matrix.
Exits non-zero on failure.
"""
import os
import sys
import tempfile
import tomllib

from worldtime import config, render


def main():
    with open(config.DEFAULT_CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    cities = cfg.get("city", [])
    im = render.render(cities, out_size=(1280, 720), font_path=None, font_bold_path=None)
    out = os.path.join(tempfile.gettempdir(), "greyline-smoke.png")
    im.save(out)
    size = os.path.getsize(out)
    print(f"rendered {im.size} -> {out} ({size} bytes)")
    if size <= 0:
        print("FAIL: empty PNG", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
