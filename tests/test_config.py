"""Config merge, home-city flagging, and render kwarg mapping."""
from worldtime import config


def test_deep_merge_is_recursive():
    base = {"a": 1, "t": {"x": 1, "y": 2}}
    over = {"t": {"y": 9, "z": 3}}
    out = config._deep_merge(base, over)
    assert out == {"a": 1, "t": {"x": 1, "y": 9, "z": 3}}
    assert base["t"] == {"x": 1, "y": 2}  # inputs untouched


def test_defaults_load_with_cities():
    cfg = config.load(path="/nonexistent/config.toml")
    assert isinstance(cfg.get("city"), list) and cfg["city"]
    assert all({"name", "lat", "lon", "tz"} <= c.keys() for c in cfg["city"])


def test_user_config_overrides_and_replaces_cities(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(
        'theme = "dark"\n'
        '[home]\ntz = "Europe/London"\n'
        '[[city]]\nname = "London"\nlat = 51.51\nlon = -0.13\ntz = "Europe/London"\n'
        '[[city]]\nname = "Tokyo"\nlat = 35.68\nlon = 139.69\ntz = "Asia/Tokyo"\n'
    )
    cfg = config.load(path=str(user))
    assert cfg["theme"] == "dark"
    assert [c["name"] for c in cfg["city"]] == ["London", "Tokyo"]  # replaced, not merged
    home = [c for c in cfg["city"] if c["home"]]
    assert [c["name"] for c in home] == ["London"]


def test_render_kwargs_shape():
    cfg = config.load(path="/nonexistent/config.toml")
    rkw = config.render_kwargs(cfg)
    assert rkw["theme"] and rkw["fmt"] in ("24h", "12h")
    assert rkw["logo_scale"] == 1.0  # default logo sizing
    assert "show_date" not in rkw  # dropped feature must not leak back in
