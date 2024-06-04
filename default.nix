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
  lib,
  nix-gitignore,
  buildPythonPackage,
  setuptools,
  setuptools_scm,

  # Tools
  klayout,
  klayout-pymod,
  magic,
  netgen,
  volare,
  octave,
  xschem,
  ngspice,
  
  # PIP
  matplotlib,
  numpy,
  pillow,
  tkinter,
  rich,
}:
buildPythonPackage rec {
  name = "cace";
  format = "pyproject";

  version_file = builtins.readFile ./cace/__version__.py;
  version_list = builtins.match ''.+''\n__version__ = '([^']+)'.+''\n.+''$'' version_file;
  version = builtins.head version_list;

  src = [
    ./README.md
    ./pyproject.toml
    (nix-gitignore.gitignoreSourcePure "__pycache__" ./cace)
    ./requirements.txt
  ];
  
  unpackPhase = ''
    echo $src
    for file in $src; do
      BASENAME=$(python3 -c "import os; print('$file'.split('-', maxsplit=1)[1], end='$EMPTY')")
      cp -r $file $PWD/$BASENAME
    done
    ls -lah
  '';

  buildInputs = [
    setuptools
    setuptools_scm
  ];
  
  includedTools = [
    klayout
    magic
    netgen
    octave
    ngspice
    xschem
  ];

  propagatedBuildInputs = [
    # Python
    matplotlib
    numpy
    pillow
    volare
    tkinter
    rich
  ]
  ++ includedTools;
  
  computed_PATH = lib.makeBinPath propagatedBuildInputs;

  # Make PATH available to OpenLane subprocesses
  makeWrapperArgs = [
    "--prefix PATH : ${computed_PATH}"
  ];

  meta = with lib; {
    description = "Circuit Automatic Characterization Engine";
    homepage = "https://github.com/efabless/cace";
    license = licenses.asl20;
    mainProgram = "cace";
    platforms = platforms.linux ++ platforms.darwin;
  };
}
