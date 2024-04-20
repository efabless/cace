# 2.0.1

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