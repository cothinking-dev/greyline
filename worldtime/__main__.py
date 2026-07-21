"""CLI: render the World Time wallpaper for each output and apply it.

Runs ONCE and exits — a systemd user timer (or any scheduler) invokes it each
minute. With --out it just writes a PNG (no display backend needed), which is how
the standalone render is tested.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from . import __version__, backends, config, render


def _resolve_font(family, bold=False):
    """Resolve a font family to a file path via fontconfig, or None."""
    if not shutil.which("fc-match"):
        return None
    query = f"{family}:bold" if bold else family
    out = subprocess.run(
        ["fc-match", "-f", "%{file}", query], capture_output=True, text=True
    )
    return out.stdout.strip() or None


def _runtime_dir():
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    d = os.path.join(base, "greyline")
    os.makedirs(d, exist_ok=True)
    return d


def _parse_res(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main(argv=None):
    p = argparse.ArgumentParser(prog="greyline")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    p.add_argument("--config", help="path to config.toml (default: XDG location)")
    p.add_argument("--backend", help="override backend: sway|swww|hyprpaper|x11")
    p.add_argument("--out", help="write a single PNG here instead of applying")
    p.add_argument("--res", help="force resolution WxH (for --out)")
    p.add_argument("--font-family", default="Aporetic Sans",
                   help="label font family (resolved via fontconfig)")
    p.add_argument("--list-outputs", action="store_true",
                   help="print detected outputs and exit")
    args = p.parse_args(argv)

    cfg = config.load(args.config)
    rkw = config.render_kwargs(cfg)
    cities = cfg.get("city", [])

    font = _resolve_font(args.font_family)
    font_bold = _resolve_font(args.font_family, bold=True)

    # Single-image mode (testing / non-backend use).
    if args.out:
        res = _parse_res(args.res) if args.res else (1920, 1200)
        img = render.render(cities, out_size=res, font_path=font,
                            font_bold_path=font_bold, **rkw)
        img.save(args.out)
        print(f"wrote {args.out} {img.size}")
        return 0

    backend_name = args.backend or cfg.get("backend", "auto")
    try:
        name, mod = backends.resolve(backend_name)
    except RuntimeError as e:  # no compositor/backend detected — report cleanly, no traceback
        print(e, file=sys.stderr)
        return 1
    outs = mod.outputs()
    if args.list_outputs:
        print(f"backend: {name}")
        for o in outs:
            print(f"  {o['name']}: {o['width']}x{o['height']} scale={o['scale']}")
        return 0
    if not outs:
        print("no active outputs", file=sys.stderr)
        return 1

    rt = _runtime_dir()
    failures = 0
    for o in outs:
        # Render + apply each output independently: a single failing monitor
        # (e.g. unplugged mid-run) must not blank the others.
        try:
            img = render.render(cities, out_size=(o["width"], o["height"]),
                                font_path=font, font_bold_path=font_bold, **rkw)
            path = os.path.join(rt, f"{o['name']}.png")
            img.save(path)
            mod.apply(o["name"], path)
        except Exception as e:  # noqa: BLE001 — keep going for the remaining outputs
            failures += 1
            print(f"output {o['name']}: {e}", file=sys.stderr)
    return 1 if failures == len(outs) else 0


if __name__ == "__main__":
    sys.exit(main())
