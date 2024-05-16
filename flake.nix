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
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/1.tar.gz";
  };

  inputs.volare.inputs.nixpkgs.follows = "nix-eda/nixpkgs";

  outputs = {
    self,
    nix-eda,
    volare,
    ...
  }: let
    package-config = {
      current = self;
      withInputs = [nix-eda volare];
    };
  in {
    # Helper functions
    createCaceShell = import ./nix/create-shell.nix;

    # Outputs
    packages = nix-eda.forAllSystems package-config (util:
      with util;
        rec {
          colab-env = callPackage ./nix/colab-env.nix {};
          cace = callPythonPackage ./default.nix {};
          default = cace;
        }
        // (pkgs.lib.optionalAttrs (pkgs.stdenv.isLinux) {cace-docker = callPackage ./nix/docker.nix {createDockerImage = nix-eda.createDockerImage;};}));

    devShells = nix-eda.forAllSystems package-config (
      util:
        with util; rec {
          default =
            callPackage (self.createCaceShell {
              }) {};
          notebook = callPackage (self.createCaceShell {
            extra-packages = with pkgs; [
              jupyter
            ];
          }) {};
          dev = callPackage (self.createCaceShell {
            extra-packages = with pkgs; [
            ];
            extra-python-packages = with pkgs.python3.pkgs; [
              setuptools
              build
              twine
              black # blue
            ];
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
          }) {};
        }
    );
  };
}
