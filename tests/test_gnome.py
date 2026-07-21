"""GNOME wallpaper backend."""
from worldtime.backends import gnome


def test_gnome_backend_detects_gnome_session(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.delenv("DESKTOP_SESSION", raising=False)
    monkeypatch.setattr(gnome.shutil, "which", lambda _: "/usr/bin/gsettings")
    assert gnome.available()

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "sway")
    assert not gnome.available()


def test_gnome_backend_sets_both_background_uris(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(gnome.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    png = tmp_path / "wallpaper.png"
    gnome.apply("gnome-0", png)

    uri = png.resolve().as_uri()
    assert [args[0][3] for args, _ in calls] == ["picture-options", "picture-uri", "picture-uri-dark"]
    assert [args[0][-1] for args, _ in calls] == ["zoom", uri, uri]
    assert all(kwargs["check"] for _, kwargs in calls)


def test_gnome_backend_uses_alternating_paths(monkeypatch):
    monkeypatch.setattr(gnome.time, "time", lambda: 60)
    assert gnome.outputs()[0]["name"] == "gnome-1"


def test_gnome_uses_shared_1920x1080_canvas(monkeypatch):
    monkeypatch.setattr(gnome.time, "time", lambda: 0)
    assert gnome.outputs() == [{
        "name": "gnome-0", "width": 1920, "height": 1080, "scale": 1.0,
    }]
