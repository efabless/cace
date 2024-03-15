<h1 align="center">CACE</h1>
<h2 align="center">Circuit Automatic Characterization Engine</h2>
<p align="center">
    <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"/></a>
    <img src="https://github.com/efabless/cace/actions/workflows/ci.yaml/badge.svg?branch=main" alt="GitHub Actions Status Badge" />
    <a href="https://cace.readthedocs.io/"><img src="https://readthedocs.org/projects/cace/badge/?version=latest" alt="Documentation Build Status Badge"/></a>
    <a href="https://www.python.org"><img src="https://img.shields.io/badge/Python-3.8-3776AB.svg?style=flat&logo=python&logoColor=white" alt="Python 3.8 or higher" /></a>
    <a href="https://github.com/grantjenks/blue"><img src="https://img.shields.io/badge/code%20style-blue-blue.svg" alt="Code Style: blue"/></a>
</p>
<p align="center">
    <a href="https://invite.skywater.tools"><img src="https://img.shields.io/badge/Community-Open%20Source%20Silicon%20Slack-ff69b4?logo=slack" alt="Invite to the Open Source Silicon Slack"/></a>
</p>

CACE is a set of python scripts that take an input file in the
CACE 4.0 format and uses the information found there in combination with CACE-compatible testbenches and analysis scripts to characterize a circuit and to produce a datasheet showing the circuit performance.

## Installation

You'll need the following:

- Python 3.8 or higher with PIP and Tkinter

CACE can be installed directly from PyPI:

	$ python3 -m pip install --upgrade cace
Prerequisite design tools:

- xschem:  [https://github.com/stefanschippers/xschem](https://github.com/stefanschippers/xschem)
- ngspice: git://git.code.sf.net/p/ngspice/ngspice
- magic:	 [https://github.com/RTimothyEdwards/magic](https://github.com/RTimothyEdwards/magic)

## Usage

If installed as Python package, CACE can be started from the command line using:

```
$ cace
```

Or to start the GUI:

```
$ cace-gui
```

Information on how to use CACE can be found in the documentation at [cace.readthedocs.io](https://cace.readthedocs.io/). 

## Development

### Dependencies

> [!IMPORTANT]
> You may need to set up a Python [virtual environment](https://docs.python.org/3/library/venv.html).

To install the dependencies for CACE, run:

	$ make dependencies

### Python Package

To build the Python package, run:

```
$ make build
```

To install the package, run:

```
$ make install
```

To install the package in editable mode, run:

```
$ make editable
```

### Documentation

To build the documentation, run:

```
$ make docs
```

To host the docs, run:

```
make host-docs
```

To automatically refresh the docs upon changes, run:

```
make auto-docs
```

> [!NOTE]
> The latest documentation can be viewed online at [cace.readthedocs.io](https://cace.readthedocs.io/). 

## Examples

The following repositories contain example circuit designs, each having a "cace/" subdirectory with a specification input file in the format described below, and a set of testbench schematics which are used by CACE to measure all specified electrical and physical parameters, generate results, and analyze them to determine circuit performance over corners.

> [!NOTE]
> Example repositories, like CACE itself, are currently a work in progress.

All repositories are rooted at: [https://github.com/RTimothyEdwards/](https://github.com/RTimothyEdwards/).

Example circuit repositories:

- [sky130_ef_ip__instramp](https://github.com/RTimothyEdwards/sky130_ef_ip__instramp)		Instrumentation amplifier
- [sky130_ef_ip__rdac3v_8bit](https://github.com/RTimothyEdwards/sky130_ef_ip__rdac3v_8bit)	8-bit resistor ladder DAC
- sky130_ef_ip__samplehold	sample-and-hold circuit
- sky130_ef_ip__driveramp		Rail-to-rail driver amplifier
- sky130_ef_ip__ccomp3v		Rail-to-rail continuous comparator
- sky130_ef_ip__rc_osc_500k	R-C oscillator, 500kHz nominal output
- sky130_ef_ip__xtal_osc_16M	Crystal oscillator, 4 to 15MHz
- sky130_ef_ip__xtal_osc_32k	Crystal oscillator, 32kHz

Each of these repositories contains a circuit designed with the SkyWater sky130 process open PDK, and contains schematics, layout, and CACE characterization.

> [!NOTE]
> These repositories are a work in progress, and may not exist yet or may not have a characterization setup for CACE.
