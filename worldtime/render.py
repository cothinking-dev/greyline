"""Compose the World Time wallpaper image (PORTABLE CORE; deps: Pillow).

Pipeline (see plan): work in the map's 1400x1050 calibration frame for the smooth
day/night + twilight overlays and the home timezone-column highlight; cover-crop the
composited map to the target output size; then draw the city clocks at NATIVE output
resolution so text stays crisp on HiDPI panels.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps

from . import geo, sun, vectormap

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
BASE_1400 = os.path.join(ASSET_DIR, "world.time.1400x1050.png")
LOGO_PNG = os.path.join(ASSET_DIR, "tux.png")  # default corner logo (see NOTICE for swapping it)

# Twilight boundaries (solar elevation, degrees): terminator + civil/nautical/astro.
# Each is filled as a night-side polygon; stacking translucent layers darkens the
# deeper-night regions progressively.
TWILIGHT_ELEVATIONS = (0.0, -6.0, -12.0, -18.0)

# Per-layer overlay alpha by darkness preset (4 stacked layers at full night).
DARKNESS_ALPHA = {"subtle": 28, "medium": 40, "dramatic": 55}

THEMES = {
    "blue": {
        "night": (6, 12, 34),          # deep navy overlay (faithful to the classic blue map)
        "text": (226, 232, 255),
        "text_stroke": (4, 8, 26, 220),
        "dot": (210, 220, 255),
        "dot_outline": (4, 8, 26, 200),
        "home": (255, 70, 70),         # accent: home dot + label
        "home_stroke": (40, 0, 0, 220),
        "column": (255, 255, 255, 26),  # home timezone-column highlight
        # Vector-map palette (Phase B): ocean / land / borders / timezone grid.
        "ocean": (61, 97, 210),         # #3d61d2 — the classic blue
        "land": (42, 71, 160),
        "border": (120, 150, 230),
        "grid": (255, 255, 255, 38),
        "grid_label": (200, 210, 255),
        "idl": (224, 60, 60),           # red International Date Line (faithful to the art)
        "gmt": (90, 220, 130, 64),      # green UTC+0 timezone-column fill
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
        "grid": (255, 255, 255, 48),
        "grid_label": (130, 138, 158),
        "idl": (208, 72, 72),           # red International Date Line (muted for the dark map)
        "gmt": (88, 184, 128, 52),      # green UTC+0 timezone-column fill
        "day_wash": (140, 165, 220, 18),  # per-band day-side brighten (stacked x4)
        "night_alpha": 12,                # gentle night darkening → low contrast, brighter darks
        "logo": (224, 228, 238),          # target colour when logo_invert is set (dark wordmark → light)
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


# Vector-map framing. Plain equirectangular over the FULL globe so nothing is cropped —
# the raster's tighter ~333deg window cut off the mid-Pacific (Alaska, Hawaii, the
# Aleutians). Latitude uses the raster art's px-per-degree ratio (|BY|/|AX|), so
# continents keep their familiar (slightly tall) shape rather than the squashed look of a
# 1:1 equirectangular. Centred west of Greenwich so the seam falls in the empty Bering/
# Pacific and the Americas (incl. Alaska) sit comfortably inside the left edge.
VECTOR_LON_CENTER = 12.0
VECTOR_LAT_CENTER = 0.0  # equator-centred → poles at the top/bottom edges (pole-to-pole on a 16:10 panel)


def _vector_projection(out_w, out_h):
    ppd_lon = out_w / 360.0
    ppd_lat = ppd_lon * (abs(geo.BY) / abs(geo.AX))
    cx, cy = out_w / 2.0, out_h / 2.0
    return Projection(
        to_px=lambda lon, lat: (cx + (lon - VECTOR_LON_CENTER) * ppd_lon,
                                cy + (VECTOR_LAT_CENTER - lat) * ppd_lat),
        x_to_lon=lambda x: VECTOR_LON_CENTER + (x - cx) / ppd_lon,
        lat_to_y=lambda lat: cy + (VECTOR_LAT_CENTER - lat) * ppd_lat,
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


def _blend_region(base, layer_rgb, op):
    """Apply a blend `op` (ImageChops.multiply / .screen) of `layer_rgb` onto `base`,
    preserving base's alpha. The layer is a no-op colour everywhere except the band
    polygon (white for multiply, black for screen), so only that region changes."""
    mixed = op(base.convert("RGB"), layer_rgb)
    mixed.putalpha(base.getchannel("A"))
    return mixed


def _overlay_night(base, dt, theme, bands, alpha, proj):
    """Composite the day/night terminator with stepped twilight bands.

    Rather than alpha-compositing an opaque dark scrim (a "normal" blend, which mutes
    every pixel toward the same colour and so flattens the map's GMT grid lines and
    country borders), each band is mixed into the base multiplicatively/screen — a colour
    mix that tints toward night / brightens toward day while PRESERVING the contrast of
    fine lines underneath (works for both the raster art and the vector map):
      - day-side LIGHT washes (SCREEN toward the sun) — brighten the lit hemisphere;
      - night-side DARK washes (MULTIPLY toward midnight) — deepen the dark hemisphere.
    The civil/nautical/astronomical elevations are stacked, so each twilight band is a
    distinct step.
    """
    w, h = base.size
    sublat, sublon = sun.subsolar_point(dt)
    elevations = TWILIGHT_ELEVATIONS if bands else (0.0,)

    def stack(day_side, base_color, tint, op):
        nonlocal base
        for elev in elevations:
            layer = Image.new("RGB", (w, h), base_color)
            ImageDraw.Draw(layer).polygon(
                _terminator_polygon(elev, sublat, sublon, proj, w, h, day_side=day_side),
                fill=tint,
            )
            base = _blend_region(base, layer, op)

    # Day side: SCREEN a light tint (the wash colour scaled by its alpha); black = no-op.
    dw = theme.get("day_wash")
    if dw:
        a = dw[3] if len(dw) > 3 else 255
        tint = tuple(round(c * a / 255) for c in dw[:3])
        stack(day_side=True, base_color=(0, 0, 0), tint=tint, op=ImageChops.screen)

    # Night side: MULTIPLY toward the night colour; white = no-op. The per-band multiplier
    # is the night colour pulled toward white by `alpha` (so a stack of bands darkens
    # progressively without crushing line contrast the way an opaque scrim would).
    night = theme.get("night")
    if alpha > 0 and night:
        t = alpha / 255.0
        tint = tuple(round(255 - (255 - c) * t) for c in night)
        stack(day_side=False, base_color=(255, 255, 255), tint=tint, op=ImageChops.multiply)
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


def _draw_logo(canvas, theme, logo_path, bar_height=0, logo_color=None, logo_invert=False,
               logo_scale=1.0):
    """Composite the logo, pinned to the bottom-left CORNER of the wallpaper (anchored to
    the canvas, independent of the map framing). Returns its bbox or None.

    `bar_height` lifts it above a status bar overlaying the bottom of the wallpaper.
    `logo_color` (hex) recolours the whole logo to a flat silhouette (e.g. all-white).
    `logo_invert` recolours the near-black pixels to light while keeping other colours —
    handy for a dark wordmark on a dark theme; off by default so colour logos (e.g. Tux)
    composite as-is.
    """
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except OSError:
        return None
    # ~10% of canvas width by default; logo_scale lets you size it up/down. A wide
    # wordmark stays short at this width; a square logo (e.g. Tux) reads larger, so
    # logo_scale < 1 is handy there.
    target_w = max(24, round(canvas.width * 0.104 * logo_scale))
    target_h = round(target_w * logo.height / logo.width)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    mono = _hex(logo_color)
    if mono:
        logo = _mono_logo(logo, mono)
    elif logo_invert:
        logo = _recolor_dark(logo, tuple(theme.get("logo", (235, 235, 235))))
    pad = round(canvas.width * 0.018)
    x, y = pad, canvas.height - target_h - pad - bar_height
    canvas.alpha_composite(logo, (x, y))
    return (x, y, x + target_w, y + target_h)




def _rect_overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _place_labels(items, obstacles, bounds, scale):
    """Assign each label a non-overlapping box around its dot (right/left/above/below).

    Greedy: home first, then left-to-right. Each label picks the candidate side with the
    least overlap against obstacles (dots, logo, screen edges) and already-placed labels.
    A city's `label_side` ("left"/"right"/"above"/"below") is tried first; it still falls
    back to another side rather than overlap badly or run off-screen.
    """
    gap = round(6 * scale)
    placed = list(obstacles)
    order = sorted(range(len(items)), key=lambda i: (not items[i]["is_home"], items[i]["px"]))
    default_sides = ["right", "left", "below", "above", "below-right", "below-left"]
    for i in order:
        it = items[i]
        px, py, w, h, g = it["px"], it["py"], it["w"], it["h"], it["dotr"] + gap
        anchors = {
            "right": (px + g, py - h / 2),
            "left": (px - g - w, py - h / 2),
            "below": (px - w / 2, py + g),
            "above": (px - w / 2, py - g - h),
            "below-right": (px + g, py + g),
            "below-left": (px - g - w, py + g),
        }
        pref = it.get("side")
        sides = ([pref] + [s for s in default_sides if s != pref]
                 if pref in anchors else default_sides)
        candidates = [anchors[s] for s in sides]
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
    theme="dark",
    fmt="24h",
    twilight_bands=True,
    darkness="subtle",
    column_highlight=True,
    home_color=None,
    label_bg_alpha=130,
    map_style="vector",
    logo=True,
    logo_path=None,
    logo_color=None,
    logo_invert=False,
    logo_scale=1.0,
    bar_height=0,
    desaturate=False,
    font_path=None,
    font_bold_path=None,
    font_scale=1.0,
    base_path=BASE_1400,
    crop_anchor=(0.5, 1.0),
):
    th = THEMES.get(theme, THEMES["dark"])
    logo_path = logo_path or LOGO_PNG
    dt = dt or datetime.now(timezone.utc)
    alpha = th.get("night_alpha", DARKNESS_ALPHA.get(darkness, DARKNESS_ALPHA["subtle"]))
    home_rgb = _hex(home_color) or tuple(th["home"])  # accent colour for the home city
    out_w, out_h = out_size or (geo.REF_W, geo.REF_H)

    # Home city + its current UTC offset (used to highlight its timezone column).
    home = next((c for c in cities if c.get("home")), None)
    home_offset = None
    if home and column_highlight:
        off = dt.astimezone(ZoneInfo(home["tz"])).utcoffset()
        if off is not None:
            home_offset = off.total_seconds() / 3600.0

    # Build the map base + a projection (lon/lat -> output px) for the chosen style.
    if map_style == "vector":
        # Full-globe equirectangular (see _vector_projection) — the terminator, column
        # highlight and city clocks all share this one mapping, so they line up.
        proj = _vector_projection(out_w, out_h)
        scale = proj.scale
        grid_font = _load_font(max(8, round(11 * scale)), FONT_CANDIDATES, font_path)
        # The home highlight fills the real zone polygon here (like the GMT column),
        # so the straight-band fallback below is skipped for the vector style.
        canvas = vectormap.build_base(
            out_w, out_h, th, grid_font, proj.to_px, home_offset=home_offset
        ).convert("RGBA")
    else:
        proj, (sc, cx, cy) = _raster_projection(out_w, out_h, crop_anchor)
        scale = sc
        if not os.path.isfile(base_path):
            raise FileNotFoundError(
                f"raster map artwork not found at {base_path}. The IBM/Lenovo 'World Time' "
                "art is not bundled (see NOTICE); use map_style=\"vector\" or supply your own "
                "1400x1050 map via base_path."
            )
        base = Image.open(base_path).convert("RGBA")  # the 1400x1050 calibration frame
        if desaturate:  # grayscale the blue artwork → a black-and-white map, then
            # contrast 150% + brightness 70% (darker) for a crisp, muted base.
            gray = ImageOps.grayscale(base)
            gray = ImageEnhance.Contrast(gray).enhance(1.5)
            gray = ImageEnhance.Brightness(gray).enhance(0.7)
            base = gray.convert("RGBA")
        scaled = base.resize((round(geo.REF_W * sc), round(geo.REF_H * sc)), Image.LANCZOS)
        canvas = scaled.crop((round(cx), round(cy), round(cx) + out_w, round(cy) + out_h))

    # Home timezone-column highlight for the RASTER style (a straight band, one hour of
    # longitude wide). The vector style fills the real zone polygon in build_base instead.
    if column_highlight and home and map_style != "vector":
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
        b = _draw_logo(canvas, th, logo_path, bar_height, logo_color, logo_invert,
                       logo_scale)
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
            "side": c.get("label_side"),  # optional placement preference
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
