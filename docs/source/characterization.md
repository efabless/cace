# Characterization

## Selecting a datasheet

Start by selecting a datasheet. This step is only necessary if the application is started from the command line.

%If started from the project manager, then it can only be run if a datasheet exists for the project, in which case that datasheet is automatically loaded.

If running from the command line, there is a button at the top with the text `Datasheet:` and `(no selection)`. Push this button to get a file browser. Find a project datasheet, which is a text (`.txt`) file.  A challenge datasheet should be found in the design folder for each accepted challenge.

%The project design folders are in the `design` subfolder in the user's home directory.

The challenge datasheet has the name of the project and the file extension `.txt`

When the JSON file is selected, a full display should be shown with each electrical parameter critical to the challenge, and its status.

## Characterization

The purpose of the characterization tool is to check the netlist against the official characterization specification for a circuit. The tool allows a quick check of the circuit design against the datasheet specification values, and presents a summary of results to the user. The purpose of these simulations is to see whether or not the design will pass or fail the specification. Details from these simulations are limited to the characterization values. They are not intended to replace the simulations done in the normal course of a circuit design.

The list of electrical parameters will vary by the type of design. However, each electrical paramater has a common set of properties that are listed in columns across the window. These are:

1. "Parameter" --- The name of the electrical or physical parameter.
2. "Testbench" --- The testbench corresponds to a netlist filename with the extension ".spice" (SPICE netlist) that can be found in the "cace" folder of the project (or the "testbench" path declared in the characterization file).  The testbench netlists are in a special format that allows them to be altered by substitution for a specific measurement.
3. "Min" --- The minimum limit (if any) of the electrical parameter.  After simulation, also shows the measured result of the circuit.
4. "Typ" --- The typical value (if any) of the electrical parameter.  After simulation, also shows the measured result of the circuit.
5. "Max" --- The maximum limit (if any) of the electrical parameter.  After simulation, also shows the measured result of the circuit.
6. "Status" --- Is one of "(not checked)" if the circuit has not yet been simulated, "(in progress)" if the simulation is ongoing;  "pass" if the circuit has been simulated and passed the specification for the eletrical parameter, and "fail" if it failed the specification.   If the status is "pass" or "fail", this entry is a button that can be pressed to see a detailed view of the results.
7. "Simulate" --- This is a button that will initiate an ngspice simulation of the electrical parameter.

At the bottom of the window is a space for program messages, warnings, and errors.  Below that is a button bar with the following buttons:

- "Close" --- Quits the characterization tool.  If new results have been simulated but not saved, the user will have to respond to a prompt.
- "Save" --- Saves the current characterization results.  These results will be loaded the next time the characterization tool is run, unless there is a design netlist newer than the saved results.
- "Help" --- Activates this help window.
- "Settings" --- Controls global settings for CACE.

    The available settings are:

	- Print debug output ---
		    Produce additional output for diagnostic and debugging purposes.
	- Force netlist regeneration ---
		    Require netlists to be regenerated for every simulation.  Otherwise,
		    netlists are only regenerated when the source file (schematic or layout)
		    is found to post-date the netlist.
	- Allow edit of all parameters ---
		    Allow the use of "Simulate-->Edit", which provides a method for in-app
		    editing and copying of parameters (note that the characterization file
		    itself may always be edited).
	- Simulate single-threaded ---
		    Normally all simulations are done multi-threaded (with low priority).
		    Selecting this option forces simulations to run one at a time.
	- Keep simulation files ---
		    Normally simulation files are removed after simulation and only the
		    results are kept.  This option forces the files to remain after
		    simulation.
	- Do not create plot files ---
		    Normally plot files are generated for each plot.  If this option is
		    selected, plots may be viewed in-app but no file is generated.
	- Log simulation output ---
		    Copy all simulation output into a log file.
	

At the top of the window is the name and location of the datasheet, and on the right is a button that indicates what the source of the netlist being simulated is. The netlist source can be one of the following choices:

- **Schematic Capture**:  Simulations are done from schematic
- **Layout Extracted**:   Simulations are done from layout without parasitics
- **R-C Extracted**:      Simulations are done from layout with parasitics

Separate results are maintained for each of these source cases. Proper sign-off characterization of a circuit should be done with a netlist from an R-C extracted layout.

### Generating a netlist


Design your project schematic in a directory called "xschem" (or the path declared for "schematic" in the characterization file) using the xschem schematic tool. See the xschem user manual and tutorials for details. The netlist is generated automatically when running simulations in CACE.

### Simulation

To simulate a single electrical parameter, click the `Simulate` button for each electrical parameter. Pressing the button creates a drop-down menu with the choices:

	Run
	Stop
	Edit
	Copy

Left-click on the selection to initiate it.

- **Run:**
This will combine the design netlist with a testbench, simulate using ngspice, collate results, and display the resulting margin values. While ngspice is running, the `Simulate` button says `(in progress)`.

- **Stop:**
If a testbench is running, then selecting "Stop" will end the simulations.

- **Edit:**
This allows a testbench definition to be edited through the GUI, to modify the conditions of simulation. Note that the characterization definition file is text and can also be modified directly with an editor. Note that parameters are not editable by default. Go to "Settings" and select "Allow edit of all parameters" to allow parameters to be edited.

- **Copy:**
This creates a new parameter that is a copy of the one selected. The new parameter can then be edited to simulate under a different set of conditions. This can also be done by directly modifying the characterization definition file with a text editor.

### Results

Every electrical parameter is specified over a range of conditions. This results in a series of simulations, usually one simulation run per unique set of conditions. Each simulation typically provides one result value, and the set of all values from all simulated conditions is used to find the minimum, typical, and maximum results that are printed on the main characterization page.

When an electrical parameter has finished simulating, clicking on the "Status" entry will generate a window showing details of the simulation. The window has one line per unique set of conditions simulated.  For each line, the result value is given in the leftmost column. The remaining columns show each variable condition, and the value it had for the given simulation.  The top of the column shows the range of values for the given parameter. This graph allows the user to quickly determine what are the conditions under which a circuit may be failing, and the degree to which the value is out of range of the specification. Rows in which the result is outside of the specified limit are shown in red.

In the results window, click on the title `Results` to change the view from having results ordered highest to lowest, to lowest to highest. Click on the name (column header) of any condition or variable to change the tabular view to a graph showing results vs. the selected condition or variable.

