#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# cace_simulate.py
#
#    Run a simulation (or co-simulation) according to the "simulate"
#    dictionary of electrical parameter "param".  This runs exactly
#    one simulation for the conditions defined in the testbench
#    dictionary "testbench".
#
#    Return 1 on a successful simulation or 0 if there was an error.
# ---------------------------------------------------------------------------

import os
import sys
import shutil
import re
import subprocess

from .cace_regenerate import get_pdk_root

# ---------------------------------------------------------------------------
# Main entry point for cace_simulate
#
#    "param" is the dictionary for a single electrical parameter from
# 	the project characterization datasheet.
#    "testbench" is the dictionary for a single testbench from the
# 	electrical parameter described by "param".
#    "pdk" is the (string) name of the PDK
#    "paths" is a dictionary defining a number of locations of files
# 	in the workspace.
# ---------------------------------------------------------------------------


def cace_simulate(param, testbench, pdk, paths, runtime_options):
    result = 0
    filename = testbench['filename']
    fileprefix = param['name']

    nosimmode = (
        runtime_options['nosim'] if 'nosim' in runtime_options else False
    )
    debug = runtime_options['debug'] if 'debug' in runtime_options else False

    # Prepare the list of simulation results
    testbench['results'] = []

    # Get the simulation record(s)
    simulatedict = param['simulate']
    if isinstance(simulatedict, list):
        simulatedict = param['simulate'][0]
        cosimdict = param['simulate'][1]
    else:
        cosimdict = None

    if 'format' not in simulatedict:
        # By default, assume use of wrdata.
        simulatedict['format'] = 'ascii .data null result'

    mformat = simulatedict['format']
    formatname = mformat[0]
    formatsuffix = mformat[1]
    formatvars = mformat[2:]

    # Make a list of the variable names in the 'variables' dictionaries:
    varnamelist = []
    if 'variables' in param:
        for vardict in param['variables']:
            varnamelist.append(vardict['name'])

    # Format variables *must* exist in the parameter's "variables".
    for varname in formatvars:
        if varname != 'null' and varname != 'result':
            if 'variables' not in param or varname not in varnamelist:
                print(
                    'Error:  Variable '
                    + varname
                    + ' is not in the variables list for parameter '
                    + param['name']
                )
                if debug:
                    print('Variables list is: ' + str(param['variables']))
                vardict = {}
                vardict['name'] = varname
                param['variables'].append(vardict)

    if not formatsuffix.startswith('.'):
        formatsuffix = '.' + formatsuffix

    # Note: filename already has the simulation directory path in it.
    simoutputfile = os.path.splitext(filename)[0] + formatsuffix

    # If specified from the CACE command line, determine if simulation
    # output file exists and skip the simulation if it does.  Note that
    # simulation output is immediately invalidated by a switch of the
    # project netlist's source (schematic capture vs. LVS netlist vs.
    # RCX netlist), so skipping simulations is inherently dangerous
    # and only supported as a debug option).

    needsim = True
    if nosimmode:
        if os.path.exists(simoutputfile):
            needsim = False

    if needsim:
        # Cosimulation:  If there is a '.tv' file in the simulation directory
        # with the same root name as the netlist file, then run iverilog and
        # vvp.  vvp will call ngspice from the verilog.
        # NOTE:  This needs to be redone assuming a "simulate" list with
        # multiple entries, and iverilog cosimulation is inferred from the
        # filename.  Needs to support both ngspice and Xyce methods.

        if cosimdict:
            simulator = cosimdict['tool'].split()[0]
            try:
                simargs = cosimdict['tool'].split()[1:]
            except:
                simargs = []
            filename = cosimdict['filename']

            # This section needs to be finished. . .
            print('Error:  Cosimulation is not yet implemented in CACE!')

        simulator = simulatedict['tool'].split()[0]
        try:
            simargs = simulatedict['tool'].split()[1:]
        except:
            simargs = []

        if simulator == 'ngspice':
            # Is there a .spiceinit file in the simulation directory, and is
            # one needed?
            if not os.path.exists('.spiceinit'):
                pdk_root = get_pdk_root()
                spinitfile = os.path.join(
                    pdk_root, pdk, 'libs.tech', 'ngspice', 'spinit'
                )
                if os.path.exists(spinitfile):
                    print('Copying ngspice configuration file from PDK.')
                    shutil.copy(spinitfile, '.spiceinit')

        # Capture all output from stdout and stderr.  Print each line in
        # real-time, and flush the output buffer.  All output is ignored.
        # Note:  bufsize = 1 and universal_newlines = True sets line-buffered output

        print(
            'Running: ' + simulator + ' ' + ' '.join(simargs) + ' ' + filename
        )
        print('Current working directory is: ' + os.getcwd())

        with subprocess.Popen(
            [simulator, *simargs, filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=True,
            universal_newlines=True,
        ) as spiceproc:
            pgroup = os.getpgid(spiceproc.pid)
            for line in spiceproc.stdout:
                print(line, end='')
                sys.stdout.flush()
                if 'Simulation interrupted' in line:
                    print('ngspice encountered an error. . . ending.')
                    spiceproc.kill()

        spiceproc.stdout.close()
        return_code = spiceproc.wait()
        if return_code != 0:
            print('Error:  ngspice exited with non-zero status!')

        # Clean up pipe file after cosimulation, also the .lxt file and .tvo files
        if cosimdict:
            if os.path.exists('simulator_pipe'):
                os.remove('simulator_pipe')

    # Read the output file from simulation into record testbench['results'].
    # NOTE:  Any column marked as 'result' in the simulation line is moved
    # to the first entry.  This makes the simulation['format'] incorrect,
    # and other routines (like cace_makeplot) will need to adjust it.

    if os.path.isfile(simoutputfile):
        result = 1
        with open(simoutputfile, 'r') as ifile:
            simlines = ifile.read().splitlines()
            for simline in simlines:
                idx = 0
                # Get the result
                newresult = []
                for token in simline.split():
                    try:
                        rname = formatvars[idx]
                        if rname == 'result':
                            newresult.append(token)
                        idx += 1
                    except:
                        print(
                            'CACE Simulation error:  format is missing entries'
                        )
                        print('simline is: ' + simline)
                        print('formatvars are: ' + ' '.join(formatvars))
                        break
                # Get the sweep condition values
                idx = 0
                for token in simline.split():
                    try:
                        rname = formatvars[idx]
                        if rname != 'null' and rname != 'result':
                            newresult.append(token)
                        idx += 1
                    except:
                        break
                testbench['results'].append(newresult)

        # Generate a 'format' entry in the testbench which modifies the original
        # simulation format for the next measurement.
        varnames = []
        varnames.append('result')
        for rname in formatvars[2:]:
            if rname != 'null' and rname != 'result':
                varnames.append(rname)
        testbench['format'] = varnames

    else:
        print('Error:  No output file ' + simoutputfile + ' from simulation!')

    return result


# ---------------------------------------------------------------------------
