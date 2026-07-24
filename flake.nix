{
  description = "greyline — a live, multi-timezone world-time desktop wallpaper for Wayland/X11";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: nixpkgs.legacyPackages.${system};

      mkPackage =
        pkgs:
        pkgs.python3Packages.buildPythonApplication {
          pname = "greyline";
          version = "0.5.4";
          pyproject = true;
          src = ./.;
          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = [
            pkgs.python3Packages.pillow
            pkgs.python3Packages.tomlkit
          ];
          # fc-match (font resolution) is always needed; the compositor IPC tools
          # (swaymsg/swww/hyprctl/feh) come from the session PATH or the HM module.
          nativeBuildInputs = [ pkgs.makeWrapper ];
          makeWrapperArgs = [ "--prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.fontconfig ]}" ];
          nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
          pythonImportsCheck = [ "worldtime" ];
          doCheck = true;
          # pythonImportsCheckPhase cd's to $NIX_BUILD_TOP; return to the source so
          # pytest finds tests/.
          preCheck = "cd $NIX_BUILD_TOP/$sourceRoot";
          meta = {
            description = "Live multi-timezone world-time desktop wallpaper";
            license = pkgs.lib.licenses.gpl2Plus;
            mainProgram = "greyline";
            platforms = pkgs.lib.platforms.unix;
          };
        };
    in
    {
      packages = forAll (
        s:
        let
          pkgs = pkgsFor s;
          greyline = mkPackage pkgs;
        in
        {
          # `.tests.gnome` is an on-demand GNOME VM regression test (see
          # nix/gnome-vm-test.nix). It lives in passthru, not `checks`, so
          # `nix flake check`/CI never boot a GNOME VM. Run: nix build .#default.tests.gnome
          default = greyline.overrideAttrs (old: {
            passthru = (old.passthru or { }) // {
              tests.gnome = import ./nix/gnome-vm-test.nix { inherit pkgs greyline; };
            };
          });
        }
      );

      apps = forAll (s: {
        default = {
          type = "app";
          program = "${self.packages.${s}.default}/bin/greyline";
          meta.description = "Render/apply the greyline world-time wallpaper";
        };
      });

      devShells = forAll (
        s:
        let
          pkgs = pkgsFor s;
        in
        {
          default = pkgs.mkShell {
            packages = [
              (pkgs.python3.withPackages (ps: [ ps.pillow ps.tomlkit ]))
              pkgs.fontconfig
            ];
          };
        }
      );

      homeManagerModules.default = import ./nix/hm-module.nix self;

      formatter = forAll (s: (pkgsFor s).nixfmt);
    };
}
