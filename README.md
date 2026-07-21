# greyline

[![CI](https://github.com/cothinking-dev/greyline/actions/workflows/ci.yml/badge.svg)](https://github.com/cothinking-dev/greyline/actions/workflows/ci.yml)
[![License: GPL v2+](https://img.shields.io/badge/License-GPLv2%2B-blue.svg)](LICENSE)

A live world-time desktop wallpaper for Wayland/X11 — a world map with clocks for
your cities, your home city highlighted, and a day/night terminator that tracks the
sun. A modern recreation of the classic IBM/ThinkPad **"World Time"** Active Desktop.

*(greyline = the ham-radio term for the day/night terminator.)*

![greyline — dark theme](docs/screenshots/hero.png)

<sub>Shown with the optional ThinkPad wordmark (a user-supplied logo — see [Licensing](#licensing--credits)). The bundled default logo is Tux.</sub>

It doesn't run a browser or a background daemon. A small Python program renders a PNG
once a minute and hands it to your existing wallpaper mechanism, then exits — so it's
effectively free on battery.

```
systemd timer (*:*:00) ─▶ greyline (renders in well under a second, then exits)
      render per output (Pillow): map + clocks + terminator
      └─▶ set wallpaper via the detected backend (sway/swww/hyprpaper/gnome/feh)
```

## Features

- **Multi-timezone clocks** at each city's real location, with **accurate DST** via the
  OS IANA database (`zoneinfo`). 12h or 24h.
- **Home city** accented (dot + bold label + optional timezone-column highlight),
  auto-detected from your system timezone or pinned in config.
- **Analytic day/night terminator**, seasonally correct, with discrete civil / nautical /
  astronomical **twilight bands**.
- **Vector map** drawn from public-domain **Natural Earth** data — crisp at any
  resolution, fully themeable (`dark`, `blue`, or custom), with honest zig-zag timezone
  boundaries, a green GMT column, and a red International Date Line.
- **Any resolution / multi-monitor / HiDPI** — each output rendered at native pixels
  (GNOME uses one shared virtual-desktop image).
- **Swappable corner logo** — ships with Tux; point `logo_path` at your own PNG.
- **Pluggable backends**, auto-detected: `sway`, `swww`, `hyprpaper`, `gnome`, `x11` (feh/xwallpaper).

| `blue` theme + Tux | minimal (no logo, 12h) |
|---|---|
| ![blue theme](docs/screenshots/blue.png) | ![minimal](docs/screenshots/minimal.png) |

## Install

### Nix (flake + home-manager) — recommended

```nix
# flake.nix
inputs.greyline.url = "github:cothinking-dev/greyline";

# home-manager
imports = [ inputs.greyline.homeManagerModules.default ];

services.greyline = {
  enable = true;
  backend = "sway";              # or "auto" / "swww" / "hyprpaper" / "gnome" / "x11"
  fontFamily = "Aporetic Sans";  # resolved via fontconfig
  settings = {
    theme = "dark";
    format = "24h";
    twilight = { bands = true; darkness = "subtle"; };
    home = { tz = "auto"; column_highlight = true; };  # "auto" = system tz
    city = [
      { name = "Kuala Lumpur"; lat = 3.14;  lon = 101.69; tz = "Asia/Kuala_Lumpur"; }
      { name = "London";       lat = 51.51; lon = -0.13;  tz = "Europe/London"; }
      { name = "New York";     lat = 40.71; lon = -74.01; tz = "America/New_York"; }
      { name = "Tokyo";        lat = 35.68; lon = 139.69; tz = "Asia/Tokyo"; }
    ];
  };
};
```

For GNOME, set `backend = "gnome"`. It updates both the light and dark GNOME
background settings through `gsettings`; GNOME scales its one shared 1920×1080
image rather than exposing native per-monitor sizes.

Try it without installing:

```sh
nix run github:cothinking-dev/greyline -- --out wt.png --res 2560x1440   # writes a PNG
```

### pipx (other distros)

```sh
pipx install git+https://github.com/cothinking-dev/greyline   # dep: Pillow only
mkdir -p ~/.config/greyline
# edit ~/.config/greyline/config.toml (copy worldtime/default-config.toml)

# pip doesn't ship the systemd user units — grab them from the repo:
git clone https://github.com/cothinking-dev/greyline
install -Dm644 greyline/systemd/greyline.{service,timer} -t ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now greyline.timer
```

## Configuration

Non-Nix users edit `~/.config/greyline/config.toml`; the shipped
[`worldtime/default-config.toml`](worldtime/default-config.toml) is the documented
template. Keys: `backend`, `map_style` (`vector`/`raster`), `theme` (`dark`/`blue`),
`format` (`24h`/`12h`), `logo` / `logo_path` / `logo_invert`, `[twilight] bands/darkness`,
`[home] tz/column_highlight/color`, and a `[[city]]` list (`name`, `lat`, `lon`, `tz`,
optional `label_side`).

## CLI

```
greyline                 # render all outputs and apply (what the timer runs)
greyline --list-outputs  # show detected backend + outputs
greyline --out wt.png --res 1920x1200   # render a PNG, no backend needed
greyline --backend gnome # force a backend
```

## How it works

- `geo.py` / `vectormap.py` — lon/lat → pixel projection; the vector map is drawn from
  Natural Earth GeoJSON (supersampled for smooth coastlines).
- `sun.py` — subsolar point + terminator/twilight boundary latitudes.
- `render.py` — composites map + overlays, then draws clocks at native resolution with
  smart label placement (labels pick a side to avoid overlapping each other and the edges).
- `backends/` — the only platform-specific code; everything else is portable.

## Licensing & credits

Code is **GPL-2.0-or-later**. It descends from Maxim Proskurnya's GPL "World Time
Wallpaper" tribute; the concept and original artwork are © IBM/Lenovo.

The default **vector** map uses public-domain **Natural Earth** data, and the default
logo is **Tux** (Larry Ewing / GIMP) — both cleanly redistributable. The original
IBM/Lenovo ThinkPad raster art and wordmark are **not** bundled; `map_style = "raster"`
and the ThinkPad logo require you to supply those files yourself (see
[`NOTICE`](NOTICE) and [`docs/CREDITS.md`](docs/CREDITS.md)).

> Built with the assistance of AI coding tools.
