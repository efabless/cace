# 2.2.4

## Common

- Add `markdown_summary`

## CLI

- Call `markdown_summary` at the end and print to stdout
- Change `--summary` argument to print to file

# 2.2.3

## Common

- Improve scheduling of parameters
  - Simpler and more reliable
- Queued parameters can now be canceled

## GUI

- While a simulation is running, the netlist source cannot be changed

# 2.2.2

## Common

- Lower setuptools_scm requirement to >=7

# 2.2.0

# 2.2.1

## GUI

- Don't crash if no datasheet is found

# 2.2.0

## CLI

- Simplify the code a lot
- Use the `SimulationManager`

## GUI

- Use the `SimulationManager`
- Simulations can now be stopped
- Only update row with simulation results
- Added GUI option for `parallel_parameters`
- Fix setting limits in edit window

## Common

- Create the `SimulationManager` that owns the datasheet and performs the simulations
- `PhysicalParameter` - Class to manage evaluation of physical parameters
- `ElectricalParameter` - Class to manage evaluation of electrical parameters
- `SimulationJob` performs the simulation via ngspice
- Added runtime option `parallel_parameters`, determines how many parameters run in parallel
- Export `PDK_ROOT` for other tools

# 2.1.17

## CLI

- Use argparse

## GUI

- Use argparse

## Common

- Fixed two issues deemed "severe" [#47](https://github.com/efabless/cace/pull/47)