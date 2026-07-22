"""Command backend: availability gating, output sizing, and {path}/{output} substitution.

Also covers the Windows/macOS backends (beta, untested on real hardware): these tests
mock the OS calls so their command construction and platform gating are verified on any
OS the suite runs on.
"""
import glob
import os

import pytest

from worldtime.backends import command, macos, windows


def test_available_requires_command(monkeypatch):
    monkeypatch.delenv("GREYLINE_COMMAND", raising=False)
    assert command.available() is False
    monkeypatch.setenv("GREYLINE_COMMAND", "feh --bg-fill {path}")
    assert command.available() is True


def test_outputs_uses_explicit_resolution(monkeypatch):
    monkeypatch.setenv("GREYLINE_RESOLUTION", "2560x1440")
    outs = command.outputs()
    assert outs == [{"name": "screen", "width": 2560, "height": 1440, "scale": 1.0}]


def test_outputs_falls_back_to_default_without_xrandr(monkeypatch):
    monkeypatch.delenv("GREYLINE_RESOLUTION", raising=False)
    monkeypatch.setattr(command._util, "xrandr_outputs", lambda: [])
    outs = command.outputs()
    assert outs == [{"name": "screen", "width": 1920, "height": 1080, "scale": 1.0}]


def test_outputs_prefers_largest_xrandr_output(monkeypatch):
    monkeypatch.delenv("GREYLINE_RESOLUTION", raising=False)
    monkeypatch.setattr(command._util, "xrandr_outputs", lambda: [
        {"name": "HDMI-1", "width": 1920, "height": 1080, "scale": 1.0},
        {"name": "DP-1", "width": 3840, "height": 2160, "scale": 1.0},
    ])
    w, h = command.outputs()[0]["width"], command.outputs()[0]["height"]
    assert (w, h) == (3840, 2160)


def test_apply_substitutes_path_and_output(monkeypatch):
    calls = {}

    def fake_run(cmd, shell=False, check=False):
        calls["cmd"], calls["shell"], calls["check"] = cmd, shell, check

    monkeypatch.setenv("GREYLINE_COMMAND", "set-wp --output {output} --img {path}")
    monkeypatch.setattr(command.subprocess, "run", fake_run)
    command.apply("DP-1", "/run/greyline/DP-1.png")
    assert calls["cmd"] == "set-wp --output DP-1 --img /run/greyline/DP-1.png"
    assert calls["shell"] is True and calls["check"] is True


def test_apply_without_command_errors(monkeypatch):
    monkeypatch.delenv("GREYLINE_COMMAND", raising=False)
    with pytest.raises(RuntimeError):
        command.apply("screen", "/tmp/x.png")


# --- windows backend (mocked; no Windows needed) ---

def test_windows_available_gates_on_platform(monkeypatch):
    monkeypatch.setattr(windows.sys, "platform", "win32")
    assert windows.available() is True
    monkeypatch.setattr(windows.sys, "platform", "linux")
    assert windows.available() is False


def test_windows_apply_calls_systemparametersinfo(monkeypatch):
    import ctypes

    calls = {}

    class _FakeUser32:
        def SystemParametersInfoW(self, action, uiParam, pvParam, fWinIni):
            calls["args"] = (action, uiParam, pvParam, fWinIni)
            return 1  # non-zero = success

    class _FakeWindll:
        user32 = _FakeUser32()

    monkeypatch.setattr(ctypes, "windll", _FakeWindll(), raising=False)
    windows.apply("default", r"C:\Users\me\AppData\greyline\default.png")
    action, uiParam, pvParam, fWinIni = calls["args"]
    assert action == windows.SPI_SETDESKWALLPAPER
    assert pvParam == r"C:\Users\me\AppData\greyline\default.png"
    # UPDATEINIFILE | SENDCHANGE so the change persists and goes live.
    assert fWinIni == windows.SPIF_UPDATEINIFILE | windows.SPIF_SENDCHANGE


def test_windows_apply_raises_on_failure(monkeypatch):
    import ctypes

    class _FakeUser32:
        def SystemParametersInfoW(self, *a):
            return 0  # zero = failure

    class _FakeWindll:
        user32 = _FakeUser32()

    monkeypatch.setattr(ctypes, "windll", _FakeWindll(), raising=False)
    monkeypatch.setattr(ctypes, "WinError", lambda code=None: RuntimeError("winerror"),
                        raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    with pytest.raises(RuntimeError):
        windows.apply("default", "C:/x.png")


# --- macos backend (mocked; no Mac needed) ---

def test_macos_available_gates_on_platform(monkeypatch):
    monkeypatch.setattr(macos.sys, "platform", "darwin")
    assert macos.available() is True
    monkeypatch.setattr(macos.sys, "platform", "linux")
    assert macos.available() is False


def test_macos_apply_rotates_path_and_runs_osascript(monkeypatch, tmp_path):
    src = tmp_path / "default.png"
    src.write_bytes(b"PNGDATA")

    calls = {}

    def fake_run(cmd, capture_output=False, text=False, check=False):
        calls["cmd"] = cmd

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    macos.apply("default", str(src))

    # osascript invoked with a set-picture AppleScript.
    assert calls["cmd"][0] == "osascript" and calls["cmd"][1] == "-e"
    script = calls["cmd"][2]
    assert "set picture of every desktop" in script

    # The applied path is a *rotated* copy (different name, defeats the cache),
    # it exists, and carries the same bytes as the render.
    rotated = glob.glob(str(tmp_path / f"{macos._ROTATE_PREFIX}*.png"))
    assert len(rotated) == 1
    assert rotated[0] != str(src)
    assert f'POSIX file "{rotated[0]}"' in script
    assert open(rotated[0], "rb").read() == b"PNGDATA"


def test_macos_rotate_prunes_previous_copies(monkeypatch, tmp_path):
    src = tmp_path / "default.png"
    src.write_bytes(b"A")
    # A stale rotation left over from a prior tick.
    stale = tmp_path / f"{macos._ROTATE_PREFIX}old.png"
    stale.write_bytes(b"old")

    monkeypatch.setattr(macos.subprocess, "run",
                        lambda *a, **k: None)
    macos.apply("default", str(src))

    assert not stale.exists()  # old copy pruned
    assert len(glob.glob(str(tmp_path / f"{macos._ROTATE_PREFIX}*.png"))) == 1
