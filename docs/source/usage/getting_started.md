# Getting Started

## Installation

For now, CACE can be manually installed using pip.

First the Python package needs to be build:

```
$ make build
```

To install the package, run:

```
$ make install
```

CACE is currently a work in progress and does not have an
installer;  it may be run directly from the source repository
clone.  Future work will allow CACE to be installed with the
standard python "pip" installer or a Makefile install target,
and run from the command line simply as "cace".

## Usage

If installed properly as Python package, CACE can be started from the command line using:

```
$ cace
```

Or to start the GUI:

```
$ cace-gui
```


The `cace_gui.py` script is a top-level GUI for the CACE system. The CACE system can also be run manually as `cace_cli.py`. For
interactive usage information for the command line, run `cace-cli.py` without any arguments.

CACE GUI syntax:

	/path/to/cace_gui.py [path/to/project.txt]

	where optional file project.txt (normally <name_of_project>.txt
	where <name_of_project> is the name of the circuit to be
	characterized) is a circuit characterization description in the
	file format described below.  If a file is not specified, then
	the GUI window will come up without content.  Click on the button
	with text "(no selection)" to find and select a characterization
	file to load.  The project file may also be in JSON format.

	Normally, cace_gui.py is called from a project top level directory,
	while the project.txt file is usually in a subdirectory called
	cace/.  The project.txt file may be the output file from a CACE
	run, which will add results to all of the parameter entries.

	There may be multiple characterization files in a single project
	(repository), as a project may contain multiple subcircuits that
	may need independent characterization or be able to be used as
	standalone circuits, or a project may simply be a collection of
	circuits (library) without a specific single top level. 

CACE command line syntax:

	/path/to/cace.py <filename_in> <filename_out> [options]

	where <filename_in> is a format 4.0 ASCII CACE file
	and <filename_out> is the name of the file to write.

	Options may be one of:

	  -source=schematic|layout|rcx|all|best
	  -param=<parameter_name>
	  -force
	  -json
	  -keep
	  -debug
	  -sequential
	  -summary

	When run from the top level, this program parses the CACE
	characterization file, runs simulations, and outputs a
	modified file annotated with characterization results.

	With option "-source", restrict characterization to the
	specific netlist source, which is either schematic capture,
	layout extracted, or full R-C parasitic extracted.  If not
	specified, then characterization is run on the full R-C
	parasitic extracted layout netlist if available, and the
	schematic captured netlist if not (option "best").

	Option "-param=<parameter_name>" runs simulations on only
	the named electrical or physical parameter.

	Option "-force" forces new regeneration of all netlists.

	Option "-json" generates an output file in JSON format.

	Option "-keep" retains files generated for characterization.

	Option "-noplot" will not generate any graphs.

	Option "-debug" generates additional diagnostic output.

	Option "-sequential" runs simulations sequentially.

	Option "-nosim" does not re-run simulations if the output file exists.
	   (Warning---does not check if simulations are out of date).

	Option "-summary" prints a summary of results at the end.