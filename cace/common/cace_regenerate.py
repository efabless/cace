#!/usr/bin/env python3
# -----------------------------------------------------------------------
# cace_regenerate.py
# -----------------------------------------------------------------------
#
# These procedures are used by cace_gensim to check if netlists need
# to be automatically regenerated, and to run schematic capture or
# layout extraction as needed.
# -----------------------------------------------------------------------

import os
import sys
import re
import shutil
from datetime import date as datetime
import subprocess

# ----------------------------------------------------------------------
# printwarn
#
# Print warnings output from a file run using the subprocess package
# ----------------------------------------------------------------------


def printwarn(output):
    # Check output for warning or error
    if not output:
        return 0

    failrex = re.compile('.*failure', re.IGNORECASE)
    warnrex = re.compile('.*warning', re.IGNORECASE)
    errrex = re.compile('.*error', re.IGNORECASE)
    missrex = re.compile('.*not found', re.IGNORECASE)

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
            print(line)
    return errors


# ----------------------------------------------------------------------
# printall
#
# Print all output from a file run using the subprocess package
# ----------------------------------------------------------------------


def printall(output):
    # Check output for warning or error
    if not output:
        return 0

    outlines = output.splitlines()
    for line in outlines:
        print(line)


# -----------------------------------------------------------------------
# get_pdk_root
#
# Get a value for PDK_ROOT, either from an environment variable, or
# from several standard locations (open_pdks install and IIC-tools
# install and volare install).
# -----------------------------------------------------------------------


def get_pdk_root():
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
    return pdk_root


# -----------------------------------------------------------------------
# get_pdk
#
# Get a value for the PDK, either from the second line of a .mag file,
# or from the environment as environment variable "PDK".
#
# NOTE:  Normally the PDK is provided as part of the datasheet, as
# a project does not necessarily have a .mag file;  so there is no
# source for automatically determining the project PDK.
# -----------------------------------------------------------------------


def get_pdk(magicfilename):
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
            print(
                'Error:  No .mag file and PDK is not defined in the environment.'
            )
            pdk = None

    return pdk


# -----------------------------------------------------------------------
# Get the path and filename of the magic startup script corresponding
# to the PDK.
#
# Returns a string containing the full path and filename of the startup
# script (.magicrc file).
# -----------------------------------------------------------------------


def get_magic_rcfile(dsheet, magicfilename=None):

    if 'PDK_ROOT' in dsheet:
        pdk_root = dsheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in dsheet:
        pdk = dsheet['PDK']
    elif magicfilename:
        pdk = get_pdk(magicfilename)
    else:
        paths = dsheet['paths']
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


# -----------------------------------------------------------------------
# Get the path and filename of the netgen setup script corresponding
# to the PDK.
#
# Returns a string containing the full path and filename of the setup
# script (.tcl file).
# -----------------------------------------------------------------------


def get_netgen_setupfile(dsheet):

    if 'PDK_ROOT' in dsheet:
        pdk_root = dsheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in dsheet:
        pdk = dsheet['PDK']
    elif magicfilename:
        pdk = get_pdk(magicfilename)
    else:
        paths = dsheet['paths']
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


# -----------------------------------------------------------------------
# check_simulation_out_of_date
#
# Check if a simulation result is out-of-date relative to both the
# testbench and the DUT.  It can be assumed that the DUT netlist and
# testbench have already been checked against their respective
# schematics, only the netlists need to be compared.
#
# "simpath" is the path to simulation result (usually in root_path/ngspice)
# "tbpath" is the path to testbench netlist (usually in root_path/cace)
# "dutpath" is the path to the design netlist (depends on source setting)
# -----------------------------------------------------------------------


def check_simulation_out_of_date(simpath, tbpath, dutpath, debug=False):
    need_resimulate = False
    if not os.path.isfile(simpath):
        if debug:
            print('Simulation result does not exist.  Need to resimulate.')
        need_resimulate = True
    elif not os.path.isfile(tbpath):
        if debug:
            print('Testbench or path does not exist.  Need to regenerate.')
        need_resimulate = True
    elif not os.path.isfile(dutpath):
        if debug:
            print(
                'Project netlist or path does not exist.  Need to regenerate.'
            )
        need_resimulate = True
    else:
        sim_statbuf = os.stat(simpath)
        tb_statbuf = os.stat(tbpath)
        dut_statbuf = os.stat(dutpath)

        if sim_statbuf.st_mtime < tb_statbuf.st_mtime:
            print('Simulation output is older than testbench netlist')
            if debug:
                tbtime = datetime.fromtimestamp(tb_statbuf.st_mtime)
                simtime = datetime.fromtimestamp(sim_statbuf.st_mtime)
                print('---Testbench datestamp  = ' + tbtime.isoformat())
                print('---Simulation datestamp = ' + simtime.isoformat())
            need_simulation = True

        if sim_statbuf.st_mtime < dut_statbuf.st_mtime:
            print('Simulation output is older than project netlist')
            if debug:
                duttime = datetime.fromtimestamp(dut_statbuf.st_mtime)
                simtime = datetime.fromtimestamp(sim_statbuf.st_mtime)
                print('---Project netlist datestamp = ' + duttime.isoformat())
                print('---Simulation datestamp      = ' + simtime.isoformat())
            need_simulation = True

    return need_simulation


# -----------------------------------------------------------------------
# check_layout_out_of_date
#
# Check if a netlist (spicepath) is out-of-date relative to the layouts
# (layoutpath).  Need to read the netlist and check all of the subcells.
# -----------------------------------------------------------------------


def check_layout_out_of_date(spicepath, layoutpath, debug=False):
    need_capture = False
    if not os.path.isfile(spicepath):
        if debug:
            print('Netlist does not exist, so netlist must be regenerated')
        need_capture = True
    elif not os.path.isfile(layoutpath):
        if debug:
            print('Layout does not exist, so netlist must be regenerated')
        need_capture = True
    else:
        spi_statbuf = os.stat(spicepath)
        lay_statbuf = os.stat(layoutpath)
        if spi_statbuf.st_mtime < lay_statbuf.st_mtime:
            print('Layout netlist is older than top-level layout.')
            if debug:
                laytime = datetime.fromtimestamp(lay_statbuf.st_mtime)
                nettime = datetime.fromtimestamp(spi_statbuf.st_mtime)
                print('---Layout  datestamp = ' + laytime)
                print('---Netlist datestamp = ' + nettime)
            need_capture = True
        elif os.path.splitext(layoutpath)[1] == '.mag':
            # If layoutpath points to a .mag file, then above we only
            # established that the top-level-layout is older than the
            # netlist.  Now need to read the netlist, find all subcircuits,
            # and check those dates, too.
            if debug:
                print(
                    'Netlist is newer than top-level layout, but must check subcells'
                )
            layoutdir = os.path.split(layoutpath)[0]
            subrex = re.compile(
                '^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
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
                            if debug:
                                subtime = datetime.fromtimestamp(
                                    sub_statbuf.st_mtime
                                )
                                nettime = datetime.fromtimestamp(
                                    spi_statbuf.st_mtime
                                )
                                print('---Subcell datestamp = ' + subtime)
                                print('---Netlist datestamp = ' + nettime)
                            break
    return need_capture


# -----------------------------------------------------------------------
# check_schematic_out_of_date
#
# Check if a netlist (spicepath) is out-of-date relative to the schematics
# (schempath).  Need to read the netlist and check all of the subcells.
#
# This routine can also be used to determine if a testbench netlist is
# up-to-date with respect to its schematic.
# -----------------------------------------------------------------------


def check_schematic_out_of_date(spicepath, schempath, debug=False):
    need_capture = False
    if not os.path.isfile(spicepath):
        if debug:
            print(
                'Schematic-captured netlist does not exist.  Need to regenerate.'
            )
        need_capture = True
    elif not os.path.isfile(schempath):
        if debug:
            print('Schematic does not exist.  Need to regenerate netlist.')
        need_capture = True
    else:
        spi_statbuf = os.stat(spicepath)
        sch_statbuf = os.stat(schempath)
        if spi_statbuf.st_mtime < sch_statbuf.st_mtime:
            print('Schematic netlist is older than top-level schematic')
            if debug:
                schtime = datetime.fromtimestamp(sch_statbuf.st_mtime)
                nettime = datetime.fromtimestamp(spi_statbuf.st_mtime)
                print('---Schematic datestamp = ' + schtime.isoformat())
                print('---Netlist   datestamp = ' + nettime.isoformat())
            need_capture = True
        else:
            if debug:
                print(
                    'Netlist is newer than top-level schematic, but must check subcircuits'
                )
            # only found that the top-level-schematic is older than the
            # netlist.  Now need to read the netlist, find all subcircuits,
            # and check those dates, too.
            schemdir = os.path.split(schempath)[0]
            schrex = re.compile(
                '\*\*[ \t]*sch_path:[ \t]*([^ \t\n]+)', re.IGNORECASE
            )
            subrex = re.compile(
                '^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
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
                            print(
                                'Netlist is older than subcircuit schematic '
                                + subname
                            )
                            need_capture = True
                            if debug:
                                subtime = datetime.fromtimestamp(
                                    sub_statbuf.st_mtime
                                )
                                nettime = datetime.fromtimestamp(
                                    spi_statbuf.st_mtime
                                )
                                print(
                                    '---Subcell datestamp = '
                                    + subtime.isoformat()
                                )
                                print(
                                    '---Netlist datestamp = '
                                    + nettime.isoformat()
                                )
                            break
    return need_capture


# -----------------------------------------------------------------------
# regenerate_rcx_netlist
#
# Regenerate the R-C parasitic extracted netlist if out-of-date or if
# forced.
# -----------------------------------------------------------------------


def regenerate_rcx_netlist(dsheet):

    runtime_options = dsheet['runtime_options']
    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    dname = dsheet['name']
    netlistname = dname + '.spice'
    vlogname = dname + '.v'
    magicname = dname + '.mag'
    gdsname = dname + '.gds'
    xschemname = dname + '.sch'

    paths = dsheet['paths']

    # Check the "paths" dictionary for paths to various files

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    # Magic layout
    if 'magic' in paths:
        magicpath = paths['magic']
        magicfilename = os.path.join(magicpath, magicname)
    else:
        magicpath = None
        magicfilename = None

    # GDS layout
    if 'layout' in paths:
        gdspath = paths['layout']
        gdsfilename = os.path.join(gdspath, gdsname)
    else:
        gdspath = None
        gdsfilename = None

    # Layout-extracted netlist with R-C parasitics
    if 'netlist' in paths:
        rcx_netlist_path = os.path.join(paths['netlist'], 'rcx')
        rcx_netlist = os.path.join(rcx_netlist_path, netlistname)
    else:
        rcx_netlist = None
        rcx_netlist = None

    need_rcx_extraction = True

    if force_regenerate:
        need_rcx_extract = True
    else:
        print('Checking for out-of-date RCX netlists.')
        valid_layoutpath = magicfilename if magicpath else gdsfilename
        need_rcx_extract = check_layout_out_of_date(
            rcx_netlist, valid_layoutpath, debug
        )

    if need_rcx_extract:
        print('Forcing regeneration of parasitic-extracted netlist.')

    if need_rcx_extract:
        # Layout parasitic netlist needs regenerating.  Check for magic layout.

        if not magicfilename or not os.path.isfile(magicfilename):
            print('Error:  No netlist or layout for project ' + dname + '.')
            if magicfilename:
                print(
                    '(layout master file ' + magicfilename + ' not found.)\n'
                )
            else:
                print('(layout master file ' + gdsfilename + ' not found.)\n')
            return False

        # Check for parasitic netlist directory
        if not os.path.exists(rcx_netlist_path):
            os.makedirs(rcx_netlist_path)

        rcfile = get_magic_rcfile(dsheet, magicfilename)
        newenv = os.environ.copy()

        if 'PDK_ROOT' in dsheet:
            pdk_root = dsheet['PDK_ROOT']
        else:
            pdk_root = get_pdk_root()

        if 'PDK' in dsheet:
            pdk = dsheet['PDK']
        else:
            pdk = get_pdk(magicfilename)

        if pdk_root and 'PDK_ROOT' not in newenv:
            newenv['PDK_ROOT'] = pdk_root
        if pdk and 'PDK' not in newenv:
            newenv['PDK'] = pdk

        print('Extracting netlist with parasitics from layout. . .')

        magicargs = ['magic', '-dnull', '-noconsole', '-rcfile', rcfile]
        if debug:
            print('Executing: ' + ' '.join(magicargs))

        mproc = subprocess.Popen(
            magicargs,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=root_path,
            env=newenv,
            universal_newlines=True,
        )
        if magicfilename:
            mproc.stdin.write('load ' + magicfilename + '\n')
        else:
            mproc.stdin.write('gds read ' + gdsfilename + '\n')
            mproc.stdin.write('load ' + dname + '\n')
        mproc.stdin.write('select top cell\n')
        mproc.stdin.write('expand\n')
        mproc.stdin.write('flatten ' + dname + '_flat\n')
        mproc.stdin.write('load ' + dname + '_flat\n')
        mproc.stdin.write('select top cell\n')
        mproc.stdin.write('cellname delete ' + dname + '\n')
        mproc.stdin.write('cellname rename ' + dname + '_flat ' + dname + '\n')
        mproc.stdin.write('extract path cace_extfiles\n')
        mproc.stdin.write('extract all\n')
        mproc.stdin.write('ext2sim labels on\n')
        mproc.stdin.write('ext2sim -p cace_extfiles\n')
        mproc.stdin.write('extresist tolerance 10\n')
        mproc.stdin.write('extresist\n')
        mproc.stdin.write('ext2spice lvs\n')
        mproc.stdin.write('ext2spice cthresh 0.01\n')
        mproc.stdin.write('ext2spice extresist on\n')
        mproc.stdin.write(
            'ext2spice -p cace_extfiles -o ' + rcx_netlist + '\n'
        )
        mproc.stdin.write('quit -noprompt\n')

        magout = mproc.communicate()[0]
        printwarn(magout)
        if mproc.returncode != 0:
            print(
                'Magic process returned error code '
                + str(mproc.returncode)
                + '\n'
            )

        if need_rcx_extract and not os.path.isfile(rcx_netlist):
            print('Error:  No netlist with parasitics extracted from magic.')

        # Remove the temporary directory of extraction files "cace_extfiles"
        try:
            shutil.rmtree(os.path.join(root_path, 'cace_extfiles'))
        except:
            print('Warning: Directory for extraction files was not created.')

        # Remove temporary files
        try:
            os.remove(os.path.join(root_path, dname + '.sim'))
            os.remove(os.path.join(root_path, dname + '.nodes'))
        except:
            print('Warning: .sim and .nodes files were not created.')

        if (mproc.returncode != 0) or (
            need_rcx_extract and not os.path.isfile(rcx_netlist)
        ):
            return False

    return rcx_netlist


# -----------------------------------------------------------------------
# regenerate_lvs_netlist
#
# Regenerate the layout-extracted netlist if out-of-date or if forced.
# If argument "pex" is True, then generate parasitic capacitances in
# the output.
# -----------------------------------------------------------------------


def regenerate_lvs_netlist(dsheet, pex=False):

    runtime_options = dsheet['runtime_options']
    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    dname = dsheet['name']
    netlistname = dname + '.spice'
    magicname = dname + '.mag'
    gdsname = dname + '.gds'

    paths = dsheet['paths']

    # Check the "paths" dictionary for paths to various files

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    # Magic layout
    if 'magic' in paths:
        magicpath = paths['magic']
        magicfilename = os.path.join(magicpath, magicname)
    else:
        magicpath = None
        magicfilename = None

    # GDS layout
    if 'layout' in paths:
        gdspath = paths['layout']
        gdsfilename = os.path.join(gdspath, gdsname)
    else:
        gdspath = None
        gdsfilename = None

    if pex == True:
        nettype = 'pex'
    else:
        nettype = 'layout'

    # Layout-extracted netlist for LVS
    if 'netlist' in paths:
        lvs_netlist_path = os.path.join(paths['netlist'], nettype)
        lvs_netlist = os.path.join(lvs_netlist_path, netlistname)
    else:
        lvs_netlist_path = None
        lvs_netlist = None

    need_extraction = True

    if force_regenerate:
        need_lvs_extract = True
    else:
        print('Checking for out-of-date ' + nettype + ' netlists.')
        valid_layoutpath = magicfilename if magicpath else gdsfilename
        need_lvs_extract = check_layout_out_of_date(
            lvs_netlist, valid_layoutpath, debug
        )

    if need_lvs_extract:
        print('Forcing regeneration of layout-extracted netlist.')

        # Layout LVS netlist needs regenerating.  Check for magic layout.
        if not magicfilename or not os.path.isfile(magicfilename):
            print('Error:  No netlist or layout for project ' + dname + '.')
            if magicfilename:
                print(
                    '(layout master file ' + magicfilename + ' not found.)\n'
                )
            else:
                print('(layout master file ' + gdsfilename + ' not found.)\n')
            return False

        # Check for LVS netlist directory
        if not os.path.exists(lvs_netlist_path):
            os.makedirs(lvs_netlist_path)

        if 'PDK_ROOT' in dsheet:
            pdk_root = dsheet['PDK_ROOT']
        else:
            pdk_root = get_pdk_root()

        if 'PDK' in dsheet:
            pdk = dsheet['PDK']
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

        print('Extracting LVS netlist from layout. . .')

        magicargs = ['magic', '-dnull', '-noconsole', '-rcfile', rcfile]
        if debug:
            print('Executing: ' + ' '.join(magicargs))

        mproc = subprocess.Popen(
            magicargs,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=root_path,
            env=newenv,
            universal_newlines=True,
        )
        if magicfilename:
            mproc.stdin.write('load ' + magicfilename + '\n')
        else:
            mproc.stdin.write('gds read ' + gdsfilename + '\n')
            mproc.stdin.write('load ' + dname + '\n')
        mproc.stdin.write('select top cell\n')
        mproc.stdin.write('expand\n')
        mproc.stdin.write('extract path cace_extfiles\n')
        mproc.stdin.write('extract all\n')
        mproc.stdin.write('ext2spice lvs\n')
        if pex == True:
            mproc.stdin.write('ext2spice cthresh 0.01\n')
        mproc.stdin.write(
            'ext2spice -p cace_extfiles -o ' + lvs_netlist + '\n'
        )
        mproc.stdin.write('quit -noprompt\n')

        magout = mproc.communicate()[0]
        printwarn(magout)
        if mproc.returncode != 0:
            print(
                'Magic process returned error code '
                + str(mproc.returncode)
                + '\n'
            )

        if need_lvs_extract and not os.path.isfile(lvs_netlist):
            print('Error:  No LVS netlist extracted from magic.')

        # Remove the extraction files temporary directory "cace_extfiles"
        try:
            shutil.rmtree(os.path.join(root_path, 'cace_extfiles'))
        except:
            print('Warning: Directory for extraction files was not created.')

        if (mproc.returncode != 0) or (
            need_lvs_extract and not os.path.isfile(lvs_netlist)
        ):
            return False

    return lvs_netlist


# -----------------------------------------------------------------------
# check_dependencies --
#
# Check the datasheet for listed dependencies and make sure they exist.
# If not, and the dependency entry lists a repository, then clone the
# dependency.
#
# Returns True if a dependency was cloned, and False if nothing needed
# to be done.
#
# To do:  For each dependency, find a CACE datasheet and read the path
# information to find the path to schematics, so this can be used to
# add the correct search path to the xschemrc file.  For now, it is
# assumed that the path name is 'xschem'.
# -----------------------------------------------------------------------


def check_dependencies(dsheet, debug=False):
    dependencies = []
    if 'dependencies' in dsheet:
        # If there is only one dependency it may be a dictionary and not a
        # list of dictionaries.
        if isinstance(dsheet['dependencies'], dict):
            dependencies = [dsheet['dependencies']]
        else:
            dependencies = dsheet['dependencies']
        for dependency in dependencies:
            if 'path' in dependency and 'name' in dependency:
                if debug:
                    print('Checking for dependency ' + dependency['name'])
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
                                print(line.decode('utf-8'))

                            print(
                                'git clone process returned error code '
                                + str(gproc.returncode)
                                + '\n'
                            )
                        else:
                            printwarn(gout)

                        return True

                if not os.path.isdir(dependdir):
                    print(
                        'Error: dependency '
                        + dependency['name']
                        + ' does not exist!'
                    )
                    # Maybe should return here, but what if dependency isn't used
                    # in the schematic?
    return False


# -----------------------------------------------------------------------
# set_xschem_paths ---
#
# 	Put together a set of Tcl commands that sets the search
# 	path for xschem.
#
# 	If tclstr is not None, then it is assumed to be a valid
# 	Tcl command, and the rest of the Tcl command string is
# 	appended to it, with independent commands separated by
# 	semicolons.
#
# 	Return the final Tcl command string.
#
# 	Note that this is used only when regenerating the schematic
# 	netlist.  The testbenches are assumed to call the symbol as
# 	a primitive, and rely on an include file to pull in the
# 	netlist (either schematic or layout) from the appropriate
# 	netlist directory.
#
# -----------------------------------------------------------------------


def set_xschem_paths(dsheet, tclstr=None):
    paths = dsheet['paths']

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

    # Add the schematic path to the search path
    if 'schematic' in paths:
        schempath = os.path.join(root_path, paths['schematic'])
        tcllist.append('append XSCHEM_LIBRARY_PATH :' + schempath)

    # If dependencies are declared, then pull in their locations
    # and add them to the search path as well.

    # NOTE:  This depends on the setup of the dependent repository.
    # The code below assumes that there is a subdirectory 'xschem'
    # in the repository.  There needs to be a routine that recursively
    # determines schematic paths from the dependent repository's own
    # CACE definition file.

    if 'dependencies' in dsheet:
        # If there is only one dependency it may be a dictionary and not a
        # list of dictionaries.
        if isinstance(dsheet['dependencies'], dict):
            dependencies = [dsheet['dependencies']]
        else:
            dependencies = dsheet['dependencies']

        for dependency in dependencies:
            if 'path' in dependency and 'name' in dependency:
                dependdir = os.path.join(
                    dependency['path'], dependency['name'], 'xschem'
                )
                tcllist.append('append XSCHEM_LIBRARY_PATH :' + dependdir)

    return ' ; '.join(tcllist)


# -----------------------------------------------------------------------
# regenerate_schematic_netlist
#
# Regenerate the schematic-captured netlist if out-of-date or if forced.
# -----------------------------------------------------------------------


def regenerate_schematic_netlist(dsheet):

    runtime_options = dsheet['runtime_options']
    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    dname = dsheet['name']
    netlistname = dname + '.spice'
    xschemname = dname + '.sch'

    paths = dsheet['paths']

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

    need_schem_capture = False

    if force_regenerate:
        need_schem_capture = True
    else:
        print('Checking for out-of-date schematic-captured netlists.')
        need_schem_capture = check_schematic_out_of_date(
            schem_netlist, schemfilename, debug
        )

    depupdated = check_dependencies(dsheet, debug)
    if depupdated:
        need_schem_capture = True

    if need_schem_capture:
        print('Forcing regeneration of schematic-captured netlist.')

        # Netlist needs regenerating.  Check for xschem schematic
        if not schemfilename or not os.path.isfile(schemfilename):
            if verilog_netlist and os.path.isfile(verilog_netlist):
                print('No schematic for project.')
                print(
                    'Using verilog structural netlist '
                    + verilog_netlist
                    + ' for simulation and LVS.'
                )
                return verilog_netlist
            else:
                print(
                    'Error:  No netlist or schematic for project '
                    + dname
                    + '.'
                )
                if schemfilename:
                    print(
                        '(schematic master file '
                        + schemfilename
                        + ' not found.)\n'
                    )
                else:
                    print('Project does not have a master schematic.\n')
                print('No structural verilog netlist, either.')
                return False

        print('Generating simulation netlist from schematic. . .')
        # Generate the netlist
        print('Calling xschem to generate netlist')

        if not os.path.exists(schem_netlist_path):
            os.makedirs(schem_netlist_path)

        if 'PDK_ROOT' in dsheet:
            pdk_root = dsheet['PDK_ROOT']
        else:
            pdk_root = get_pdk_root()

        if 'PDK' in dsheet:
            pdk = dsheet['PDK']
        else:
            pdk = get_pdk(magicfilename)

        newenv = os.environ.copy()
        if pdk_root and 'PDK_ROOT' not in newenv:
            newenv['PDK_ROOT'] = pdk_root
        if pdk and 'PDK' not in newenv:
            newenv['PDK'] = pdk

        tclstr = set_xschem_paths(dsheet, 'set lvs_netlist 1')

        # Xschem arguments:
        # -n:  Generate a netlist
        # -s:  Netlist type is SPICE
        # -r:  Bypass readline (because stdin/stdout are piped)
        # -x:  No X11 / No GUI window
        # -q:  Quit after processing command line
        # --tcl "set lvs_netlist 1":  Require ".subckt ... .ends" wrapper

        xschemargs = ['xschem', '-n', '-s', '-r', '-x', '-q', '--tcl', tclstr]

        # Use the PDK xschemrc file for xschem startup
        xschemrcfile = os.path.join(
            pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
        )
        if os.path.isfile(xschemrcfile):
            xschemargs.extend(['--rcfile', xschemrcfile])
        else:
            print('Error:  No xschemrc file found in the ' + pdk + ' PDK!')

        xschemargs.extend(['-o', schem_netlist_path, '-N', netlistname])
        xschemargs.append(schemfilename)
        if debug:
            print('Executing: ' + ' '.join(xschemargs))
            print('CWD is ' + root_path)

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
                print(line.decode('utf-8'))

            print(
                'Xschem process returned error code '
                + str(xproc.returncode)
                + '\n'
            )
        else:
            printwarn(xout)

        if not os.path.isfile(schem_netlist):
            print('Error: No netlist found for the circuit!\n')
            print(
                '(schematic netlist for simulation '
                + schem_netlist
                + ' not found.)\n'
            )

        else:
            # Do a quick parse of the netlist to check for errors
            missrex = re.compile('[ \t]*([^ \t]+)[ \t]+IS MISSING')
            with open(schem_netlist, 'r') as ifile:
                schemlines = ifile.read().splitlines()
                for line in schemlines:
                    mmatch = missrex.search(line)
                    if mmatch:
                        print('Error in netlist generation:')
                        print(
                            'Subcircuit ' + mmatch.group(1) + ' was not found!'
                        )
                        os.remove(schem_netlist)

    if need_schem_capture:
        if not os.path.isfile(schem_netlist):
            return False

    return schem_netlist


# -----------------------------------------------------------------------
# regenerate_testbench
#
# Regenerate a testbench template (create SPICE from .sch)
# -----------------------------------------------------------------------


def regenerate_testbench(dsheet, testbenchpath, testbench):

    runtime_options = dsheet['runtime_options']
    debug = runtime_options['debug']
    force_regenerate = runtime_options['force']

    paths = dsheet['paths']

    if not os.path.exists(testbenchpath):
        print('Error: Testbench path ' + testbenchpath + ' does not exist.')
        return 1

    need_testbench_netlist = False
    testbenchsource = os.path.splitext(testbench)[0] + '.sch'
    source_file = os.path.join(testbenchpath, testbenchsource)
    netlist_file = os.path.join(testbenchpath, testbench)

    if force_regenerate:
        need_testbench_netlist = True
    else:
        netlist_root = os.path.split(netlist_file)[1]
        print(
            'Checking for out-of-date testbench netlist ' + netlist_root + '.'
        )
        need_testbench_netlist = check_schematic_out_of_date(
            netlist_file, source_file, debug
        )

    if not need_testbench_netlist:
        # Testbench exists and is up-to-date;  nothing to do
        return 0

    if not os.path.isfile(source_file):
        print(
            'Error: No testbench netlist or source for testbench ' + testbench
        )
        return 1

    print('Generating testbench netlist ' + testbench + ' from schematic. . .')
    # Generate the netlist
    print('Calling xschem to generate netlist')

    # Root path
    if 'root' in paths:
        root_path = paths['root']
    else:
        root_path = '.'

    if 'PDK_ROOT' in dsheet:
        pdk_root = dsheet['PDK_ROOT']
    else:
        pdk_root = get_pdk_root()

    if 'PDK' in dsheet:
        pdk = dsheet['PDK']
    else:
        pdk = get_pdk(magicfilename)

    newenv = os.environ.copy()
    if pdk_root and 'PDK_ROOT' not in newenv:
        newenv['PDK_ROOT'] = pdk_root
    if pdk and 'PDK' not in newenv:
        newenv['PDK'] = pdk

    tclstr = set_xschem_paths(dsheet, '')
    xschemargs = ['xschem', '-n', '-s', '-r', '-x', '-q', '--tcl', tclstr]

    # Use the PDK xschemrc file for xschem startup
    xschemrcfile = os.path.join(
        pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
    )
    if os.path.isfile(xschemrcfile):
        xschemargs.extend(['--rcfile', xschemrcfile])
    else:
        print('Error:  No xschemrc file found in the ' + pdk + ' PDK!')

    xschemargs.extend(['-o', testbenchpath, '-N', testbench])
    xschemargs.append(os.path.join(testbenchpath, testbenchsource))
    if debug:
        print('Executing: ' + ' '.join(xschemargs))

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
            print(line.decode('utf-8'))

        print(
            'Xschem process returned error code '
            + str(xproc.returncode)
            + '\n'
        )
    else:
        printwarn(xout)

    # Do a quick parse of the netlist to check for errors
    missrex = re.compile('[ \t]*([^ \t]+)[ \t]+IS MISSING')
    with open(netlist_file, 'r') as ifile:
        schemlines = ifile.read().splitlines()
        for line in schemlines:
            mmatch = missrex.search(line)
            if mmatch:
                print('Error in netlist generation:')
                print('Subcircuit ' + mmatch.group(1) + ' was not found!')
                os.remove(netlist_file)

    if not os.path.isfile(netlist_file):
        print('Error: No netlist found for the testbench ' + testbench + '!')
        return 1

    return 0


# -----------------------------------------------------------------------
# Regenerate all netlists as needed when out of date.
# -----------------------------------------------------------------------


def regenerate_netlists(dsheet):

    # 'netlist_source' determines whether to use the layout extracted netlist
    # or the schematic captured netlist.  Also, regenerate the netlist only if
    # it is out of date, or if the user has selected forced regeneration in the
    # settings.

    runtime_options = dsheet['runtime_options']
    source = runtime_options['netlist_source']

    # PEX (parasitic capacitance-only) netlists are generated only by request.
    if source == 'pex':
        result = regenerate_lvs_netlist(dsheet, pex=True)
        # Also make sure LVS netlist is generated, in case LVS is run
        regenerate_lvs_netlist(dsheet)
        regenerate_schematic_netlist(dsheet)
        return result

    if source == 'all' or source == 'rcx' or source == 'best':
        result = regenerate_rcx_netlist(dsheet)

    made_lvs_netlist = False
    if (
        source == 'all'
        or source == 'layout'
        or (source == 'best' and result == False)
    ):
        made_lvs_netlist = True
        result = regenerate_lvs_netlist(dsheet)

    made_schem_netlist = False
    if (
        source == 'all'
        or source == 'schematic'
        or (source == 'best' and result == False)
    ):
        made_schem_netlist = True
        result = regenerate_schematic_netlist(dsheet)

    # If LVS is run while netlist source is RCX, then the LVS netlist should
    # also be generated.
    if source == 'rcx':
        if not made_lvs_netlist:
            regenerate_lvs_netlist(dsheet)
        if not made_schem_netlist:
            regenerate_schematic_netlist(dsheet)

    return result


# -----------------------------------------------------------------------
# Copy the schematic symbol to the testbench directory and remark its
# type from 'schematic' to 'primitive', so that testbench netlists will
# write an instance call but not the schematic itself.  That way, the
# schematic can be brought in from an include file that can be set to
# any one of schematic-captured or layout-extracted netlists.
# -----------------------------------------------------------------------


def make_symbol_primitive(dsheet):

    dname = dsheet['name']
    xschemname = dname + '.sym'

    paths = dsheet['paths']

    # Xschem schematic symbol
    if 'schematic' in paths:
        schempath = paths['schematic']
        symbolfilename = os.path.join(schempath, xschemname)
    else:
        schempath = None
        symbolfilename = None

    if not symbolfilename or not os.path.isfile(symbolfilename):
        print('Error:  symbol for project ' + dname + ' was not found!')
        return

    # Testbench primitive symbol
    if 'testbench' in paths:
        testbenchpath = paths['testbench']
    else:
        testbenchpath = 'testbench'

    primfilename = os.path.join(testbenchpath, xschemname)

    with open(symbolfilename, 'r') as ifile:
        symboldata = ifile.read()
        primdata = symboldata.replace('type=subcircuit', 'type=primitive')

    with open(primfilename, 'w') as ofile:
        ofile.write(primdata)


# -----------------------------------------------------------------------
# Regenerate all testbenches.
#
# If paramname is passed to regenerate_testbenches and is not None, then
# only generate testbenches required by the specified parameter.
# -----------------------------------------------------------------------


def regenerate_testbenches(dsheet, paramname=None):

    paths = dsheet['paths']
    if 'testbench' in paths:
        testbenchpath = paths['testbench']
    else:
        testbenchpath = 'testbench'

    # Copy the circuit symbol from schematic directory to testbench
    # directory and make it a primitive.
    make_symbol_primitive(dsheet)

    # Enumerate testbenches used in electrical parameters
    testbenchlist = []
    eparams = dsheet['electrical_parameters']

    for eparam in eparams:
        if paramname and paramname != eparam['name']:
            continue
        if 'simulate' in eparam:
            simlist = eparam['simulate']
            if isinstance(simlist, dict):
                simlist = [eparam['simulate']]

            for simdict in simlist:
                if 'template' in simdict:
                    testbenchlist.append(simdict['template'])

    testbenches_checked = {}
    for testbench in testbenchlist:
        if testbench in testbenches_checked:
            continue
        testbenches_checked[testbench] = True
        result = regenerate_testbench(dsheet, testbenchpath, testbench)
        if result != 0:
            print('Error in testbench generation.  Halting characterization.')
            return result

    return 0


# -----------------------------------------------------------------------
