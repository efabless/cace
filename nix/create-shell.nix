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
  extra-packages ? [],
  extra-python-packages ? [],
  include-cace ? true
}: ({
  lib,
  git,
  zsh,
  delta,
  neovim,
  gtkwave,
  coreutils,
  graphviz,
  python3,
  devshell,
}: let
  cace = python3.pkgs.cace;
  cace-env = (
    python3.withPackages (pp:
        (if include-cace then [cace] else cace.propagatedBuildInputs)
        ++ extra-python-packages)
  );
  cace-env-sitepackages = "${cace-env}/${cace-env.sitePackages}";
  prompt = ''\[\033[1;32m\][nix-shell:\w]\$\[\033[0m\] '';
  packages =
  [
    cace-env

    # Conveniences
    git
    zsh
    delta
    neovim
    gtkwave
    coreutils
    graphviz
  ]
  ++ extra-packages
  ++ cace.includedTools;
in
  devshell.mkShell {
    devshell.packages = packages;
    env = [
      {
        name = "PYTHONPATH";
        value = "${cace-env-sitepackages}";
      }
    ];
    devshell.interactive.PS1 = {
      text = ''PS1="${prompt}"'';
    };
    motd = "";
  })
