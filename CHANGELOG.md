# Changelog

All notable changes to greyline are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.3] — 2026-07-23

### Fixed
- **KDE Plasma wallpaper now refreshes on every tick (`command` backend).** Plasma caches
  the wallpaper by path, so greyline's fixed filename never repainted. The command backend
  now ping-pongs two buffers (`screen-a.png`/`screen-b.png`) so each update hands Plasma a
  new path — capped at two files, no cache or junk-file growth. Native backends keep the
  single stable filename. (#11)
- **systemd timer fires within ~1s of the minute.** Added `AccuracySec=1s` so the clock
  updates on time instead of drifting up to ~50s from systemd's default timer coalescing.
  A single per-minute timer at 1s accuracy has negligible power cost. (#12)

### Added
- **Principles (north star) section in the README** — universal compatibility, performance
  & battery life, and staying lightweight, as a checklist for future changes.

## [0.5.2] — 2026-07-22

### Added
- **Configurable label font via `font_family`.** Set the label font in `config.toml` (a
  fontconfig family name or a direct font-file path) instead of only via `--font-family`;
  the CLI flag still overrides the config for a single run. Unset falls back to the bundled
  Aporetic Sans, then system fonts.
- **`logo_max_height` config key.** Caps the corner logo's height to a fraction of the
  screen height (`0` = no cap), so tall/portrait custom logos no longer blow up at the
  fixed logo width. Aspect ratio is preserved.
- **Documented `font_scale`.** The existing text-size multiplier is now surfaced in the
  default config template (e.g. `font_scale = 1.25` for 25% larger labels).

## [0.5.1] — 2026-07-22

### Fixed
- **Windows: timezone lookups no longer fail with `ZoneInfoNotFoundError`.** Windows has no
  system IANA tz database, so stdlib `zoneinfo` couldn't resolve any timezone; greyline now
  depends on the `tzdata` PyPI package on Windows (Unix is unaffected — it ships tzdata
  system-wide). Caught by the new `windows-latest` CI matrix.
- **Windows: reading the GeoJSON map data and the config no longer crashes with
  `UnicodeDecodeError`.** File reads/writes now specify `encoding="utf-8"` instead of
  relying on the platform default (Windows defaults to cp1252, which choked on the UTF-8
  map/config data). Also caught by the `windows-latest` CI matrix.

## [0.5.0] — 2026-07-22

### Added
- **Beta, untested Windows and macOS support.** New `windows` (Win32 `SystemParametersInfoW`
  via stdlib `ctypes`) and `macos` (`osascript`, with per-tick filename rotation to defeat
  WindowServer's path cache) wallpaper backends, auto-detected and platform-gated so Linux is
  unaffected. Single combined desktop only; no native scheduler yet — wrap `greyline watch` in
  Task Scheduler / launchd (see README). Font resolution falls back to Pillow's system-font
  search off Linux. A `windows-latest`/`macos-latest` CI matrix runs the render smoke test and
  mocked backend tests, but the actual desktop-paint step remains unverified on real hardware.

## [0.4.2] — 2026-07-22

### Fixed
- **`greyline init` no longer picks the `x11` backend on GNOME/KDE/XFCE when `feh`/`xwallpaper`
  is installed.** Those desktops draw their own wallpaper, so the X11 root-window image is
  silently overpainted by the compositor. `init` now prefers the desktop's own wallpaper
  command (`gsettings`/`plasma-apply-wallpaperimage`/`xfconf-query`) over the generic `x11`
  fallback; real wlroots compositors (sway/swww/hyprpaper) are unaffected.

## [0.4.1] — 2026-07-22

### Fixed
- **`config set home.color`/`logo_color` no longer breaks rendering.** An all-digit hex like
  `990000` was coerced to the integer `990000` and crashed the renderer (in the normal apply
  path the error was swallowed, so the wallpaper silently stopped updating); `000000` (black)
  was silently dropped. Colour keys now stay strings, `#rgb` shorthand is accepted, and an
  invalid colour is rejected up front with a clear message.
- **`config unset` on a dotted path that runs into a scalar** (e.g. `logo.foo` when `logo` is a
  bool) no longer raises `TypeError`; it reports the key as not set.
- **A malformed `--res`** (e.g. `1920`, `1920xABC`) now prints a clean error instead of an
  uncaught traceback.

## [0.4.0] — 2026-07-22

### Added
- **`logo_scale`** config option — size the corner logo up or down (e.g. `0.5` for half).
  Square logos like the default Tux read large at the default size; `logo_scale` tames them.

### Changed
- Refreshed the README screenshots (smaller, tasteful logo) and reorganised the README with a
  table of contents, a **Requirements** section, and a "How it works" diagram.

## [0.3.0] — 2026-07-22

### Added
- **Setup + configuration CLI** — no more hand-editing TOML or copying systemd units:
  - `greyline init` — detect the desktop, write a starter config, auto-pick the backend
    (filling in the GNOME/KDE/XFCE `command` recipe), and enable the systemd user timer where
    available. `--dry-run` to preview.
  - `greyline config get|set|unset` and `greyline city list|add|remove` — edit
    `~/.config/greyline/config.toml` from the CLI, preserving comments, with validation.
  - `greyline watch [--interval SEC]` — a foreground render loop for any init system / WM
    (no systemd required; add it to your session autostart).
  - `greyline enable|disable|status` — manage the systemd user timer.
  - `greyline doctor` — report session, detected backend + outputs, and timer status.
- systemd units are now generated by the CLI (`greyline enable`/`init`); the files under
  `systemd/` remain for manual installs.

### Changed
- New dependency: **`tomlkit`** (for comment-preserving config edits). greyline now needs
  Pillow + tomlkit.

## [0.2.0] — 2026-07-22

### Added
- **Generic `command` backend** for desktops without a native backend — GNOME, KDE Plasma,
  XFCE, and anything else with a CLI wallpaper-setter. greyline renders a PNG and runs a
  user-supplied shell command with `{path}` (the PNG) and `{output}` (the output name)
  substituted. Configure with `backend = "command"` + `command = "..."` (and optional
  `resolution = "WxH"`), or `--backend command --command '...'`. It **replaces** the desktop
  wallpaper (it is not an overlay). Opt-in only — not part of backend auto-detection.
- README "Desktop environments" section with copy-paste GNOME/KDE/XFCE recipes (flagged
  best-effort / community-verified).
- GitHub issue templates, including a structured **desktop-compatibility report** to help
  verify and fix the DE recipes.

### Changed
- Factored xrandr output enumeration out of the `x11` backend into a shared
  `backends/_util.py` helper (reused by the new `command` backend).

## [0.1.0] — 2026-07-21

### Added
- Initial public release; published to [PyPI](https://pypi.org/project/greyline/)
  (`pipx install greyline` / `uvx greyline`).
- Live world-time wallpaper: vector world map (Natural Earth), multi-timezone clocks with
  accurate DST via `zoneinfo`, an analytic day/night terminator with twilight bands, and an
  accented home city.
- Backends: `sway`, `swww`, `hyprpaper`, `x11` (feh/xwallpaper), auto-detected.
- Nix flake + home-manager module; systemd user timer for once-a-minute rendering.

[0.4.1]: https://github.com/cothinking-dev/greyline/releases/tag/v0.4.1
[0.4.0]: https://github.com/cothinking-dev/greyline/releases/tag/v0.4.0
[0.3.0]: https://github.com/cothinking-dev/greyline/releases/tag/v0.3.0
[0.2.0]: https://github.com/cothinking-dev/greyline/releases/tag/v0.2.0
[0.1.0]: https://github.com/cothinking-dev/greyline/releases/tag/v0.1.0
