# Graphical User Interface

CACE has also support for a graphical user interface, started via:

    $ cace-gui [path/to/project.txt]

Where optional file `project.txt` (normally `<name_of_project>.txt` where `<name_of_project>` is the name of the circuit to be
characterized) is a circuit characterization description in the file format described below.  If a file is not specified, then
the GUI window will come up without content.  Click on the button with text `(no selection)` to find and select a characterization
file to load. The project file may also be in JSON format.

Normally, `cace_gui.py` is called from a project top level directory, while the project.txt file is usually in a subdirectory called
cace/. The `project.txt` file may be the output file from a CACE run, which will add results to all of the parameter entries.

There may be multiple characterization files in a single project (repository), as a project may contain multiple subcircuits that
may need independent characterization or be able to be used as standalone circuits, or a project may simply be a collection of
circuits (library) without a specific single top level.

![CACE GUI Screenshot](../_static/cace_screenshot.png)
