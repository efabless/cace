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
  extra-python-packages ? []
}: ({
  lib,
  cace,
  git,
  zsh,
  delta,
  neovim,
  gtkwave,
  coreutils,
  graphviz,
  python3,
  mkShell,
  glibcLocales,
}: let
  cace-env = (
    python3.withPackages (pp:
      with pp;
        [
          cace
        ]
        ++ extra-python-packages)
  );
  cace-env-sitepackages = "${cace-env}/${cace-env.sitePackages}";
in
  mkShell {
    name = "cace-shell";

    propagatedBuildInputs =
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

    PYTHONPATH = "${cace-env-sitepackages}"; # Allows venvs to work properly
    LOCALE_ARCHIVE = "${glibcLocales}/lib/locale/locale-archive";
    shellHook = ''
      export PS1="\n\[\033[1;32m\][nix-shell:\w]\$\[\033[0m\] ";
    '';
  })
