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
    Get a value for the PDK, either from the second line of a .mag file,
    or from the environment as environment variable "PDK".

    NOTE:  Normally the PDK is provided as part of the datasheet, as
    a project does not necessarily have a .mag file;  so there is no
    source for automatically determining the project PDK.
    """
    if magicfilename and os.path.isfile(magicfilename):
        with open(magicfilename, 'r') as ifile:
            for line in ifile.readlines():
                tokens = line.split()
                if tokens[0] == 'tech':
                    pdk = tokens[1]
                    break
    else:
        try:
            pdk = os.environ['PDK']
        except KeyError:
            error('No .mag file and PDK is not defined in the environment.')
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
            error('Could not locate PDK_ROOT!')

    return pdk_root


def get_magic_rcfile(datasheet, magicfilename=None):
    """
    Get the path and filename of the magic startup script corresponding
    to the PDK.

    Returns a string containing the full path and filename of the startup
    script (.magicrc file).
    """

    if 'PDK_ROOT' in datasheet:
        pdk_root = datasheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in datasheet:
        pdk = datasheet['PDK']
    elif magicfilename:
        pdk = get_pdk(magicfilename)
    else:
        paths = datasheet['paths']
        if magicfilename:
            pdk = get_pdk(magicfilename)
        elif 'magic' in paths:
            magicpath = paths['magic']
            magicfilename = os.path.join(magicpath, magicname)
            pdk = get_pdk(magicfilename)
        else:
            return None

    rcfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'magic', pdk + '.magicrc'
    )
    return rcfile


def get_netgen_setupfile(datasheet):
    """
    Get the path and filename of the netgen setup script corresponding
    to the PDK.

    Returns a string containing the full path and filename of the setup
    script (.tcl file).
    """

    if 'PDK_ROOT' in datasheet:
        pdk_root = datasheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in datasheet:
        pdk = datasheet['PDK']
    elif magicfilename:
        pdk = get_pdk(magicfilename)
    else:
        paths = datasheet['paths']
        if 'magic' in paths:
            magicpath = paths['magic']
            magicfilename = os.path.join(magicpath, magicname)
            pdk = get_pdk(magicfilename)
        else:
            return None

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


def run_subprocess(proc, args=[], env=None, input=None, cwd=None):

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
        if stderr:
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
        if stdout:
            with open(
                f'{os.path.join(cwd, proc)}_stdout.out', 'w'
            ) as stdout_file:
                stdout_file.write(stdout)

    return returncode
