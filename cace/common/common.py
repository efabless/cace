# Copyright 2024 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess

from ..logging import (
    dbg,
    verbose,
    info,
    subproc,
    rule,
    success,
    warn,
    err,
)


def get_pdk(magicfilename=None):
    """
    Get a value for the PDK, as environment variable "PDK".
    """

    try:
        pdk = os.environ['PDK']
    except KeyError:
        error('PDK is not defined in the environment.')
        pdk = None

    return pdk


def get_pdk_root():
    """
    Get a value for PDK_ROOT, either from an environment variable, or
    from several standard locations (open_pdks install and IIC-tools
    install and volare install).
    If found, set the environment variable PDK_ROOT.
    """

    try:
        pdk_root = os.environ['PDK_ROOT']
    except KeyError:
        # Try a few common places where open_pdks might be installed
        pdk_root = '/usr/local/share/pdk'
        if not os.path.isdir(pdk_root):
            pdk_root = '/usr/share/pdk'
            if not os.path.isdir(pdk_root):
                pdk_root = '/foss/pdks'
                if not os.path.isdir(pdk_root):
                    pdk_root = os.path.join(os.path.expanduser('~'), '.volare')
                    if not os.path.isdir(pdk_root):
                        pdk_root = None

        if pdk_root:
            os.environ['PDK_ROOT'] = pdk_root
        else:
            error(
                'PDK_ROOT is not defined in the environment and could not automatically locate PDK_ROOT.'
            )

    return pdk_root


def get_magic_rcfile():
    """
    Get the path and filename of the magic startup script corresponding
    to the PDK.

    Returns a string containing the full path and filename of the startup
    script (.magicrc file).
    """

    pdk_root = get_pdk_root()
    pdk = get_pdk()

    rcfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'magic', pdk + '.magicrc'
    )

    return rcfile


def get_layout_path(projname, paths, check_magic=False):

    # Prefer magic layout
    if check_magic and 'magic' in paths:
        layout_path = paths['magic']
        layout_filename = projname + '.mag'
        layout_filepath = os.path.join(layout_path, layout_filename)

        dbg(f'Trying to find magic layout {layout_filepath}.')

        # Check if magic layout exists
        if os.path.isfile(layout_filepath):

            dbg(f'Found magic layout {layout_filepath}!')

            # Return magic layout
            return (layout_filepath, True)

        dbg('No magic layout found.')

    # Else use GDSII
    if 'layout' in paths:
        layout_path = paths['layout']
        layout_filename = projname + '.gds'
        layout_filepath = os.path.join(layout_path, layout_filename)

        dbg(f'Trying to find GDS layout {layout_filepath}.')

        # Check if GDS layout exists
        if os.path.exists(layout_filepath):

            dbg(f'Found GDS layout {layout_filepath}!')

            # Return GDS layout
            return (layout_filepath, False)

        dbg('No GDS layout found.')
        dbg('Trying to find compressed GDS layout.')

        layout_path = paths['layout']
        layout_filename = projname + '.gds.gz'
        layout_filepath = os.path.join(layout_path, layout_filename)

        # Check if compressed GDS layout exists
        if os.path.exists(layout_filepath):

            dbg(f'Found compressed GDS layout {layout_filepath}!')

            # Return compressed GDS layout
            return (layout_filepath, False)

        dbg('No compressed GDS layout found.')

    err('Neither magic nor (compressed) GDS layout found.')

    return (None, None)


def get_klayout_techfile():
    """
    Get the path and filename of the klayout tech file corresponding
    to the PDK.

    Returns a string containing the full path and filename of the tech
    file (.lyt file).
    """

    pdk_root = get_pdk_root()
    pdk = get_pdk()

    techfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'klayout', 'tech', pdk + '.lyt'
    )

    return techfile


def get_klayout_layer_props():
    """
    Get the path and filename of the klayout layer properties corresponding
    to the PDK.

    Returns a string containing the full path and filename of the layer
    properties (.lyp file).
    """

    pdk_root = get_pdk_root()
    pdk = get_pdk()

    techfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'klayout', 'tech', pdk + '.lyp'
    )

    return techfile


def get_netgen_setupfile():
    """
    Get the path and filename of the netgen setup script corresponding
    to the PDK.

    Returns a string containing the full path and filename of the setup
    script (.tcl file).
    """

    pdk_root = get_pdk_root()
    pdk = get_pdk()

    setupfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'netgen', pdk + '_setup.tcl'
    )

    return setupfile


def set_xschem_paths(datasheet, symbolpath, tclstr=None):
    """
    Put together a set of Tcl commands that sets the search
    path for xschem.

    If tclstr is not None, then it is assumed to be a valid
    Tcl command, and the rest of the Tcl command string is
    appended to it, with independent commands separated by
    semicolons.

    Return the final Tcl command string.

    Note that this is used only when regenerating the schematic
    netlist. The testbenches are assumed to call the symbol as
    a primitive, and rely on an include file to pull in the
    netlist (either schematic or layout) from the appropriate
    netlist directory.
    """

    paths = datasheet['paths']

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    # List of tcl commands to string together to make up the full
    # string argument to pass to xschem.

    tcllist = []
    if tclstr and tclstr != '':
        tcllist.append(tclstr)

    # Add the root path to the search path (may not be necessary but covers
    # cases where schematics have been specified from the project root for
    # either the testbench or schematic directories, or both).

    tcllist.append('append XSCHEM_LIBRARY_PATH :' + os.path.abspath(root_path))

    # Add the path with the DUT symbol to the search path.  Note that testbenches
    # use a version of the DUT symbol that is marked as "primitive" so that it
    # does not get added to the netlist directly.  The netlist is included by a
    # ".include" statement in the testbenches.
    tcllist.append('append XSCHEM_LIBRARY_PATH :' + symbolpath)

    # If dependencies are declared, then pull in their locations
    # and add them to the search path as well.

    # NOTE:  This depends on the setup of the dependent repository.
    # The code below assumes that there is a subdirectory 'xschem'
    # in the repository.  There needs to be a routine that recursively
    # determines schematic paths from the dependent repository's own
    # CACE definition file.

    if 'dependencies' in datasheet:
        # If there is only one dependency it may be a dictionary and not a
        # list of dictionaries.
        if isinstance(datasheet['dependencies'], dict):
            dependencies = [datasheet['dependencies']]
        else:
            dependencies = datasheet['dependencies']

        for dependency in dependencies:
            if 'path' in dependency and 'name' in dependency:
                dependdir = os.path.join(
                    dependency['path'], dependency['name'], 'xschem'
                )
                if not os.path.isdir(dependdir):
                    dependdir = os.path.join(
                        dependency['path'], dependency['name']
                    )
                    if not os.path.isdir(dependdir):
                        err(
                            'Cannot find xschem library in '
                            + dependency['name']
                        )
                        err('Current directory is: ' + os.getcwd())
                        err('Dependdir is: ' + dependdir)
                        dependdir = None
                if dependdir:
                    tcllist.append('append XSCHEM_LIBRARY_PATH :' + dependdir)

    return ' ; '.join(tcllist)


def xschem_generate_svg(schempath, svgpath):
    """
    Generate an SVG drawing of a schematic or symbol using xschem

    Return 0 if the drawing was generated, 1 if not.
    """

    if not os.path.isfile(schempath):
        err(f'Could not find {schempath}.')
        return 1

    # Xschem arguments:
    # -r:  Bypass readline (because stdin/stdout are piped)
    # -x:  No X11 / No GUI window
    # -q:  Quit after processing command line

    xschemargs = [
        '-r',
        '-x',
        '-q',
        '--svg',
        '--plotfile',
        svgpath,
    ]

    pdk_root = get_pdk_root()
    pdk = get_pdk()

    # See if there is an xschemrc file  we can source
    xschemrcfile = os.path.join(os.path.split(schempath)[0], 'xschemrc')
    if os.path.isfile(xschemrcfile):
        xschemargs.extend(['--rcfile', xschemrcfile])
    else:
        warn(f'No project xschemrc file found at: {xschemrcfile}')
        warn(
            f'It is highly recommended to set up an xschemrc file for your project.'
        )

        # Use the PDK xschemrc file for xschem startup
        xschemrcfile = os.path.join(
            pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
        )
        warn(f'Using the PDK xschemrc instead…')
        if os.path.isfile(xschemrcfile):
            xschemargs.extend(['--rcfile', xschemrcfile])
        else:
            err(f'No xschemrc file found in the {pdk} PDK!')

    xschemargs.append(schempath)

    dbg('Generating SVG using xschem.')

    returncode = run_subprocess('xschem', xschemargs, write_file=False)

    if returncode != 0:
        return 1

    return 0


def magic_generate_svg(layout_path, svgpath):
    """
    Generate an SVG drawing of a layout using magic

    Return 0 if the drawing was generated, 1 if not.
    """

    if not os.path.isfile(layout_path):
        err(f'Could not find {layout_path}.')
        return 1

    layout_directory = os.path.split(layout_path)[0]
    layout_filename = os.path.split(layout_path)[1]
    layout_cellname = os.path.splitext(layout_filename)[0]
    layout_extension = os.path.splitext(layout_filename)[1]

    rcfile = get_magic_rcfile()

    magic_input = ''

    magic_input += f'addpath {os.path.abspath(layout_directory)}\n'
    if layout_extension == '.mag':
        magic_input += f'load {layout_filename}\n'
    elif layout_extension == '.gds':
        magic_input += f'gds read {layout_filename}\n'
        magic_input += f'load {layout_cellname}\n'
    else:
        err(f'Unknown file extension for: {layout_path}')
        return 1

    magic_input += f'plot svg {svgpath}\n'

    returncode = run_subprocess(
        'magic',
        ['-noconsole', '-d XR', '-rcfile', rcfile],
        input=magic_input,
        write_file=False,
    )

    if returncode != 0:
        return 1

    return 0


def klayout_generate_png(layout_filepath, out_path, out_name):
    """
    Generate a PNG drawing of a layout using klayout

    Return 0 if the drawing was generated, 1 if not.
    """

    if layout_filepath == None:
        err(f'No layout found.')
        return 1

    if not os.path.isfile(layout_filepath):
        err(f'Could not find {layout_filepath}.')
        return 1

    layout_directory = os.path.dirname(layout_filepath)
    layout_filename = os.path.basename(layout_filepath)

    techfile = get_klayout_techfile()
    layer_props = get_klayout_layer_props()
    pdk = get_pdk()

    if pdk == 'sky130A':
        tech_name = 'sky130'
    elif pdk == 'sky130B':
        tech_name = 'sky130'
    else:
        tech_name = pdk

    klayout_script = """import pya
import os

# Input:
# gds_path: path to the gds file
# out_path: output directory
# out_name: output name
# w: width

if not 'w' in globals():
    w = 1024

background_white = "#FFFFFF"
background_black = "#000000"

lv = pya.LayoutView()

lv.set_config("grid-visible", "false")
lv.set_config("grid-show-ruler", "false")
lv.set_config("text-visible", "false")
tech = pya.Technology.technology_by_name(tech_name)
lv.load_layout(gds_path, tech.load_layout_options, tech_name)
lv.max_hier()

ly = lv.active_cellview().layout()

# top cell bounding box in micrometer units
bbox = ly.top_cell().dbbox()

# compute an image size having the same aspect ratio than 
# the bounding box
h = int(0.5 + w * bbox.height() / bbox.width())

lv.load_layer_props(layer_props)

lv.set_config("background-color", background_white)
lv.save_image_with_options(os.path.join(out_path, out_name + "_w.png"), w, h, 0, 0, 0, bbox, False)

lv.set_config("background-color", background_black)
lv.save_image_with_options(os.path.join(out_path, out_name + "_b.png"), w, h, 0, 0, 0, bbox, False)"""

    scriptpath = 'klayout_script.py'

    with open(scriptpath, 'w') as f:
        f.write(klayout_script)

    # -b: batch mode
    # -nn: tech file
    # -r: script
    # -rd <name>=<value>: script variable

    returncode = run_subprocess(
        'klayout',
        [
            '-b',
            '-nn',
            techfile,
            '-r',
            scriptpath,
            '-rd',
            f'gds_path={layout_filepath}',
            '-rd',
            f'out_path={out_path}',
            '-rd',
            f'out_name={out_name}',
            '-rd',
            f'tech_name={tech_name}',
            '-rd',
            f'layer_props={layer_props}',
        ],
        write_file=False,
    )

    # Delete script after use
    if os.path.isfile(scriptpath):
        os.remove(scriptpath)

    if returncode != 0:
        return 1

    return 0


# -----------------------------------------------------------------------
# floating-point linear numeric sequence generator, to be used with
# condition generator
# -----------------------------------------------------------------------


def linseq(start, stop, step):
    a = start
    e = stop
    s = step
    while a < e + s:
        if a > e:
            yield stop
        else:
            yield a
        a = a + s


# -----------------------------------------------------------------------
# floating-point logarithmic numeric sequence generator, to be used with
# condition generator
# -----------------------------------------------------------------------


def logseq(start, stop, step):
    a = start
    e = stop
    s = step
    while a < e * s:
        if a > e:
            yield stop
        else:
            yield a
        a = a * s


# -----------------------------------------------------------------------
# binary (integer) numeric sequence generators, to be used with
# condition generator
# -----------------------------------------------------------------------


def bindigits(n, bits):
    s = bin(n & int('1' * bits, 2))[2:]
    return ('{0:0>%s}' % (bits)).format(s)


# -----------------------------------------------------------------------
# compute the 2's compliment of integer value val
# -----------------------------------------------------------------------


def twos_comp(val, bits):
    if (
        val & (1 << (bits - 1))
    ) != 0:   # if sign bit is set e.g., 8bit: 128-255
        val = val - (1 << bits)        # compute negative value
    return val                         # return positive value as is


# -----------------------------------------------------------------------
# Binary sequence counter (used for linear stepping of binary vectors)
# -----------------------------------------------------------------------


def bcount(condition, unit, start, stop, step):
    blen = len(start)
    a = safe_eval('0b' + start)
    e = safe_eval('0b' + stop)
    if a > e:
        a = twos_comp(a, blen)
        e = twos_comp(e, blen)
    s = int(step)
    while a < e + s:
        if a > e:
            bstr = bindigits(e, blen)
        else:
            bstr = bindigits(a, blen)
        yield (condition, unit, bstr)
        a = a + s


# -----------------------------------------------------------------------
# Binary sequence shifter (used for logarithmic stepping of binary
# vectors)
# -----------------------------------------------------------------------


def bshift(condition, unit, start, stop, step):
    a = safe_eval('0b' + start)
    e = safe_eval('0b' + stop)
    if a > e:
        a = twos_comp(a, blen)
        e = twos_comp(e, blen)
    s = int(step)
    while a < e * s:
        if a > e:
            bstr = bindigits(e, blen)
        else:
            bstr = bindigits(a, blen)
        yield (condition, unit, bstr)
        a = a * s


# -----------------------------------------------------------------------
# Read a template file and record all of the variable names that will
# be substituted, so it is clear which local and global conditions
# need to be enumerated.  Vectors are reduced to just the vector name.
#
# Returns a dictionary with keys corresponding to condition names;
# the dictionary values are unused and just set to "True".
# -----------------------------------------------------------------------


def get_condition_names_used(template):

    if not os.path.isfile(template):
        err('No such template file ' + template)
        return

    with open(template, 'r') as ifile:
        simtext = ifile.read()

    simlines = simtext.splitlines()
    condlist = {}

    # Regular expressions
    # varex:		variable name {name}
    varex = re.compile(r'\{([^ \}\t]+)\}')

    # Vectors in name[number|range] format
    vectrex = re.compile(r'([^\[]+)\[([0-9:]+)\]')

    # List for {cond=value} syntax
    default_cond = {}

    for line in simlines:
        for patmatch in varex.finditer(line):
            pattern = patmatch.group(1)

            # For condition names in the form {cond=value}, use only the name
            if '=' in pattern:
                (pattern, default) = pattern.split('=')
                # Add the default value
                default_cond[pattern] = default

            # For condition names in the form {cond|value}, use only the name
            if '|' in pattern:
                pstart = pattern.split('|')[0]
                if pstart != 'PIN' and pstart != 'FUNCTIONAL':
                    pattern = pstart

            pmatch = vectrex.match(pattern)
            if pmatch:
                pattern = pmatch.group(1) + '['
            condlist[pattern] = True

    return (condlist, default_cond)


def run_subprocess(
    proc, args=[], env=None, input=None, cwd=None, write_file=True
):

    if not cwd:
        cwd = os.getcwd()

    dbg(
        f'Subprocess {proc} {" ".join(args)} at \'[repr.filename][link=file://{os.path.abspath(cwd)}]{os.path.relpath(cwd)}[/link][/repr.filename]\'…'
    )

    with subprocess.Popen(
        [proc] + args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if input else subprocess.DEVNULL,
        env=env,
        text=True,
    ) as process:

        dbg(input)
        stdout, stderr = process.communicate(input)
        returncode = process.returncode

        if returncode != 0:
            err(f'Subprocess exited with error code {returncode}')

        # Print stderr
        if stderr and returncode != 0:
            err('Error output generated by subprocess:')
            for line in stderr.splitlines():
                err(line.rstrip('\n'))
        else:
            dbg('Error output generated by subprocess:')
            for line in stderr.splitlines():
                dbg(line.rstrip('\n'))

        # Write stderr to file
        if stderr and write_file:
            with open(
                f'{os.path.join(cwd, proc)}_stderr.out', 'w'
            ) as stderr_file:
                stderr_file.write(stderr)

        # Print stdout
        if stdout:
            dbg(f'Output from subprocess {proc}:')
            for line in stdout.splitlines():
                dbg(line.rstrip())

        # Write stdout to file
        if stdout and write_file:
            with open(
                f'{os.path.join(cwd, proc)}_stdout.out', 'w'
            ) as stdout_file:
                stdout_file.write(stdout)

    return returncode
