"""systemd user timer generation + lifecycle — so `greyline enable` replaces the
old "git clone the repo to grab the units, install, daemon-reload, enable" dance.

The unit text is generated here (one source of truth); the files under systemd/ in
the repo remain only as reference for people who prefer to install them by hand.
"""
import os
import shutil
import subprocess
import sys

UNIT_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "systemd", "user",
)


def greyline_bin():
    """Absolute path to the greyline executable for ExecStart."""
    return shutil.which("greyline") or os.path.realpath(sys.argv[0])


def service_unit():
    return f"""[Unit]
Description=Render the greyline world-time wallpaper
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
ExecStart={greyline_bin()}
"""


def timer_unit(interval="*:*:00"):
    return f"""[Unit]
Description=Update the greyline world-time wallpaper on a schedule

[Timer]
OnCalendar={interval}
# Fire within 1s of :00 — a visible clock can't drift; one timer/min = negligible power.
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
"""


def systemd_user_available():
    """True if a systemd user instance is usable (systemctl --user responds)."""
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-system-running"],
        capture_output=True, text=True,
    )
    # "running"/"degraded" => usable; "offline"/no bus => rc != 0 with an error.
    return r.returncode == 0 or r.stdout.strip() in {"running", "degraded", "starting"}


def _systemctl(*args):
    subprocess.run(["systemctl", "--user", *args], check=True)


def install_and_enable(interval="*:*:00", dry_run=False):
    """Write the units and enable+start the timer. Returns a list of action strings."""
    svc = os.path.join(UNIT_DIR, "greyline.service")
    tmr = os.path.join(UNIT_DIR, "greyline.timer")
    actions = [
        f"write {svc}",
        f"write {tmr}  (OnCalendar={interval})",
        "systemctl --user daemon-reload",
        "systemctl --user enable --now greyline.timer",
    ]
    if dry_run:
        return actions
    os.makedirs(UNIT_DIR, exist_ok=True)
    with open(svc, "w", encoding="utf-8") as f:
        f.write(service_unit())
    with open(tmr, "w", encoding="utf-8") as f:
        f.write(timer_unit(interval))
    _systemctl("daemon-reload")
    _systemctl("enable", "--now", "greyline.timer")
    return actions


def disable():
    _systemctl("disable", "--now", "greyline.timer")


def status():
    subprocess.run(
        ["systemctl", "--user", "list-timers", "greyline.timer", "--no-pager"]
    )
