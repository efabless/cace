# 2.2.0

## CLI

- Simplify the code a lot
- Use the `SimulationManager`

## GUI

- Use the `SimulationManager`
- Simulations can now be stopped
- Only update row with simulation results

## Common

- Create the `SimulationManager` that owns the datasheet and performs the simulations
- `PhysicalParameter` - Class to manage evaluation of physical parameters
- `ElectricalParameter` - Class to manage evaluation of electrical parameters
- `SimulationJob` performs the simulation via ngspice

# 2.1.17

## CLI

- Use argparse

## GUI

- Use argparse

## Common

- Fixed two issues deemed "severe" [#47](https://github.com/efabless/cace/pull/47)