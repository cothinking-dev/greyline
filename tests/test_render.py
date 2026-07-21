"""End-to-end smoke: both map styles produce an RGB image of the requested size."""
import os
from datetime import datetime, timezone

import pytest

from worldtime import render

CITIES = [
    {"name": "London", "lat": 51.51, "lon": -0.13, "tz": "Europe/London", "home": True},
    {"name": "Tokyo", "lat": 35.68, "lon": 139.69, "tz": "Asia/Tokyo", "home": False},
]
DT = datetime(2024, 6, 20, 9, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("style", ["raster", "vector"])
def test_render_returns_rgb_at_size(style):
    if style == "raster" and not os.path.isfile(render.BASE_1400):
        pytest.skip("raster map artwork not bundled (IBM/Lenovo art, see NOTICE)")
    img = render.render(CITIES, dt=DT, out_size=(480, 300), map_style=style)
    assert img.size == (480, 300)
    assert img.mode == "RGB"


def test_unknown_theme_falls_back():
    img = render.render(CITIES, dt=DT, out_size=(320, 200), theme="does-not-exist")
    assert img.size == (320, 200)


def test_vector_projection_covers_portrait_output():
    proj = render._vector_projection(300, 480)
    assert proj.lat_to_y(90) <= 0
    assert proj.lat_to_y(-90) >= 480
