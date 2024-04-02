# Command Line Interface

CACE can be run directly from your command line:

	$ cace <filename_in> [<filename_out>] [options]

Where `<filename_in>` is a format 4.0 ASCII CACE file and `<filename_out>` is the name of the file to write.
Options may be one of:

```
--source=schematic|layout|rcx|all|best
--param=<parameter_name> <parameter_name> ...
--force
--json
--keep
--debug
--sequential
--no-simulation
--summary
```

When run from the top level, this program parses the CACE characterization file, runs simulations, and outputs a modified file annotated with characterization results.

With option `-source`, restrict characterization to the specific netlist source, which is either schematic capture,
layout extracted, or full R-C parasitic extracted. If not specified, then characterization is run on the full R-C
parasitic extracted layout netlist if available, and the schematic captured netlist if not (option "best").

```
positional arguments:
  datasheet             format 4.0 ASCII CACE file
  outfile               name of the file to write

options:
  -h, --help            show this help message and exit
  -s {schematic,layout,rcx,all,best}, --source {schematic,layout,rcx,all,best}
                        restricts characterization to the specific netlist source, which is either schematic
                        capture layout extracted, or full R-C parasitic extracted. If not specified, then
                        characterization is run on the full R-C parasitic extracted layout netlist if available,
                        and the schematic captured netlist if not (option "best")
  -p PARAMETER [PARAMETER ...], --parameter PARAMETER [PARAMETER ...]
                        runs simulations on only the named electrical or physical parameters, by default it runs
                        all parameters
  -f, --force           forces new regeneration of all netlists
  -j, --json            generates an output file in JSON format
  -k, --keep            retains files generated for characterization
  --no-plot             do not generate any graphs
  --debug               generates additional diagnostic output
  --sequential          runs simulations sequentially
  --no-simulation       does not re-run simulations if the output file exists. (Warning: Does not check if
                        simulations are out of date)
  --summary             prints a summary of results at the end
```
