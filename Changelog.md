# 2.5.4

## Common

- `ngspice` tool:
  - Add `jobs` argument
  - Add `spiceinit_path` argument
  - By default copy the PDK spiceinit to the simulation directory
- `klayout_drc` tool:
  - Add `jobs` argument
  - Add `drc_script_path` argument
- Reserved variables:
  - Add `CACE{jobs}`
  - Add `CACE{root}`
- Issue a warning when a conditions has the same name as a reserved variable

# 2.5.3

## Common

- Add a simulation summary for the `ngspice` tool

# 2.5.2

## Common

- Add reserved variable `netlist_source`

# 2.5.1

## CLI

- Allow parameters to be specified via `--parameter` as a pattern
- Add `--skip-parameter` to skip certain parameters
  - Applied after parameters have been queued via `--parameter`
  - Also allows the use of patterns

# 2.5.0

## Common

- Implement custom scripts for the `ngspice` tool
  - `script` specifies the Python script
  - `script_variables` specifies the output variables
- Improve various error messages
- Variables in `collate` and `plot` entries can be specified with or without bit vectors (`[a:b]`). For now bit vectors are unused.
- A collate condition can still be used in a plot (but won't be displayed in the legend).

## Documentation

- Added a tutorial for custom scripts using the `ngspice` tool

# 2.4.14

## Common

- Implement plot limits
  - Plots have an optional argument `limits`, which can be `true`, `false` or `auto`

# 2.4.13

## Common

- Add `runs` path to datasheet
  - Specifies where the `runs` directory will be created

## CLI

- Add `--run-path` to arguments
  - Overrides `runs` path from datasheet

# 2.4.12

## Common

- Add `magic_antenna_check` as a tool
  - Performs antenna violation checks using magic
  - Returns `antenna_violations`, the number of violations that have occured

# 2.4.11

## Common

- Improve netlist regeneration:
  - Call `extract no all` when netlist source is layout
  - Use correct layout image names when GDS is compressed
  - Don't crash when GDS layout is not found

# 2.4.10

## Common

- Fix: Do not include broken links in the documentation if no layout is available

# 2.4.9

## Common

- Generate a gzip compressed GDS file from magic layout

# 2.4.8

## Common

- Use absolute path for layout

# 2.4.7

## Common

- Use `path search +path` in magic

# 2.4.6

## Common

- Improve layout detection
  - Fix `.gds.gz` handling
  - Unify codepaths for layout detection
  - Unify log messages during regeneration

# 2.4.5

## Common

- Improve plots
  - Sort minimum/typical/maximum labels
  - Connect points with the same condition on the x-axis
- Print when netlists do not need regeneration

# 2.4.4

## Common

- **Named results**
  - Tools generate named results
  - Spec entries apply per result
- **Named plots**
  - Enable multiple plots per paramter
- Improve documentation generation
  - Copy plots to the documentation directory and reference them in the Markdown

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
