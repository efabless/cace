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
  buildPythonPackage,
  fetchPypi,
  setuptools,
  setuptools_scm,
  
  # Tools
  klayout,
  
  # Python
  matplotlib,
  numpy,
  rich,
  flit-core,
  orjson,
  pandas,
  pydantic,
  pydantic-settings,
  pydantic-extra-types,
  pyyaml,
  qrcode,
  scipy,
  shapely,
  toolz,
  types-pyyaml,
  typer,
  watchdog,
  freetype-py,
  mapbox-earcut,
  networkx,
  trimesh,
  ipykernel,
  attrs,
  aenum,
  cachetools,
  gitpython,
  loguru,
  requests,
  tomli,
  cython_0,
  ruamel-yaml,
  jinja2,
}: let

  rectangle-packer = buildPythonPackage rec {
    pname = "rectangle-packer";
    format = "pyproject";
    version = "2.0.2";
    
    buildInputs = [
        setuptools
        cython_0
      ];
  
    propagatedBuildInputs = [
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-NORQApJV9ybEqObpOaGMrVh58Nn+WIwYeP6FyHLcvkE=";
    };
    doCheck = false;
  };

  rectpack = buildPythonPackage rec {
    pname = "rectpack";
    format = "pyproject";
    version = "0.2.2";
    
    buildInputs = [
        setuptools
      ];
  
    propagatedBuildInputs = [
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-FeODUF/fuutV7GQKWCXZyizokBmmzdVS1uV+w2xouio=";
    };
    doCheck = false;
  };

  ruamel-yaml-string = buildPythonPackage rec {
    pname = "ruamel.yaml.string";
    format = "pyproject";
    version = "0.1.1";
    
    buildInputs = [
        setuptools
      ];
  
    propagatedBuildInputs = [
        ruamel-yaml
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-enrtzAVdRcAE04t1b1hHTr77EGhR9M5WzlhBVwl4Q1A=";
    };
    doCheck = false;
  };

  kfactory = buildPythonPackage rec {
    pname = "kfactory";
    format = "pyproject";
    version = "0.18.4";
    
    buildInputs = [
        setuptools
        setuptools_scm
      ];
  
    propagatedBuildInputs = [
        aenum
        cachetools
        gitpython
        loguru
        klayout.pymod
        pydantic
        pydantic-settings
        rectangle-packer
        requests
        ruamel-yaml-string
        scipy
        tomli
        toolz
        typer
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-2thvsHTlc61U5LiaDLlEAcKYY7Vh2ZGe5Z7tAN1sUtQ=";
    };
    doCheck = false;
  };

  trimesh-4_4_1 = buildPythonPackage rec {
    pname = "trimesh";
    format = "pyproject";
    version = "4.4.1";
    
    buildInputs = [
        setuptools
      ];
  
    propagatedBuildInputs = [
        numpy
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-dn/jyGa6dObZqdIWw07MHP4vvz8SmmwR1ZhxcFpZGro=";
    };
    doCheck = false;
  };

  self = buildPythonPackage rec {
    pname = "gdsfactory";
    format = "pyproject";
    version = "8.7.3";
    
    buildInputs = [
        flit-core
      ];
  
    propagatedBuildInputs = [
        matplotlib
        numpy
        orjson
        pandas
        pydantic
        pydantic-settings
        pydantic-extra-types
        pyyaml
        qrcode
        rectpack
        rich
        scipy
        shapely
        toolz
        types-pyyaml
        typer
        kfactory
        watchdog
        freetype-py
        mapbox-earcut
        networkx
        #scikit-image
        trimesh-4_4_1
        ipykernel
        attrs
        jinja2
      ];
    
    src = fetchPypi {
      inherit pname version;
      sha256 = "sha256-F2XMb1bSlg3Psydp1rag7Z4jO9+o23d0EySDY4WhqbI=";
    };
    doCheck = false;

    postPatch = ''
      substituteInPlace pyproject.toml \
        --replace "\"scikit-image\"," ""
    '';
  };
  in
    self
