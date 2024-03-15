# Command Line Interface

CACE can be run directly from your command line:

	$ cace <filename_in> <filename_out> [options]

Where `<filename_in>` is a format 4.0 ASCII CACE file and `<filename_out>` is the name of the file to write.
Options may be one of:

	  -source=schematic|layout|rcx|all|best
	  -param=<parameter_name>
	  -force
	  -json
	  -keep
	  -debug
	  -sequential
	  -summary

When run from the top level, this program parses the CACE characterization file, runs simulations, and outputs a modified file annotated with characterization results.

With option `-source`, restrict characterization to the specific netlist source, which is either schematic capture,
layout extracted, or full R-C parasitic extracted. If not specified, then characterization is run on the full R-C
parasitic extracted layout netlist if available, and the schematic captured netlist if not (option "best").

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
