# Getting Started

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

