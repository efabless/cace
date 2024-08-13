# 2.4.3

## Common

- **New format for CACE substitutions**
    - `CACE{condition}` and `CACE[expression]`
    - Fallback for datasheet version <= 5.0
- Export the schematic netlist with `top_is_subckt` enabled, which preserves certain spice parameters. This improves the simulation accuracy compared to layout extracted.
- Fix for layout extraction: Reload the top cell after `readspice`

# 2.4.2

## Common

- Do not perform substitutions if the conditions is not defined.

# 2.4.1

## CLI

- After successful execution of CACE, the documentation is generated under the specified path "documentation"
  - Generate Markdown summary of the design
  - Generate Markdown summary of the results
  - Export the symbol as SVG
  - Export the schematic as SVG
  - Export the layout as PNG
- Added `--nofail` argument

# 2.4.0

## Common

- Major rewrite of tool implementations:
    * Each tool inherits from the `Parameter` class
    * Behavior is implemented by overwriting methods
    * Registered via `@register_parameter`
- Unified `physical_parameters` and `electrical_parameters` to `parameters`
- Each parameter and each simulation run of a parameter (e.g. `ngspice`) has their own subfolder
- Rewrite of the result handling
- Rewrite of plotting
- Added the `klayout_drc` tool
- GDSII will be automatically generated from mag files
  - Tools using magic will prefer mag files

## CLI

- Remove `--keep` argument since all files are kept under `run/`
- Added `--save` argument to save the summary upon successful completion
- Cancel run with Ctrl+C

## GUI

- Temporarily disable the GUI until it can be revised with the current changes

# 2.3.11

## Common

- Bugfix: Do not crash if certain entries are missing from authorship
- Improvement: Allow to specify `'null'` as `null`

# 2.3.10

## Common

- Improve the .txt to .yaml conversion: export numbers as integers or float

# 2.3.9

## Common

- Fix paths in default LVS setup

# 2.3.8

## GUI

- Added `--max-runs` to limit the maximum number of runs in the run folder

## CLI

- Print the total runtime after completion
- Removed `--no-simulation` as the output files never exist in a new timestamp
- Renamed `--parallel_parameters` to `--parallel-parameters`
- Added `--max-runs` to limit the maximum number of runs in the run folder

# 2.3.7

## Common

- Add support for the `-j`/`--jobs` flag to limit the maximum number of jobs running in parallel
- Parallelized simulations with collated conditions (Monte Carlo for example)

# 2.3.6

## Common

- Do not generate testbench netlists in parallel, this leads to race conditions

# 2.3.5

## Common

- Improve netlist generation
    * Schematic netlist is always generated to get the correct port order for the extracted netlists

# 2.3.4

## Common

- Abort early if netlist generation fails

# 2.3.3

## Common

- Add a new logging system (adopted from OpenLane 2)
- Store output under `run/timestamp/`
- New recommended design directory structure
- Add support for `{cond=value}`

# 2.3.2

## Common

- Add portability checks for paths. Warn the user:
     - If there are any paths containing `libs.tech`
       or `libs.ref` that are not using `{PDK_ROOT}`
     - If the path has the user's $HOME as a leading component

# 2.3.1

## Common

- Add [Rich](https://github.com/Textualize/rich) as dependency
- Pass `--batch` to ngspice, to exit simulations after they are done

## CLI

- Add a progress bar
- Render the Markdown of the summary
- Bugfix: Show a fail in the summary if a simulation fails

# 2.3.0

## Common

- Remove JSON datasheet format
- Add YAML datasheet format, set as default
- Remove cli interface from `cace_read.py` and `cace_write.py`

## GUI

- Remove `JSON` in the file picker
- Add `YAML` to the file picker
- Remove bit-rotted `load_results`

## CLI

- Remove `--json` argument

# 2.2.7

## Common

- Improve extraction with only a GDS file

# 2.2.6

## Common

- Restored functionality of `sequential` runtime option

# 2.2.5

## CLI

- Add `--version` argument

## GUI

- Add `--version` argument

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
