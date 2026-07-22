"""CLI for greyline.

Bare `greyline` renders the wallpaper for each output and applies it, once, then
exits — a systemd user timer (or `greyline watch`) invokes it on a schedule. With
--out it just writes a PNG (no backend needed). Subcommands (init/config/city/
watch/enable/disable/status/doctor) manage setup and configuration.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from . import __version__, backends, config, recipes, render, service


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
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise SystemExit(f"invalid --res {s!r}; expected WxH, e.g. 2560x1440")


def run_apply(args):
    """Render every output and apply it (or write one PNG with --out). Reused by the
    bare invocation and by `watch`."""
    cfg = config.load(args.config)
    rkw = config.render_kwargs(cfg)
    cities = cfg.get("city", [])

    # Font family: CLI flag > config `font_family` > built-in default. Accept either a
    # fontconfig family name or a direct font-file path (fc-match treats its arg as a
    # family pattern, so a bare path would resolve wrong — route paths straight to Pillow).
    family = args.font_family or cfg.get("font_family") or "Aporetic Sans"
    if os.path.isfile(family):
        font = font_bold = family
    else:
        font = _resolve_font(family) or family
        font_bold = _resolve_font(family, bold=True) or family

    # Single-image mode (testing / non-backend use).
    if args.out:
        res = _parse_res(args.res) if args.res else (1920, 1200)
        img = render.render(cities, out_size=res, font_path=font,
                            font_bold_path=font_bold, **rkw)
        img.save(args.out)
        print(f"wrote {args.out} {img.size}")
        return 0

    backend_name = args.backend or cfg.get("backend", "auto")
    if backend_name == "command":
        # The command backend reads its template + size from the environment
        # (keeps the backend contract's apply(name, path) signature unchanged).
        command = args.command or cfg.get("command")
        if not command:
            print("backend 'command' requires a command "
                  "(set `command` in config or pass --command)", file=sys.stderr)
            return 1
        os.environ["GREYLINE_COMMAND"] = command
        resolution = args.res or cfg.get("resolution")
        if resolution:
            os.environ["GREYLINE_RESOLUTION"] = resolution
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


# --- subcommands ---

def cmd_init(args):
    """Detect the desktop, write a starter config + backend, and schedule updates."""
    cfg_path = args.config or config.user_config_path()
    exists = os.path.isfile(cfg_path)

    detected = backends.detect()
    deskey = recipes.detect_desktop()
    # A full desktop environment (GNOME/KDE/XFCE) paints its own wallpaper, so the
    # generic x11 root-window backend is silently overpainted there even when feh/
    # xwallpaper happens to be installed. Prefer the DE's own wallpaper command over
    # the x11 fallback. Real wlroots compositors (sway/swww/hyprpaper) still win —
    # their sessions carry no gnome/kde/xfce token in $XDG_CURRENT_DESKTOP.
    if detected and not (detected == "x11" and deskey):
        backend, command = detected, None
        backend_line = f"backend = {detected}  (detected)"
    elif deskey:
        backend, command = "command", recipes.RECIPES[deskey]
        backend_line = f"backend = command  ({deskey} recipe)"
    else:
        backend, command = None, None
        backend_line = "backend = (none detected — set one manually)"

    use_systemd = service.systemd_user_available()

    if args.dry_run:
        print("greyline init --dry-run — would:")
        print(f"  {'keep' if exists else 'create'} {cfg_path}")
        print(f"  set {backend_line}")
        if command:
            print(f"  set command = {command}")
        if use_systemd:
            for a in service.install_and_enable(interval=args.interval, dry_run=True):
                print(f"  {a}")
        else:
            print(f"  (no systemd --user) autostart: {service.greyline_bin()} watch")
        return 0

    from . import configedit
    path = configedit.ensure_config(cfg_path)
    if backend:
        configedit.set_key(path, "backend", backend)
    if command:
        configedit.set_key(path, "command", command)

    print(f"{'kept' if exists else 'wrote'} config: {path}")
    print(f"  {backend_line}")
    if use_systemd:
        service.install_and_enable(interval=args.interval)
        print("  scheduled: systemd user timer 'greyline.timer' (enabled + started)")
    else:
        print("  no systemd --user — add this to your session/WM autostart:")
        print(f"    {service.greyline_bin()} watch")
    if not backend:
        print("  ! no wallpaper backend detected — set one with: "
              "greyline config set backend <name>")
        print("    GNOME/KDE/XFCE: see the README 'Desktop environments' section.")
    print("Next: pick your cities with `greyline city add …`; check with `greyline doctor`.")
    return 0


def cmd_watch(args):
    """Render+apply in a foreground loop — works on any init system / WM."""
    import time
    print(f"greyline watch: rendering every {args.interval}s (Ctrl-C to stop)",
          file=sys.stderr)
    try:
        while True:
            run_apply(args)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\ngreyline watch: stopped", file=sys.stderr)
    return 0


def cmd_config(args):
    path = args.config or config.user_config_path()
    if args.config_cmd == "get":
        from . import configedit
        if args.key:
            val = configedit.get_key(path, args.key)
            if val is None:
                print(f"{args.key}: (unset)", file=sys.stderr)
                return 1
            print(val)
        elif os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                sys.stdout.write(f.read())
        else:
            print(f"no config at {path} (run `greyline init`)", file=sys.stderr)
            return 1
        return 0

    from . import configedit
    path = configedit.ensure_config(path)
    if args.config_cmd == "set":
        try:
            val = configedit.set_key(path, args.key, args.value)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"{args.key} = {val!r}")
    elif args.config_cmd == "unset":
        removed = configedit.unset_key(path, args.key)
        print(f"{args.key}: {'removed' if removed else 'not set'}")
    return 0


def cmd_city(args):
    from . import configedit
    path = args.config or config.user_config_path()
    if args.city_cmd == "list":
        cities = configedit.list_cities(path)
        if not cities:
            print("no cities configured")
            return 0
        for c in cities:
            home = "  (home)" if c.get("home") else ""
            print(f"  {c['name']:<20} {c.get('tz','')}{home}")
        return 0

    path = configedit.ensure_config(path)
    if args.city_cmd == "add":
        try:
            configedit.add_city(path, args.name, args.lat, args.lon, args.tz,
                                home=args.home, label_side=args.label_side)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"added {args.name} ({args.tz})" + ("  [home]" if args.home else ""))
    elif args.city_cmd == "remove":
        n = configedit.remove_city(path, args.name)
        print(f"removed {n} matching {args.name!r}" if n else f"no city named {args.name!r}")
    return 0


def cmd_enable(args):
    if not service.systemd_user_available():
        print("systemd --user not available; use `greyline watch` in your autostart "
              "instead.", file=sys.stderr)
        return 1
    service.install_and_enable(interval=args.interval)
    print("enabled greyline.timer (systemd user)")
    return 0


def cmd_disable(args):
    if not service.systemd_user_available():
        print("systemd --user not available.", file=sys.stderr)
        return 1
    service.disable()
    print("disabled greyline.timer")
    return 0


def cmd_status(args):
    if not service.systemd_user_available():
        print("systemd --user not available; greyline is not scheduled via systemd.")
        return 0
    service.status()
    return 0


def cmd_doctor(args):
    print(f"session: XDG_CURRENT_DESKTOP={os.environ.get('XDG_CURRENT_DESKTOP', '')!r} "
          f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '')!r}")
    cfg = config.load(args.config)
    backend_name = args.backend or cfg.get("backend", "auto")
    if backend_name == "command" and (args.command or cfg.get("command")):
        os.environ["GREYLINE_COMMAND"] = args.command or cfg.get("command")
    try:
        name, mod = backends.resolve(backend_name)
        print(f"backend: {name}")
        for o in mod.outputs():
            print(f"  {o['name']}: {o['width']}x{o['height']} scale={o['scale']}")
    except RuntimeError as e:
        print(f"backend: ERROR — {e}")
    print("systemd --user: " +
          ("available" if service.systemd_user_available()
           else "not available (use `greyline watch`)"))
    return 0


def build_parser():
    # Render/apply flags: real defaults on the main parser (for the bare invocation),
    # and a SUPPRESS-default copy (render_opts) added to the render-running subcommands
    # (watch/doctor) so both `greyline watch --backend X` and `greyline --backend X
    # watch` work. Sharing via SUPPRESS-only on the subparsers avoids argparse's
    # parent/subparser default-clobber (a subcommand flag omits itself unless given).
    render_opts = argparse.ArgumentParser(add_help=False)
    render_opts.add_argument("--config", default=argparse.SUPPRESS)
    render_opts.add_argument("--backend", default=argparse.SUPPRESS)
    render_opts.add_argument("--command", default=argparse.SUPPRESS)
    render_opts.add_argument("--res", default=argparse.SUPPRESS)
    render_opts.add_argument("--font-family", default=argparse.SUPPRESS)

    p = argparse.ArgumentParser(prog="greyline")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", default=None,
                   help="path to config.toml (default: XDG location)")
    p.add_argument("--backend", default=None,
                   help="override backend: sway|swww|hyprpaper|x11|windows|macos|command")
    p.add_argument("--command", default=None,
                   help="for --backend command: shell command run per output with "
                        "{path} (and {output}) substituted")
    p.add_argument("--out", default=None,
                   help="write a single PNG here instead of applying")
    p.add_argument("--res", default=None, help="force resolution WxH (for --out)")
    p.add_argument("--font-family", default=None,
                   help="label font family or font-file path (overrides config "
                        "`font_family`; resolved via fontconfig)")
    p.add_argument("--list-outputs", action="store_true",
                   help="print detected outputs and exit")

    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("init", help="detect desktop, write config, schedule updates")
    sp.add_argument("--interval", default="*:*:00",
                    help="systemd OnCalendar expression (default: each minute)")
    sp.add_argument("--dry-run", action="store_true",
                    help="print what would happen; change nothing")

    sp = sub.add_parser("watch", parents=[render_opts],
                        help="render+apply in a loop (any init system / WM)")
    sp.add_argument("--interval", type=int, default=60,
                    help="seconds between renders (default: 60)")

    cp = sub.add_parser("config", help="get/set/unset config keys")
    cs = cp.add_subparsers(dest="config_cmd", required=True)
    g = cs.add_parser("get", help="print a dotted key, or the whole config")
    g.add_argument("key", nargs="?")
    s = cs.add_parser("set", help="set a dotted key, e.g. twilight.darkness medium")
    s.add_argument("key")
    s.add_argument("value")
    u = cs.add_parser("unset", help="remove a key (revert to default)")
    u.add_argument("key")

    cip = sub.add_parser("city", help="list/add/remove cities")
    ci = cip.add_subparsers(dest="city_cmd", required=True)
    ci.add_parser("list", help="list configured cities")
    a = ci.add_parser("add", help="add a city")
    a.add_argument("name")
    a.add_argument("lat", type=float)
    a.add_argument("lon", type=float)
    a.add_argument("tz")
    a.add_argument("--home", action="store_true", help="make this the home city")
    a.add_argument("--label-side", choices=["left", "right", "above", "below"])
    rm = ci.add_parser("remove", help="remove a city by name")
    rm.add_argument("name")

    ep = sub.add_parser("enable", help="install + enable the systemd user timer")
    ep.add_argument("--interval", default="*:*:00")
    sub.add_parser("disable", help="disable the systemd user timer")
    sub.add_parser("status", help="show the timer status")
    sub.add_parser("doctor", parents=[render_opts],
                   help="diagnose backend / session / timer")
    return p


_DISPATCH = {
    "init": cmd_init, "watch": cmd_watch, "config": cmd_config, "city": cmd_city,
    "enable": cmd_enable, "disable": cmd_disable, "status": cmd_status,
    "doctor": cmd_doctor,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    handler = _DISPATCH.get(getattr(args, "cmd", None))
    if handler:
        return handler(args)
    return run_apply(args)  # bare invocation / --out / --list-outputs


if __name__ == "__main__":
    sys.exit(main())
