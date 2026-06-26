"""Compose the World Time wallpaper image (PORTABLE CORE; deps: Pillow).

Pipeline (see plan): work in the map's 1400x1050 calibration frame for the smooth
day/night + twilight overlays and the home timezone-column highlight; cover-crop the
composited map to the target output size; then draw the city clocks at NATIVE output
resolution so text stays crisp on HiDPI panels.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from . import geo, sun, vectormap

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
BASE_1400 = os.path.join(ASSET_DIR, "world.time.1400x1050.png")
LOGO_PNG = os.path.join(ASSET_DIR, "thinkpad_logo.png")

# Twilight boundaries (solar elevation, degrees): terminator + civil/nautical/astro.
# Each is filled as a night-side polygon; stacking translucent layers darkens the
# deeper-night regions progressively.
TWILIGHT_ELEVATIONS = (0.0, -6.0, -12.0, -18.0)

# Per-layer overlay alpha by darkness preset (4 stacked layers at full night).
DARKNESS_ALPHA = {"subtle": 28, "medium": 40, "dramatic": 55}

THEMES = {
    "thinkpad-blue": {
        "night": (6, 12, 34),          # deep navy overlay (faithful to the blue map)
        "text": (226, 232, 255),
        "text_stroke": (4, 8, 26, 220),
        "dot": (210, 220, 255),
        "dot_outline": (4, 8, 26, 200),
        "home": (255, 70, 70),         # accent: home dot + label
        "home_stroke": (40, 0, 0, 220),
        "column": (255, 255, 255, 26),  # home timezone-column highlight
        # Vector-map palette (Phase B): ocean / land / borders / timezone grid.
        "ocean": (61, 97, 210),         # #3d61d2 — the ThinkPad blue
        "land": (42, 71, 160),
        "border": (120, 150, 230),
        "grid": (255, 255, 255, 38),
        "grid_label": (200, 210, 255),
        "day_wash": (255, 255, 255, 10),  # per-band day-side brighten (stacked x4)
    },
    # Dark variant (Modus-Vivendi-flavoured) — intended for the vector map (Phase B).
    "dark": {
        "night": (2, 4, 8),
        "text": (220, 224, 235),
        "text_stroke": (0, 0, 0, 220),
        "dot": (170, 185, 220),
        "dot_outline": (0, 0, 0, 210),
        "home": (255, 209, 64),
        "home_stroke": (30, 24, 0, 220),
        "column": (255, 255, 255, 20),
        "ocean": (11, 14, 20),          # #0b0e14
        "land": (30, 34, 43),
        "border": (74, 82, 100),
        "grid": (255, 255, 255, 16),
        "grid_label": (130, 138, 158),
        "day_wash": (140, 165, 220, 18),  # per-band day-side brighten (stacked x4)
        "night_alpha": 12,                # gentle night darkening → low contrast, brighter darks
        "logo_invert": True,              # recolour the dark wordmark to light on this theme
        "logo": (224, 228, 238),
    },
}

# Font candidates (Aporetic preferred per the repo; DejaVu as the portable fallback).
FONT_CANDIDATES = [
    "Aporetic Sans", "AporeticSans", "Aporetic-Sans",
    "DejaVuSans.ttf", "DejaVu Sans",
]
FONT_BOLD_CANDIDATES = [
    "Aporetic Sans Bold", "AporeticSans-Bold",
    "DejaVuSans-Bold.ttf", "DejaVu Sans Bold",
]


def _hex(s):
    """Parse '#rrggbb' (or 'rrggbb') to an (r, g, b) tuple; None passes through."""
    if not s:
        return None
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _load_font(size, candidates, explicit=None):
    for name in ([explicit] if explicit else []) + candidates:
        if not name:
            continue
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size)


class Projection:
    """Maps geographic lon/lat to OUTPUT pixel coordinates (and back, for x and lat).

    `scale` is a sizing factor (relative to the 1400-wide reference) for fonts/dots so
    both map styles look consistent.
    """

    def __init__(self, to_px, x_to_lon, lat_to_y, scale):
        self.to_px = to_px
        self.x_to_lon = x_to_lon
        self.lat_to_y = lat_to_y
        self.scale = scale


def _cover_transform(ref_w, ref_h, out_w, out_h, anchor):
    """Scale + crop offsets mapping the ref frame onto the output (cover)."""
    scale = max(out_w / ref_w, out_h / ref_h)
    crop_x = (ref_w * scale - out_w) * anchor[0]
    crop_y = (ref_h * scale - out_h) * anchor[1]
    return scale, crop_x, crop_y


def _raster_projection(out_w, out_h, anchor):
    """Phase-A projection: the calibrated 1400x1050 affine, then cover-crop to output."""
    sc, cx, cy = _cover_transform(geo.REF_W, geo.REF_H, out_w, out_h, anchor)

    def to_px(lon, lat):
        rx, ry = geo.lonlat_to_px(lon, lat)
        return rx * sc - cx, ry * sc - cy

    proj = Projection(
        to_px,
        x_to_lon=lambda x: geo.x_to_lon((x + cx) / sc),
        lat_to_y=lambda lat: geo.lat_to_y(lat) * sc - cy,
        scale=sc,
    )
    return proj, (sc, cx, cy)


CENTER_LAT = 12.0  # vertical centre of the vector map (the land midpoint, Antarctica dropped)


def _equirect_projection(out_w, out_h):
    """Undistorted (1:1 deg/px) equirectangular, full longitude, centred on CENTER_LAT.

    Longitude fills the width; latitude keeps the same px-per-degree so continents are
    not stretched. Centring on the land midpoint (not the equator) balances the seamless
    ocean margins top/bottom now that Antarctica is dropped.
    """
    ppd = out_w / 360.0
    y0 = out_h / 2.0 - (90.0 - CENTER_LAT) * ppd
    return Projection(
        to_px=lambda lon, lat: ((lon + 180.0) * ppd, (90.0 - lat) * ppd + y0),
        x_to_lon=lambda x: x / ppd - 180.0,
        lat_to_y=lambda lat: (90.0 - lat) * ppd + y0,
        scale=out_w / geo.REF_W,
    )


def _terminator_polygon(elevation, sublat, sublon, proj, w, h, step=3, day_side=False):
    """Polygon (output px) for the region darker than `elevation` (or the lit side)."""
    pts = []
    x = 0
    while x <= w:
        lat = sun.boundary_lat(proj.x_to_lon(x), sublat, sublon, elevation)
        pts.append((x, max(0.0, min(float(h), proj.lat_to_y(lat)))))
        x += step
    close_bottom = sun.night_is_south(sublat) != day_side
    pts += [(w, h), (0, h)] if close_bottom else [(w, 0), (0, 0)]
    return pts


def _overlay_night(base, dt, theme, bands, alpha, proj):
    """Composite the day/night terminator with stepped twilight bands.

    Two stacks share the civil/nautical/astronomical elevations, so each twilight band
    is a distinct step:
      - day-side LIGHT washes (brighten toward the sun) — the only thing visible on a
        near-black map, and what makes the bands apparent;
      - night-side DARK washes (deepen toward midnight) — gentle, to keep contrast low.
    """
    w, h = base.size
    sublat, sublon = sun.subsolar_point(dt)
    elevations = TWILIGHT_ELEVATIONS if bands else (0.0,)

    def stack(day_side, fill):
        nonlocal base
        for elev in elevations:
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(layer).polygon(
                _terminator_polygon(elev, sublat, sublon, proj, w, h, day_side=day_side),
                fill=fill,
            )
            base = Image.alpha_composite(base, layer)

    if theme.get("day_wash"):
        stack(day_side=True, fill=tuple(theme["day_wash"]))
    if alpha > 0 and theme.get("night"):
        stack(day_side=False, fill=tuple(theme["night"]) + (alpha,))
    return base


def _recolor_dark(img, light_rgb, thresh=70):
    """Recolour near-black pixels (the wordmark text) to `light_rgb`, keeping coloured
    parts (the IBM bars) intact — so the logo reads on a dark background."""
    px = img.load()
    lr, lg, lb = light_rgb
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) < thresh:
                px[x, y] = (lr, lg, lb, a)
    return img


def _mono_logo(img, rgb):
    """Recolour the whole logo to a single colour (a flat silhouette), keeping its alpha
    (anti-aliased edges preserved). Used for an all-white logo, etc."""
    out = Image.new("RGBA", img.size, tuple(rgb) + (255,))
    out.putalpha(img.getchannel("A"))
    return out


def _draw_logo(canvas, theme, logo_path, bar_height=0, logo_color=None):
    """Composite the bottom-left logo image. Returns its bbox or None.

    `bar_height` reserves space at the bottom (e.g. for a status bar overlaying the
    wallpaper) so the logo sits above it. `logo_color` (hex) recolours the whole logo to
    a flat silhouette (e.g. all-white); otherwise a dark-theme `logo_invert` recolours
    just the wordmark to light while keeping the IBM colour bars.
    """
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except OSError:
        return None
    target_w = max(72, round(canvas.width * 0.104))  # ~13% width, scaled down 20%
    target_h = round(target_w * logo.height / logo.width)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    mono = _hex(logo_color)
    if mono:
        logo = _mono_logo(logo, mono)
    elif theme.get("logo_invert"):
        logo = _recolor_dark(logo, tuple(theme.get("logo", (235, 235, 235))))
    pad = round(canvas.width * 0.018)
    x, y = pad, canvas.height - target_h - pad - bar_height
    canvas.alpha_composite(logo, (x, y))
    return (x, y, x + target_w, y + target_h)




def _rect_overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _place_labels(items, obstacles, bounds, scale):
    """Assign each label a non-overlapping box around its dot (right/left/above/below).

    Greedy: home first (keeps the right-side preference), then left-to-right. Each label
    picks the candidate side with the least overlap against obstacles (dots, logo,
    screen edges) and already-placed labels.
    """
    gap = round(6 * scale)
    placed = list(obstacles)
    order = sorted(range(len(items)), key=lambda i: (not items[i]["is_home"], items[i]["px"]))
    for i in order:
        it = items[i]
        px, py, w, h, g = it["px"], it["py"], it["w"], it["h"], it["dotr"] + gap
        candidates = [
            (px + g, py - h / 2),       # right
            (px - g - w, py - h / 2),   # left
            (px - w / 2, py + g),       # below
            (px - w / 2, py - g - h),   # above
            (px + g, py + g),           # below-right
            (px - g - w, py + g),       # below-left
        ]
        best, best_pen = None, None
        for bx, by in candidates:
            box = (bx, by, bx + w, by + h)
            pen = sum(_rect_overlap(box, o) for o in placed)
            off = (max(0, bounds[0] - bx) + max(0, (bx + w) - bounds[2])
                   + max(0, bounds[1] - by) + max(0, (by + h) - bounds[3]))
            pen += off * (w + h) * 3  # heavily penalise going off-screen
            if best_pen is None or pen < best_pen:
                best, best_pen = box, pen
            if pen == 0:
                break
        it["box"] = best
        placed.append(best)


def _fmt_time(local, fmt):
    if fmt == "12h":
        h = local.hour % 12 or 12
        return f"{h}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    return f"{local.hour:02d}:{local.minute:02d}"


def _label_lines(city, dt, fmt):
    """City label: name + local time. Kept deliberately simple."""
    local = dt.astimezone(ZoneInfo(city["tz"]))
    return [city["name"], _fmt_time(local, fmt)]


def render(
    cities,
    *,
    dt=None,
    out_size=None,
    theme="thinkpad-blue",
    fmt="24h",
    twilight_bands=True,
    darkness="subtle",
    column_highlight=True,
    home_color=None,
    label_bg_alpha=130,
    map_style="raster",
    logo=True,
    logo_path=LOGO_PNG,
    logo_color=None,
    bar_height=0,
    desaturate=False,
    font_path=None,
    font_bold_path=None,
    font_scale=1.0,
    base_path=BASE_1400,
    crop_anchor=(0.5, 1.0),
):
    th = THEMES.get(theme, THEMES["thinkpad-blue"])
    dt = dt or datetime.now(timezone.utc)
    alpha = th.get("night_alpha", DARKNESS_ALPHA.get(darkness, DARKNESS_ALPHA["subtle"]))
    home_rgb = _hex(home_color) or tuple(th["home"])  # accent colour for the home city
    out_w, out_h = out_size or (geo.REF_W, geo.REF_H)

    # Build the map base + a projection (lon/lat -> output px) for the chosen style.
    if map_style == "vector":
        proj = _equirect_projection(out_w, out_h)
        scale = proj.scale
        grid_font = _load_font(max(8, round(11 * scale)), FONT_CANDIDATES, font_path)
        canvas = vectormap.build_base(
            out_w, out_h, th, grid_font, proj.to_px
        ).convert("RGBA")
    else:
        proj, (sc, cx, cy) = _raster_projection(out_w, out_h, crop_anchor)
        scale = sc
        base = Image.open(base_path).convert("RGBA")  # the 1400x1050 calibration frame
        if desaturate:  # grayscale the blue artwork → a black-and-white map,
            # then double the contrast so the desaturated land/ocean stay distinct.
            gray = ImageEnhance.Contrast(ImageOps.grayscale(base)).enhance(2.0)
            base = gray.convert("RGBA")
        scaled = base.resize((round(geo.REF_W * sc), round(geo.REF_H * sc)), Image.LANCZOS)
        canvas = scaled.crop((round(cx), round(cy), round(cx) + out_w, round(cy) + out_h))

    # Home timezone-column highlight (output space; width = one hour of longitude here).
    home = next((c for c in cities if c.get("home")), None)
    if column_highlight and home:
        hx, _hy = proj.to_px(home["lon"], home["lat"])
        x0, _ = proj.to_px(home["lon"] - 7.5, home["lat"])
        x1, _ = proj.to_px(home["lon"] + 7.5, home["lat"])
        col_w = abs(x1 - x0)
        band = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        ImageDraw.Draw(band).rectangle(
            [hx - col_w / 2, 0, hx + col_w / 2, out_h], fill=tuple(th["column"])
        )
        canvas = Image.alpha_composite(canvas, band)

    # Day/night + twilight overlay (output space, via the projection).
    canvas = _overlay_night(canvas, dt, th, twilight_bands, alpha, proj)

    # Logo first — its box becomes an obstacle so no label hides behind it.
    obstacles = []
    if logo:
        b = _draw_logo(canvas, th, logo_path, bar_height, logo_color)
        if b:
            obstacles.append(b)

    # Fonts for the clocks (crisp text, sizes scale with output + font_scale).
    fs = max(8, round(16 * scale * font_scale))
    fs_home = max(10, round(20 * scale * font_scale))
    font = _load_font(fs, FONT_CANDIDATES, font_path)
    font_home = _load_font(fs_home, FONT_BOLD_CANDIDATES, font_bold_path)
    draw = ImageDraw.Draw(canvas)

    # Size each label; collect for placement.
    items = []
    for c in cities:
        px, py = proj.to_px(c["lon"], c["lat"])
        if px < -40 or px > out_w + 40 or py < -40 or py > out_h + 40:
            continue  # off-screen
        is_home = bool(c.get("home"))
        f = font_home if is_home else font
        text = "\n".join(_label_lines(c, dt, fmt))
        bb = draw.multiline_textbbox((0, 0), text, font=f, spacing=2, anchor="la")
        items.append({
            "c": c, "is_home": is_home, "f": f, "text": text, "px": px, "py": py,
            "ox": bb[0], "oy": bb[1], "w": bb[2] - bb[0], "h": bb[3] - bb[1],
            "dotr": round((6 if is_home else 4) * scale),
        })

    # Place labels avoiding dots, the logo box, the screen edges and each other.
    dot_boxes = [(it["px"] - it["dotr"], it["py"] - it["dotr"],
                  it["px"] + it["dotr"], it["py"] + it["dotr"]) for it in items]
    m = round(10 * scale)
    _place_labels(items, obstacles + dot_boxes,
                  (m, m, out_w - m, out_h - m - bar_height), scale)

    # Semi-transparent rounded backplate behind each label, for legibility over the map.
    if label_bg_alpha > 0 and items:
        pad_x = max(4, round(10 * scale * font_scale))
        pad_y = max(3, round(7 * scale * font_scale))
        rad = max(3, round(7 * scale * font_scale))
        plate = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        pd = ImageDraw.Draw(plate)
        for it in items:
            bx0, by0, bx1, by1 = it["box"]
            pd.rounded_rectangle([bx0 - pad_x, by0 - pad_y, bx1 + pad_x, by1 + pad_y],
                                 radius=rad, fill=(0, 0, 0, label_bg_alpha))
        canvas = Image.alpha_composite(canvas, plate)
        draw = ImageDraw.Draw(canvas)  # rebind to the composited canvas

    # Draw dots + labels at their placed boxes.
    for it in items:
        is_home = it["is_home"]
        dot = home_rgb if is_home else th["dot"]
        txt = home_rgb if is_home else th["text"]
        stroke = th["home_stroke"] if is_home else th["text_stroke"]
        r = it["dotr"]
        px, py = it["px"], it["py"]
        draw.ellipse([px - r, py - r, px + r, py + r], fill=dot,
                     outline=th["dot_outline"], width=max(1, round(scale)))
        draw.multiline_text(
            (it["box"][0] - it["ox"], it["box"][1] - it["oy"]), it["text"],
            font=it["f"], fill=txt, spacing=2, anchor="la",
            stroke_width=max(1, round(scale)), stroke_fill=stroke,
        )

    return canvas.convert("RGB")
