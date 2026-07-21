# Home-manager module: declaratively configure + schedule the wallpaper.
#
# Import via the flake's homeManagerModules.default, then:
#   services.greyline = {
#     enable = true;
#     settings.city = [ { name = "Kuala Lumpur"; lat = 3.14; lon = 101.69; tz = "Asia/Kuala_Lumpur"; } ... ];
#   };
self:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.greyline;
  tomlFormat = pkgs.formats.toml { };
  useSwww = cfg.backend == "swww";
  useGnome = cfg.backend == "gnome";
  # The daemon binary is "<mainProgram>-daemon" — works whether the package ships
  # swww-daemon or awww-daemon (some nixpkgs revisions rename it).
  swwwDaemon = "${lib.getExe cfg.swwwPackage}-daemon";
in
{
  options.services.greyline = {
    enable = lib.mkEnableOption "the greyline live world-time wallpaper";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "greyline";
      description = "The wallpaper renderer package.";
    };

    interval = lib.mkOption {
      type = lib.types.str;
      default = "*:*:00";
      description = "systemd OnCalendar expression — the update cadence (default: each minute).";
    };

    backend = lib.mkOption {
      type = lib.types.enum [
        "auto"
        "sway"
        "swww"
        "hyprpaper"
        "gnome"
        "x11"
      ];
      default = "auto";
      description = "Display backend used to set the wallpaper.";
    };

    fontFamily = lib.mkOption {
      type = lib.types.str;
      default = "Aporetic Sans";
      description = "Label font family, resolved at runtime via fontconfig.";
    };

    target = lib.mkOption {
      type = lib.types.str;
      default = "graphical-session.target";
      description = "Graphical-session target the service binds to (so it renders at login).";
    };

    extraPackages = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = if useSwww then [ cfg.swwwPackage ] else if useGnome then [ ] else [ pkgs.sway ];
      defaultText = lib.literalExpression "[ pkgs.sway ] (or [ swwwPackage ] for swww; no extra package for gnome)";
      description = ''
        Runtime tools placed on the service PATH (e.g. the compositor's IPC client:
        swaymsg from sway, or swww / hyprland). fontconfig and glib (gsettings)
        are always added. Hyprland users: set this to [ pkgs.hyprland ].
      '';
    };

    swwwPackage = lib.mkOption {
      type = lib.types.package;
      default = pkgs.swww;
      defaultText = lib.literalExpression "pkgs.swww";
      description = "swww package providing the wallpaper daemon (used when backend = swww).";
    };

    settings = lib.mkOption {
      type = tomlFormat.type;
      default = { };
      description = ''
        Written to ~/.config/greyline/config.toml. When empty, the package's
        bundled defaults (10 world cities, dark vector theme) are used. Provide a
        `city` list to choose your own cities and a `home.tz` to pick the accented one.
      '';
      example = lib.literalExpression ''
        {
          theme = "dark";
          format = "24h";
          twilight = { bands = true; darkness = "subtle"; };
          home = { tz = "auto"; column_highlight = true; };
          city = [
            { name = "Kuala Lumpur"; lat = 3.14; lon = 101.69; tz = "Asia/Kuala_Lumpur"; }
            { name = "London"; lat = 51.51; lon = -0.13; tz = "Europe/London"; }
            { name = "New York"; lat = 40.71; lon = -74.01; tz = "America/New_York"; }
          ];
        }
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    xdg.configFile = lib.mkIf (cfg.settings != { }) {
      "greyline/config.toml".source = tomlFormat.generate "greyline-config.toml" cfg.settings;
    };

    # swww wallpaper daemon — buffered, flash-free swaps; survives `swaymsg reload`.
    systemd.user.services.swww-daemon = lib.mkIf useSwww {
      Unit = {
        Description = "swww wallpaper daemon (backend for greyline)";
        After = [ cfg.target ];
        PartOf = [ cfg.target ];
      };
      Service = {
        Type = "simple";
        ExecStart = swwwDaemon;
        Restart = "on-failure";
      };
      Install.WantedBy = [ cfg.target ];
    };

    # Oneshot renderer: runs once at session start and on each timer tick, then exits.
    systemd.user.services.greyline = {
      Unit = {
        Description = "Render the greyline world-time wallpaper";
        After = [ cfg.target ] ++ lib.optional useSwww "swww-daemon.service";
        Wants = lib.optional useSwww "swww-daemon.service";
        PartOf = [ cfg.target ];
      };
      Service = {
        Type = "oneshot";
        # glib provides gsettings for the GNOME backend.
        Environment = [
          "PATH=${lib.makeBinPath (cfg.extraPackages ++ [ pkgs.fontconfig pkgs.glib ])}:/run/current-system/sw/bin"
        ];
        ExecStart = ''${cfg.package}/bin/greyline --backend ${cfg.backend} --font-family "${cfg.fontFamily}"'';
      };
      Install.WantedBy = [ cfg.target ];
    };

    systemd.user.timers.greyline = {
      Unit.Description = "Update the greyline world-time wallpaper on a schedule";
      Timer = {
        OnCalendar = cfg.interval;
        Persistent = true;
      };
      Install.WantedBy = [ "timers.target" ];
    };
  };
}
