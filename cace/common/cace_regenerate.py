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
"""
These procedures are used by cace_gensim to check if netlists need
to be automatically regenerated, and to run schematic capture or
layout extraction as needed.
"""

import os
import sys
import re
import shutil
from datetime import date as datetime
import subprocess

from .common import (
    get_pdk,
    get_pdk_root,
    get_magic_rcfile,
    set_xschem_paths,
    get_layout_path,
    run_subprocess,
)
from .misc import mkdirp

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


def printwarn(output):
    """Print warnings output from a file run using the subprocess package"""
    # Check output for warning or error
    if not output:
        return 0

    failrex = re.compile(r'.*failure', re.IGNORECASE)
    warnrex = re.compile(r'.*warning', re.IGNORECASE)
    errrex = re.compile(r'.*error', re.IGNORECASE)
    missrex = re.compile(r'.*not found', re.IGNORECASE)

    errors = 0
    outlines = output.splitlines()
    for line in outlines:
        try:
            wmatch = warnrex.match(line)
        except TypeError:
            line = line.decode('utf-8')
            wmatch = warnrex.match(line)
        ematch = errrex.match(line)
        if ematch:
            errors += 1
        fmatch = failrex.match(line)
        if fmatch:
            errors += 1
        mmatch = missrex.match(line)
        if mmatch:
            errors += 1
        if ematch or wmatch or fmatch or mmatch:
            warn(line)
    return errors


def printall(output):
    """Print all output from a file run using the subprocess package"""

    # Check output for warning or error
    if not output:
        return 0

    outlines = output.splitlines()
    for line in outlines:
        info(line)


def check_layout_out_of_date(spicepath, layoutpath, debug=False):
    """
    Check if a netlist (spicepath) is out-of-date relative to the layouts
    (layoutpath).  Need to read the netlist and check all of the subcells.
    """

    need_capture = False
    if not os.path.isfile(spicepath):
        dbg('Netlist does not exist, so netlist must be regenerated')
        need_capture = True
    elif not os.path.isfile(layoutpath):
        dbg('Layout does not exist, so netlist must be regenerated')
        need_capture = True
    else:
        spi_statbuf = os.stat(spicepath)
        lay_statbuf = os.stat(layoutpath)
        if spi_statbuf.st_mtime < lay_statbuf.st_mtime:
            dbg('Layout netlist is older than top-level layout.')
            laytime = datetime.fromtimestamp(lay_statbuf.st_mtime)
            nettime = datetime.fromtimestamp(spi_statbuf.st_mtime)
            dbg('---Layout  datestamp = ' + str(laytime))
            dbg('---Netlist datestamp = ' + str(nettime))
            need_capture = True
        elif os.path.splitext(layoutpath)[1] == '.mag':
            # If layoutpath points to a .mag file, then above we only
            # established that the top-level-layout is older than the
            # netlist.  Now need to read the netlist, find all subcircuits,
            # and check those dates, too.
            dbg(
                'Netlist is newer than top-level layout, but must check subcells'
            )
            layoutdir = os.path.split(layoutpath)[0]
            subrex = re.compile(
                r'^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
            )
            with open(spicepath, 'r') as ifile:
                duttext = ifile.read()
            dutlines = duttext.replace('\n+', ' ').splitlines()
            for line in dutlines:
                lmatch = subrex.match(line)
                if lmatch:
                    subname = lmatch.group(1)
                    sublayout = os.path.join(layoutdir, subname + '.mag')
                    # subcircuits that cannot be found in the current directory are
                    # assumed to be library components and therefore never out-of-date.
                    if os.path.exists(sublayout):
                        sub_statbuf = os.stat(sublayout)
                        if spi_statbuf.st_mtime < sub_statbuf.st_mtime:
                            # netlist exists but is out-of-date
                            need_capture = True
                            subtime = datetime.fromtimestamp(
                                sub_statbuf.st_mtime
                            )
                            nettime = datetime.fromtimestamp(
                                spi_statbuf.st_mtime
                            )
                            dbg('---Subcell datestamp = ' + subtime)
                            dbg('---Netlist datestamp = ' + nettime)
                            break
    return need_capture


def check_gds_out_of_date(gdspath, magpath):
    """
    Check if the gds is out-of-date relative to the magic layout.
    Need to generate the gds from the mag files.
    """

    if not os.path.isfile(gdspath):
        dbg('GDSII layout does not exist, so must be regenerated.')
        return True

    gds_statbuf = os.stat(gdspath)
    mag_statbuf = os.stat(magpath)

    if gds_statbuf.st_mtime < mag_statbuf.st_mtime:
        dbg('GDSII layout  is older than magic layout.')
        gds_time = datetime.fromtimestamp(gds_statbuf.st_mtime)
        mag_time = datetime.fromtimestamp(mag_statbuf.st_mtime)
        dbg(f'---GDSII datestamp = {gds_time}')
        dbg(f'---magic datestamp = {mag_time}')
        return True

    # Since magpath points to a .mag file, the above only
    # established that the top-level-layout is older than the
    # netlist.

    # TODO check mag file

    return False


def check_schematic_out_of_date(spicepath, schempath, debug=False):
    """
    Check if a netlist (spicepath) is out-of-date relative to the schematics
    (schempath).  Need to read the netlist and check all of the subcells.

    This routine can also be used to determine if a testbench netlist is
    up-to-date with respect to its schematic.
    """

    need_capture = False

    if not os.path.isfile(spicepath):
        dbg('Schematic-captured netlist does not exist. Need to regenerate.')
        need_capture = True
    elif not os.path.isfile(schempath):
        dbg('Schematic does not exist.  Need to regenerate netlist.')
        need_capture = True
    else:
        spi_statbuf = os.stat(spicepath)
        sch_statbuf = os.stat(schempath)
        if spi_statbuf.st_mtime < sch_statbuf.st_mtime:
            dbg('Schematic netlist is older than top-level schematic')
            schtime = datetime.fromtimestamp(sch_statbuf.st_mtime)
            nettime = datetime.fromtimestamp(spi_statbuf.st_mtime)
            dbg('---Schematic datestamp = ' + schtime.isoformat())
            dbg('---Netlist   datestamp = ' + nettime.isoformat())
            need_capture = True
        else:
            dbg(
                'Netlist is newer than top-level schematic, but must check subcircuits'
            )
            # only found that the top-level-schematic is older than the
            # netlist.  Now need to read the netlist, find all subcircuits,
            # and check those dates, too.
            schemdir = os.path.split(schempath)[0]
            schrex = re.compile(
                r'\*\*[ \t]*sch_path:[ \t]*([^ \t\n]+)', re.IGNORECASE
            )
            subrex = re.compile(
                r'^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
            )
            with open(spicepath, 'r') as ifile:
                duttext = ifile.read()

            dutlines = duttext.replace('\n+', ' ').splitlines()
            for line in dutlines:
                # xschem helpfully adds a "sch_path" comment line for every subcircuit
                # coming from a separate schematic file.

                lmatch = schrex.match(line)
                if lmatch:
                    subschem = lmatch.group(1)
                    subfile = os.path.split(subschem)[1]
                    subname = os.path.splitext(subfile)[0]

                    # subcircuits that cannot be found in the current directory are
                    # assumed to be library components or read-only IP components and
                    # therefore never out-of-date.
                    if os.path.exists(subschem):
                        sub_statbuf = os.stat(subschem)
                        if spi_statbuf.st_mtime < sub_statbuf.st_mtime:
                            # netlist exists but is out-of-date
                            dbg(
                                'Netlist is older than subcircuit schematic '
                                + subname
                            )
                            need_capture = True
                            subtime = datetime.fromtimestamp(
                                sub_statbuf.st_mtime
                            )
                            nettime = datetime.fromtimestamp(
                                spi_statbuf.st_mtime
                            )
                            dbg(
                                '---Subcell datestamp = ' + subtime.isoformat()
                            )
                            dbg(
                                '---Netlist datestamp = ' + nettime.isoformat()
                            )
                            break
    return need_capture


def regenerate_netlist(datasheet, netlist_source, runtime_options, pex=False):
    """
    Regenerate the layout-extracted netlist if out-of-date or if forced.
    If argument "pex" is True, then generate parasitic capacitances in
    the output.
    """

    force_regenerate = runtime_options['force']

    dname = datasheet['name']
    netlistname = dname + '.spice'
    paths = datasheet['paths']

    # Check the "paths" dictionary for paths to various files

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    # Get the path to the layout, prefer magic if given in datasheet
    (layout_filepath, is_magic) = get_layout_path(
        dname, paths, check_magic='magic' in paths
    )

    if layout_filepath == None:
        err(f'No layout for project {dname} found.')
        return False

    # Schematic-captured netlist
    if 'netlist' in paths:
        schem_netlist_path = os.path.join(paths['netlist'], 'schematic')
        schem_netlist = os.path.join(schem_netlist_path, netlistname)
    else:
        schem_netlist_path = None
        schem_netlist = None

    # Path to netlist spice file
    netlist_path = os.path.join(paths['netlist'], netlist_source)
    netlist_filepath = os.path.join(netlist_path, netlistname)

    if force_regenerate:
        dbg(f'Forcing regeneration of {netlist_source} netlist.')
        need_extract = True
    else:
        dbg(f'Checking for out of date {netlist_source} netlist.')
        need_extract = check_layout_out_of_date(
            netlist_filepath, layout_filepath, False
        )

    if need_extract:
        if layout_filepath == None:
            err(f'No layout for project {dname} found.')
            return False

        # Check for netlist directory
        if not os.path.exists(netlist_path):
            os.makedirs(netlist_path)

        if 'PDK_ROOT' in datasheet:
            pdk_root = datasheet['PDK_ROOT']
        else:
            pdk_root = get_pdk_root()

        if 'PDK' in datasheet:
            pdk = datasheet['PDK']
        else:
            pdk = get_pdk(magicfilename)

        rcfile = os.path.join(
            pdk_root, pdk, 'libs.tech', 'magic', pdk + '.magicrc'
        )

        newenv = os.environ.copy()
        if pdk_root and 'PDK_ROOT' not in newenv:
            newenv['PDK_ROOT'] = pdk_root
        if pdk and 'PDK' not in newenv:
            newenv['PDK'] = pdk

        info(f'Extracting {netlist_source} netlist from layout…')

        # Assemble stdin for magic
        magic_input = ''

        if is_magic:
            magic_input += f'path search +{os.path.abspath(os.path.dirname(layout_filepath))}\n'
            magic_input += f'load {os.path.basename(layout_filepath)}\n'
        else:
            # magic_input += 'gds flatglob *\n'
            magic_input += f'gds read {layout_filepath}\n'
            magic_input += f'load {dname}\n'
            # Use readspice to get the port order
            magic_input += f'readspice {schem_netlist}\n'
            # necessary after readspice
            magic_input += f'load {dname}\n'

        if netlist_source == 'layout' or netlist_source == 'pex':
            magic_input += f'select top cell\n'
            magic_input += 'expand\n'
            magic_input += 'extract path cace_extfiles\n'
            if netlist_source == 'layout':
                magic_input += 'extract no all\n'
            magic_input += 'extract all\n'
            magic_input += 'ext2spice lvs\n'
            if netlist_source == 'pex':
                magic_input += 'ext2spice cthresh 0.01\n'
            magic_input += (
                f'ext2spice -p cace_extfiles -o {netlist_filepath}\n'
            )

        if netlist_source == 'rcx':
            magic_input += f'select top cell\n'
            magic_input += 'expand\n'
            magic_input += f'flatten {dname + "_flat"}\n'
            magic_input += f'load {dname + "_flat"}\n'
            magic_input += 'select top cell\n'
            magic_input += f'cellname delete {dname}\n'
            magic_input += f'cellname rename {dname + "_flat"} {dname}\n'
            magic_input += 'extract path cace_extfiles\n'
            magic_input += 'extract all\n'
            magic_input += 'ext2sim labels on\n'
            magic_input += 'ext2sim -p cace_extfiles\n'
            magic_input += 'extresist tolerance 10\n'
            magic_input += 'extresist\n'
            magic_input += 'ext2spice lvs\n'
            magic_input += 'ext2spice cthresh 0.01\n'
            magic_input += 'ext2spice extresist on\n'
            magic_input += (
                f'ext2spice -p cace_extfiles -o {netlist_filepath}\n'
            )

        magic_input += 'quit -noprompt\n'

        magicargs = ['-dnull', '-noconsole', '-rcfile', rcfile]

        returncode = run_subprocess(
            'magic', magicargs, input=magic_input, write_file=False
        )
        # printwarn(magout) TODO check if still useful

        # Remove the extraction files temporary directory "cace_extfiles"
        try:
            shutil.rmtree(os.path.join(root_path, 'cace_extfiles'))
        except:
            warn('Directory for extraction files was not created.')

        # Remove temporary files
        try:
            os.remove(os.path.join(root_path, dname + '.sim'))
            os.remove(os.path.join(root_path, dname + '.nodes'))
        except:
            dbg('.sim and .nodes files were not created.')

        if (returncode != 0) or (
            need_extract and not os.path.isfile(netlist_filepath)
        ):
            return False

    else:
        info(f'Skipping extraction of {netlist_source} netlist. Up to date.')

    return netlist_filepath


def check_dependencies(datasheet, debug=False):
    """
    Check the datasheet for listed dependencies and make sure they exist.
    If not, and the dependency entry lists a repository, then clone the
    dependency.

    Returns True if a dependency was cloned, and False if nothing needed
    to be done.

    To do:  For each dependency, find a CACE datasheet and read the path
    information to find the path to schematics, so this can be used to
    add the correct search path to the xschemrc file.  For now, it is
    assumed that the path name is 'xschem'.
    """

    dependencies = []
    if 'dependencies' in datasheet:
        # If there is only one dependency it may be a dictionary and not a
        # list of dictionaries.
        if isinstance(datasheet['dependencies'], dict):
            dependencies = [datasheet['dependencies']]
        else:
            dependencies = datasheet['dependencies']
        for dependency in dependencies:
            if 'path' in dependency and 'name' in dependency:
                dbg('Checking for dependency ' + dependency['name'])
                dependdir = os.path.join(
                    dependency['path'], dependency['name']
                )
                if not os.path.isdir(dependdir):
                    if 'repository' in dependency:
                        deprepo = dependency['repository']
                        deppath = dependency['path']
                        if not os.path.isdir(os.path.abspath(deppath)):
                            os.makedirs(os.path.abspath(deppath))

                        # Now try to do a git clone on the repo.
                        # To do:  Handle other formats than git

                        gproc = subprocess.Popen(
                            ['git', 'clone', deprepo, '--depth=1'],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            cwd=deppath,
                        )

                        gout = gproc.communicate()[0]
                        if gproc.returncode != 0:
                            for line in gout.splitlines():
                                dbg(line.decode('utf-8'))

                            err(
                                'git clone process returned error code '
                                + str(gproc.returncode)
                                + '\n'
                            )
                        else:
                            printwarn(gout)

                        return True

                if not os.path.isdir(dependdir):
                    err(
                        'dependency ' + dependency['name'] + ' does not exist!'
                    )
                    # Maybe should return here, but what if dependency isn't used
                    # in the schematic?
    return False


def regenerate_schematic_netlist(datasheet, runtime_options):
    """Regenerate the schematic-captured netlist if out-of-date or if forced."""

    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    dname = datasheet['name']
    netlistname = dname + '.spice'
    xschemname = dname + '.sch'

    paths = datasheet['paths']

    # Check the "paths" dictionary for paths to various files

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    # Xschem schematic
    if 'schematic' in paths:
        schempath = paths['schematic']
        schemfilename = os.path.join(schempath, xschemname)
    else:
        schempath = None
        schemfilename = None

    # Schematic-captured netlist
    if 'netlist' in paths:
        schem_netlist_path = os.path.join(paths['netlist'], 'schematic')
        schem_netlist = os.path.join(schem_netlist_path, netlistname)
    else:
        schem_netlist_path = None
        schem_netlist = None

    # Verilog netlist
    if 'verilog' in paths:
        verilog_netlist_path = paths['verilog']
        verilog_netlist = os.path.join(verilog_netlist_path, netlistname)
    else:
        verilog_netlist_path = None
        verilog_netlist = None

    # Always regenerate the schematic netlist
    # We cannot always be sure that none of the dependencies was changed
    # as there are many different ways to include e.g. spice files etc.
    need_schem_capture = True

    """if force_regenerate:
        need_schem_capture = True
    else:
        dbg('Checking for out-of-date schematic-captured netlists.')
        need_schem_capture = check_schematic_out_of_date(
            schem_netlist, schemfilename, debug
        )

    depupdated = check_dependencies(datasheet, debug)
    if depupdated:
        need_schem_capture = True"""

    if need_schem_capture:
        dbg('Forcing regeneration of schematic-captured netlist.')

        # Netlist needs regenerating.  Check for xschem schematic
        if not schemfilename or not os.path.isfile(schemfilename):
            if verilog_netlist and os.path.isfile(verilog_netlist):
                info('No schematic for project.')
                info(
                    'Using verilog structural netlist '
                    + verilog_netlist
                    + ' for simulation and LVS.'
                )
                return verilog_netlist
            else:
                err('No netlist or schematic for project ' + dname + '.')
                if schemfilename:
                    err(
                        '(schematic master file '
                        + schemfilename
                        + ' not found.)\n'
                    )
                else:
                    err('Project does not have a master schematic.\n')
                err('No structural verilog netlist, either.')
                return False

        info('Generating simulation netlist from schematic…')

        # Generate the netlist
        dbg('Calling xschem to generate netlist')

        if not os.path.exists(schem_netlist_path):
            os.makedirs(schem_netlist_path)

        if 'PDK_ROOT' in datasheet:
            pdk_root = datasheet['PDK_ROOT']
        else:
            pdk_root = get_pdk_root()

        if 'PDK' in datasheet:
            pdk = datasheet['PDK']
        else:
            pdk = get_pdk(magicfilename)

        # Xschem arguments:
        # -n:  Generate a netlist
        # -s:  Netlist type is SPICE
        # -r:  Bypass readline (because stdin/stdout are piped)
        # -x:  No X11 / No GUI window
        # -q:  Quit after processing command line
        # --tcl "set top_is_subckt 1":  Require ".subckt ... .ends" wrapper

        xschemargs = [
            'xschem',
            '-n',
            '-s',
            '-r',
            '-x',
            '-q',
            '--tcl',
            'set top_is_subckt 1',
        ]

        # Check whether there is an xschemrc file in the project
        xschemrcfile = os.path.join(schempath, 'xschemrc')
        if not os.path.isfile(xschemrcfile):
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

        xschemargs.extend(
            [
                '-o',
                os.path.abspath(
                    os.path.join(root_path, schem_netlist_path)
                ),  # output dir
                '-N',
                netlistname,  # spice netlist
                xschemname,  # schematic
            ]
        )

        dbg('Executing: ' + ' '.join(xschemargs))
        dbg('CWD is ' + os.path.join(root_path, schempath))

        # Start xschem process in schematic directory
        # This will automatically source the project xschemrc
        xproc = subprocess.Popen(
            xschemargs,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.path.join(root_path, schempath),
        )

        xout = xproc.communicate()[0]
        if xproc.returncode != 0:
            for line in xout.splitlines():
                err(line.decode('utf-8'))

            err(
                'Xschem process returned error code '
                + str(xproc.returncode)
                + '\n'
            )
        else:
            printwarn(xout)

        if not os.path.isfile(schem_netlist):
            err('No netlist found for the circuit!\n')
            err(
                '(schematic netlist for simulation '
                + schem_netlist
                + ' not found.)\n'
            )

        else:
            # Do a quick parse of the netlist to check for errors
            missrex = re.compile(r'[ \t]*([^ \t]+)[ \t]+IS MISSING')
            with open(schem_netlist, 'r') as ifile:
                schemlines = ifile.read().splitlines()
                for line in schemlines:
                    mmatch = missrex.search(line)
                    if mmatch:
                        err('Error in netlist generation:')
                        err(
                            'Subcircuit ' + mmatch.group(1) + ' was not found!'
                        )

    if need_schem_capture:
        if not os.path.isfile(schem_netlist):
            return False

    return schem_netlist


def regenerate_testbench(datasheet, runtime_options, testbenchpath, testbench):
    """Regenerate a testbench template (create SPICE from .sch)"""

    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    paths = datasheet['paths']

    if not os.path.exists(testbenchpath):
        err('Testbench path ' + testbenchpath + ' does not exist.')
        return 1

    need_testbench_netlist = False
    testbenchsource = os.path.splitext(testbench)[0] + '.sch'
    source_file = os.path.join(testbenchpath, testbenchsource)
    netlist_file = os.path.join(testbenchpath, testbench)

    if force_regenerate:
        need_testbench_netlist = True
    else:
        netlist_root = os.path.split(netlist_file)[1]
        dbg('Checking for out-of-date testbench netlist ' + netlist_root + '.')
        need_testbench_netlist = check_schematic_out_of_date(
            netlist_file, source_file, debug
        )

    if not need_testbench_netlist:
        # Testbench exists and is up-to-date; nothing to do
        return 0

    if not os.path.isfile(source_file):
        err('No testbench netlist or source for testbench ' + testbench)
        return 1

    info('Generating testbench netlist ' + testbench + ' from schematic…')

    # Generate the netlist
    dbg('Calling xschem to generate netlist')

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    if 'PDK_ROOT' in datasheet:
        pdk_root = datasheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in datasheet:
        pdk = datasheet['PDK']
    else:
        pdk = get_pdk(magicfilename)

    newenv = os.environ.copy()
    if pdk_root and 'PDK_ROOT' not in newenv:
        newenv['PDK_ROOT'] = pdk_root
    if pdk and 'PDK' not in newenv:
        newenv['PDK'] = pdk

    tclstr = set_xschem_paths(datasheet, testbenchpath, '')
    xschemargs = ['xschem', '-n', '-s', '-r', '-x', '-q', '--tcl', tclstr]

    # Use the PDK xschemrc file for xschem startup
    xschemrcfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
    )
    if os.path.isfile(xschemrcfile):
        xschemargs.extend(['--rcfile', xschemrcfile])
    else:
        err('No xschemrc file found in the ' + pdk + ' PDK!')

    xschemargs.extend(['-o', testbenchpath, '-N', testbench])
    xschemargs.append(os.path.join(testbenchpath, testbenchsource))
    dbg('Executing: ' + ' '.join(xschemargs))

    xproc = subprocess.Popen(
        xschemargs,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=root_path,
        env=newenv,
    )

    xout = xproc.communicate()[0]
    if xproc.returncode != 0:
        for line in xout.splitlines():
            err(line.decode('utf-8'))

        err(
            'Xschem process returned error code '
            + str(xproc.returncode)
            + '\n'
        )
    else:
        printwarn(xout)

    # Do a quick parse of the netlist to check for errors
    missrex = re.compile(r'[ \t]*([^ \t]+)[ \t]+IS MISSING')
    with open(netlist_file, 'r') as ifile:
        schemlines = ifile.read().splitlines()
        for line in schemlines:
            mmatch = missrex.search(line)
            if mmatch:
                err('Error in netlist generation:')
                err('Subcircuit ' + mmatch.group(1) + ' was not found!')
                os.remove(netlist_file)

    if not os.path.isfile(netlist_file):
        err('No netlist found for the testbench ' + testbench + '!')
        return 1

    return 0


def regenerate_netlists(datasheet, runtime_options):
    """Regenerate all netlists as needed when out of date."""

    # 'netlist_source' determines whether to use the layout extracted netlist
    # or the schematic captured netlist.  Also, regenerate the netlist only if
    # it is out of date, or if the user has selected forced regeneration in the
    # settings.

    source = runtime_options['netlist_source']

    # Always generate the schematic netlist
    # Either the netlist source is "schematic", or we need it
    # to get the correct port order for the extracted netlists
    result = regenerate_schematic_netlist(datasheet, runtime_options)

    # Layout extracted netlist
    if source == 'layout':
        result = regenerate_netlist(datasheet, 'layout', runtime_options)
        return result

    # PEX (parasitic capacitance-only) netlist
    if source == 'pex':
        result = regenerate_netlist(datasheet, 'pex', runtime_options)

        # Also make sure LVS netlist is generated, in case LVS is run
        regenerate_netlist(datasheet, 'layout', runtime_options)
        return result

    # RCX (R-C-extraction) netlist
    if source == 'all' or source == 'rcx' or source == 'best':
        result = regenerate_netlist(datasheet, 'rcx', runtime_options)

        # Also make sure LVS netlist is generated, in case LVS is run
        regenerate_netlist(datasheet, 'layout', runtime_options)
        return result

    return result


def regenerate_gds(datasheet, runtime_options):
    """Regenerate gds as needed when out of date."""

    paths = datasheet['paths']
    dname = datasheet['name']

    # Running on schematic, no regeneration needed
    if runtime_options['netlist_source'] == 'schematic':
        return 0

    # No mag files given, gds does not need regeneration
    if not 'magic' in datasheet['paths']:
        return 0

    gdspath = os.path.join(paths['root'], paths['layout'], f'{dname}.gds.gz')
    magpath = os.path.join(paths['root'], paths['magic'], f'{dname}.mag')

    # make sure mag files exist
    if not os.path.isfile(magpath):
        err(f'Could not find magic layout: {magpath}')
        return 1

    # Create the path to gds file
    mkdirp(os.path.join(paths['root'], paths['layout']))

    # Check whether we need to regenerate the gds from magic
    if check_gds_out_of_date(gdspath, magpath):
        info('Regenerating GDSII from magic layout…')

        pdk = datasheet['PDK']
        pdk_root = get_pdk_root()

        rcfile = os.path.join(
            pdk_root, pdk, 'libs.tech', 'magic', pdk + '.magicrc'
        )

        magicargs = ['magic', '-dnull', '-noconsole', '-rcfile', rcfile]
        dbg('Executing: ' + ' '.join(magicargs))

        mproc = subprocess.Popen(
            magicargs,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=paths['root'],
            text=True,
        )

        mproc.stdin.write('load ' + magpath + '\n')
        mproc.stdin.write('gds compress 9\n')
        mproc.stdin.write('gds write ' + gdspath + '\n')
        mproc.stdin.write('quit -noprompt\n')

        magout = mproc.communicate()[0]
        printwarn(magout)

        if mproc.returncode != 0:
            err(f'Magic process returned error code {mproc.returncode}.')
    else:
        info('Not regenerating GDSII from magic layout. Up to date.')

    if not os.path.isfile(gdspath):
        err(f'Could not generate gds layout: {gdspath}')
        return 1

    return 0


def make_symbol_primitive(datasheet):
    """
    Copy the schematic symbol to the testbench directory and remark its
    type from 'schematic' to 'primitive', so that testbench netlists will
    write an instance call but not the schematic itself.  That way, the
    schematic can be brought in from an include file that can be set to
    any one of schematic-captured or layout-extracted netlists.
    """

    dname = datasheet['name']
    xschemname = dname + '.sym'

    paths = datasheet['paths']

    # Xschem schematic symbol
    if 'schematic' in paths:
        schempath = paths['schematic']
        symbolfilename = os.path.join(schempath, xschemname)
    else:
        schempath = None
        symbolfilename = None

    if not symbolfilename or not os.path.isfile(symbolfilename):
        err('Symbol for project ' + dname + ' was not found!')
        return

    # Testbench primitive symbol
    testbenchpath = paths.get('testbench', paths['templates'])

    primfilename = os.path.join(testbenchpath, xschemname)

    with open(symbolfilename, 'r') as ifile:
        symboldata = ifile.read()
        primdata = symboldata.replace('type=subcircuit', 'type=primitive')

    with open(primfilename, 'w') as ofile:
        ofile.write(primdata)


def regenerate_testbenches(datasheet, pname=None):
    """
    If pname is passed to regenerate_testbenches and is not None, then
    only generate testbenches required by the specified parameter.
    """

    paths = datasheet['paths']
    testbenchpath = paths.get('testbench', paths['templates'])

    # Copy the circuit symbol from schematic directory to testbench
    # directory and make it a primitive.
    make_symbol_primitive(datasheet)

    # Enumerate testbenches used in electrical parameters
    testbenchlist = []

    # Generate testbench for a single parameter
    if pname:
        if pname in datasheet['parameters']:
            param = datasheet['parameters'][pname]

            if 'simulate' in param:
                if 'ngspice' in param['simulate']:
                    if 'template' in param['simulate']['ngspice']:
                        template = param['simulate']['ngspice']['template']

                        result = regenerate_testbench(
                            datasheet, testbenchpath, template
                        )
                        if result != 0:
                            err(
                                'Error in testbench generation. Halting characterization.'
                            )
                            return result
        else:
            warn(f'Unknown parameter {pname}')
    else:
        for param in datasheet['parameters'].values():
            if 'simulate' in param:
                if 'ngspice' in param['simulate']:
                    if 'template' in param['simulate']['ngspice']:
                        template = param['simulate']['ngspice']['testbench']

                        result = regenerate_testbench(
                            datasheet, testbenchpath, template
                        )
                        if result != 0:
                            err(
                                'Error in testbench generation. Halting characterization.'
                            )
                            return result

    return 0
