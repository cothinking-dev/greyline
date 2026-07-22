# End-to-end regression test on a real GNOME session.
#
# Reproduces the exact trap that used to make `greyline init` pick the generic `x11`
# root-window backend on GNOME: a full GNOME desktop that also has `feh` on PATH and
# `$DISPLAY` set (via Xwayland). feh sets the X root window, which mutter silently
# overpaints — so the wallpaper never changes. After the fix, init must instead use the
# GNOME `gsettings` recipe, and greyline must actually set the desktop wallpaper.
#
# Heavy: this boots a full GNOME VM (KVM required, multi-GB closure). It is deliberately
# kept OUT of the flake `checks` output so `nix flake check` / CI stay light; run it on
# demand with:  nix build .#default.tests.gnome -L
{ pkgs, greyline }:

pkgs.testers.runNixOSTest {
  name = "greyline-gnome-wallpaper";

  nodes.machine =
    { pkgs, ... }:
    {
      services.xserver.enable = true;
      services.displayManager.gdm.enable = true;
      services.displayManager.autoLogin = {
        enable = true;
        user = "alice";
      };
      services.desktopManager.gnome.enable = true;

      users.users.alice = {
        isNormalUser = true;
        uid = 1000;
      };

      # greyline + the two ingredients of the trap: feh on PATH, and glib for gsettings.
      environment.systemPackages = [
        greyline
        pkgs.feh
        pkgs.glib
      ];

      virtualisation.memorySize = 4096;
      virtualisation.cores = 2;
    };

  testScript =
    let
      uid = "1000";
      # The env a real GNOME session provides: user bus + runtime dir for gsettings/dconf,
      # the GNOME desktop token, and DISPLAY set (Xwayland) — the last two are what made
      # detection pick x11 before the fix.
      env =
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${uid}/bus "
        + "XDG_RUNTIME_DIR=/run/user/${uid} "
        + "XDG_CURRENT_DESKTOP=GNOME DISPLAY=:0";
      # Run a command inside alice's live GNOME session.
      run = cmd: "su - alice -c '${env} ${cmd}'";
      getUri = "gsettings get org.gnome.desktop.background picture-uri";
    in
    ''
      machine.wait_for_unit("display-manager.service")
      machine.wait_for_file("/run/user/${uid}/wayland-0")
      machine.wait_for_unit("default.target", "alice")
      # dconf/gsettings must be reachable in the session before we assert on it.
      machine.wait_until_succeeds(${builtins.toJSON (run getUri)})

      # Confirm the trap is present: feh really is on PATH in the session.
      machine.succeed(${builtins.toJSON (run "command -v feh")})

      # 1) Backend selection: init must choose the GNOME gsettings recipe, not x11.
      init_out = machine.succeed(${builtins.toJSON (run "greyline init --dry-run")})
      assert "backend = command  (gnome recipe)" in init_out, init_out
      assert "x11" not in init_out, init_out

      # 2) End-to-end: real init + one render/apply, then the live GNOME wallpaper
      #    setting must point at greyline's rendered PNG.
      machine.succeed(${builtins.toJSON (run "greyline init")})
      machine.succeed(${builtins.toJSON (run "greyline")})
      uri = machine.succeed(${builtins.toJSON (run getUri)})
      assert "greyline/screen.png" in uri, uri
    '';
}
