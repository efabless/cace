# Template Format

Schematics are drawn normally but statements can have special syntax
that is substituted by CACE. The syntax follows three essential rules:

1. Condition and variable names in the project specification file
    are written in the schematic in braces prefixed with "CACE", so "temperature" in the
    project file is "CACE{temperature}" in the schematic.

2. Expressions involving equations using condition and variable
    names are written in the schematic in brackets prefixed with "CACE", so, for example,
    half of condition vdd would be written "CACE[CACE{vdd} / 2]". These
    expressions are evaluated in python, so any arithmetic python expression
    that evaluates to a valid result may appear inside the brackets.

3. There are a handful of reserved variable names that are automatically
    substituted by CACE if they appear in the schematic:

- `CACE{filename}`
	
    > The root name of the schematic file.

- `CACE{simpath}`
	
	> The name of the path to simulation files.

- `CACE{DUT_path}`
	
	> The full path to the DUT subcircuit definition netlist.

- `CACE{DUT_name}`
	
	> The name of the DUT subcircuit

- `CACE{netlist_source}`
	
	> The current netlist source such as: schematic, layout, pex or rcx.

- `CACE{PDK_ROOT}`
	
	> The path to the directory containing the PDK

- `CACE{PDK}`
	
	> The name of the PDK

- `CACE{N}`
    	
	> This is substituted with the simulation index.  Most often
	used as a filename suffix for the output data file.

- `CACE{random}`
	
	> A random integer number.

- `CACE{cond=value}`
	
		For any condition cond, this form indicates that "value" is
		to be subsituted for the condition if the condition is not
		declared in the CACE project file.

- `CACE{cond|minimum}` `{cond|maximum}` `{cond|stepsize}` `{cond|steps}`
	
	> Instead of substituting one value for a condition, a value
	over all conditions is substituted, including the maximum
	over all conditions, minimum over all conditions, the
	step size between neighboring condition values, or the
	number of steps over all values of the condition.
	This is used most often in cases where a condition is handled
	entirely inside a testbench netlist (such as in a sweep), and
	not iterated over multiple netlists.

<!---

## Planned support

- `{PIN|pin_name|net_name}`
	
    > Used in symbol descriptions.  Indicates a pin of a subcircuit
    including both the pin name in the subcircuit and the name
    of the net connecting to the pin.  This allows a subcircuit
    call to be made without any specific pin order.  CACE will
    determine the pin order and output the correct syntax.

- `{FUNCTIONAL|ip_name}`
	
		Indicates that the subcircuit ip_name will be replaced with
		its functional view (xspice or verilog) for simulation.

-->
