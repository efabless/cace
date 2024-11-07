# Copyright 2024 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
{
  description = "open-source framework for automatic circuit characterization";

  nixConfig = {
    extra-substituters = [
      "https://openlane.cachix.org"
    ];
    extra-trusted-public-keys = [
      "openlane.cachix.org-1:qqdwh+QMNGmZAuyeQJTH9ErW57OWSvdtuwfBKdS254E="
    ];
  };

  inputs = {
    nix-eda.url = github:efabless/nix-eda;
    volare.url = github:efabless/volare;
    devshell.url = github:numtide/devshell;
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/1.tar.gz";
  };

  inputs.volare.inputs.nixpkgs.follows = "nix-eda/nixpkgs";
  inputs.devshell.inputs.nixpkgs.follows = "nix-eda/nixpkgs";

  outputs = {
    self,
    nix-eda,
    volare,
    devshell,
    ...
  }: let
    nixpkgs = nix-eda.inputs.nixpkgs;
    lib = nixpkgs.lib;
  in {
    # Common
    overlays = {
      default = lib.composeManyExtensions [
        (import ./nix/overlay.nix)
        (nix-eda.flakesToOverlay [volare])
        (
          pkgs': pkgs: let
            callPackage = lib.callPackageWith pkgs';
          in {
            colab-env = callPackage ./nix/colab-env.nix {};
          }
        )
        (
          nix-eda.composePythonOverlay (pkgs': pkgs: pypkgs': pypkgs: let
            callPythonPackage = lib.callPackageWith (pkgs' // pkgs'.python3.pkgs);
          in {
            cace = callPythonPackage ./default.nix {};
          })
        )
        (pkgs': pkgs: let
          callPackage = lib.callPackageWith pkgs';
        in
          {}
          // lib.optionalAttrs pkgs.stdenv.isLinux {
            cace-docker = callPackage ./nix/docker.nix {
              createDockerImage = nix-eda.createDockerImage;
              cace = pkgs'.python3.pkgs.cace;
            };
          })
      ];
    };

    # Helper functions
    createCaceShell = import ./nix/create-shell.nix;

    # Packages
    legacyPackages = nix-eda.forAllSystems (
      system:
        import nix-eda.inputs.nixpkgs {
          inherit system;
          overlays = [devshell.overlays.default nix-eda.overlays.default self.overlays.default];
        }
    );

    packages = nix-eda.forAllSystems (
      system: let
        pkgs = (self.legacyPackages."${system}");
        in {
          inherit (pkgs) colab-env;
          inherit (pkgs.python3.pkgs) cace;
          default = pkgs.python3.pkgs.cace;
        }
        // lib.optionalAttrs pkgs.stdenv.isLinux {
          inherit (pkgs) cace-docker;
        }
    );

    # devshells

    devShells = nix-eda.forAllSystems (
      system: let
        pkgs = self.legacyPackages."${system}";
        callPackage = lib.callPackageWith pkgs;
      in {
        # These devShells are rather unorthodox for Nix devShells in that they
        # include the package itself. For a proper devShell, try .#dev.
        default =
          callPackage (self.createCaceShell {
            }) {};
        notebook = callPackage (self.createCaceShell {
          extra-python-packages = with pkgs.python3.pkgs; [
            jupyter
            pandas
          ];
        }) {};
        # Normal devShells
        dev = callPackage (self.createCaceShell {
          extra-packages = with pkgs; [
          ];
          extra-python-packages = with pkgs.python3.pkgs; [
            setuptools
            build
            twine
            black # blue
          ];
          include-cace = false;
        }) {};
        docs = callPackage (self.createCaceShell {
          extra-packages = with pkgs; [
          ];
          extra-python-packages = with pkgs.python3.pkgs; [
            sphinx
            myst-parser
            furo
            sphinx-autobuild
          ];
          include-cace = false;
        }) {};
      }
    );
  };
}
