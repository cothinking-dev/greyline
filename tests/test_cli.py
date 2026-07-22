"""CLI plumbing: DE recipe detection, systemd unit generation, init, watch loop."""
import shutil

import pytest

from worldtime import __main__ as cli
from worldtime import config, recipes, service


# --- argument parsing ---

def test_parse_res_valid():
    assert cli._parse_res("2560x1440") == (2560, 1440)
    assert cli._parse_res("1920X1080") == (1920, 1080)  # case-insensitive


def test_parse_res_malformed_exits_cleanly():
    # Regression: a bad --res must give a clean SystemExit, not a raw ValueError traceback.
    for bad in ("1920", "1920xABC", "1920x1080x2"):
        with pytest.raises(SystemExit):
            cli._parse_res(bad)


# --- recipes ---

def test_detect_desktop_matches_case_insensitively():
    assert recipes.detect_desktop({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}) == "gnome"
    assert recipes.detect_desktop({"XDG_CURRENT_DESKTOP": "KDE"}) == "kde"
    assert recipes.detect_desktop({"XDG_CURRENT_DESKTOP": "XFCE"}) == "xfce"
    assert recipes.detect_desktop({"XDG_CURRENT_DESKTOP": "sway"}) is None
    assert recipes.detect_desktop({}) is None


def test_all_recipes_have_path_placeholder():
    assert all("{path}" in cmd for cmd in recipes.RECIPES.values())


# --- systemd unit generation ---

def test_service_unit_execstart_and_timer(monkeypatch):
    monkeypatch.setattr(service, "greyline_bin", lambda: "/opt/bin/greyline")
    svc = service.service_unit()
    assert "ExecStart=/opt/bin/greyline" in svc
    assert "Type=oneshot" in svc
    tmr = service.timer_unit(interval="*:0/5:00")
    assert "OnCalendar=*:0/5:00" in tmr
    assert "WantedBy=timers.target" in tmr


def test_install_and_enable_dry_run_lists_actions_without_writing(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "UNIT_DIR", str(tmp_path / "systemd"))
    actions = service.install_and_enable(interval="*:*:00", dry_run=True)
    assert any("daemon-reload" in a for a in actions)
    assert any("enable --now greyline.timer" in a for a in actions)
    assert not (tmp_path / "systemd").exists()  # nothing written in dry-run


# --- init ---

def test_init_writes_config_and_detected_backend(monkeypatch, tmp_path):
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.backends, "detect", lambda: "sway")
    monkeypatch.setattr(cli.service, "systemd_user_available", lambda: False)
    rc = cli.main(["--config", str(cfg_path), "init"])
    assert rc == 0 and cfg_path.exists()
    assert config.load(str(cfg_path))["backend"] == "sway"


def test_init_uses_command_recipe_for_gnome(monkeypatch, tmp_path):
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.backends, "detect", lambda: None)
    monkeypatch.setattr(cli.recipes, "detect_desktop", lambda: "gnome")
    monkeypatch.setattr(cli.service, "systemd_user_available", lambda: False)
    rc = cli.main(["--config", str(cfg_path), "init"])
    assert rc == 0
    c = config.load(str(cfg_path))
    assert c["backend"] == "command"
    assert c["command"] == recipes.RECIPES["gnome"]


def test_init_prefers_de_recipe_over_x11_fallback(monkeypatch, tmp_path):
    # Regression: on a full DE (GNOME/KDE/XFCE) that draws its own wallpaper, the
    # generic x11 root-window backend is silently overpainted by the compositor. If
    # feh/xwallpaper is installed, backends.detect() returns "x11" — but init must
    # still pick the DE's gsettings/xfconf/plasma recipe, not x11.
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.backends, "detect", lambda: "x11")
    monkeypatch.setattr(cli.recipes, "detect_desktop", lambda: "gnome")
    monkeypatch.setattr(cli.service, "systemd_user_available", lambda: False)
    rc = cli.main(["--config", str(cfg_path), "init"])
    assert rc == 0
    c = config.load(str(cfg_path))
    assert c["backend"] == "command"
    assert c["command"] == recipes.RECIPES["gnome"]


def test_init_keeps_x11_when_not_a_desktop_environment(monkeypatch, tmp_path):
    # A bare X11 window manager (no gnome/kde/xfce token) must still get the x11 backend.
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.backends, "detect", lambda: "x11")
    monkeypatch.setattr(cli.recipes, "detect_desktop", lambda: None)
    monkeypatch.setattr(cli.service, "systemd_user_available", lambda: False)
    rc = cli.main(["--config", str(cfg_path), "init"])
    assert rc == 0
    assert config.load(str(cfg_path))["backend"] == "x11"


def test_init_dry_run_writes_nothing(monkeypatch, tmp_path):
    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(cli.backends, "detect", lambda: "sway")
    monkeypatch.setattr(cli.service, "systemd_user_available", lambda: False)
    rc = cli.main(["--config", str(cfg_path), "init", "--dry-run"])
    assert rc == 0 and not cfg_path.exists()


# --- watch ---

def test_render_flags_work_before_and_after_subcommand():
    # Regression: argparse parent/subparser default-clobber must not drop --backend.
    parse = cli.build_parser().parse_args
    for argv in (["watch", "--backend", "command", "--command", "cp {path} x"],
                 ["--backend", "command", "--command", "cp {path} x", "watch"]):
        a = parse(argv)
        assert a.backend == "command" and a.command == "cp {path} x"
    assert parse(["watch"]).backend is None  # unset stays None


def test_watch_loops_run_apply_until_interrupted(monkeypatch):
    calls = {"n": 0}

    def fake_apply(args):
        calls["n"] += 1
        return 0

    def fake_sleep(_):
        raise KeyboardInterrupt  # break the loop after the first render

    monkeypatch.setattr(cli, "run_apply", fake_apply)
    monkeypatch.setattr("time.sleep", fake_sleep)
    rc = cli.main(["watch", "--interval", "60"])
    assert rc == 0 and calls["n"] == 1
