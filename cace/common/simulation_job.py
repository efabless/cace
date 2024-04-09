#!/usr/bin/env python3

import os
import re
import sys
import shutil
import threading
import subprocess

from .cace_measure import *
from .cace_regenerate import get_pdk_root


class SimulationJob(threading.Thread):
    """
    The SimulationJob represents one simulation as part of
    an ElectricalParameter that is run via ngspice
    """

    def __init__(
        self,
        param,
        testbenchlist,
        pdk,
        paths,
        runtime_options,
        *args,
        **kwargs,
    ):
        self.param = param
        self.testbenchlist = testbenchlist
        self.pdk = pdk
        self.paths = paths
        self.runtime_options = runtime_options

        self.sim_complete_callback = None

        self.canceled = False
        self.spiceproc = None

        super().__init__(*args, **kwargs)

    def cancel(self, cancel_cb):
        print(f'Cancel simulation: {self.param["name"]} {self.testbenchlist}')
        self.canceled = True

        if cancel_cb:
            self.sim_complete_callback = None

        if self.spiceproc:
            self.spiceproc.kill()

    def run(self):
        paramname = self.param['name']
        simresult = 0

        if self.canceled:
            return None

        for testbench in self.testbenchlist:
            simresult += self.simulate(testbench)

            if self.canceled:
                return None

        debug = (
            self.runtime_options['debug']
            if 'debug' in self.runtime_options
            else False
        )

        print(f'simresult: {simresult}')

        simdict = self.param['simulate']
        if 'collate' in simdict:
            collnames = simdict['collate']
            print('collate_after_simulation!')
            self.collate_after_simulation(
                self.param, collnames, self.testbenchlist, debug
            )

        # If results were collated, then all results have been moved to the first
        # testbench.  If not, then there is only one testbench.  Either way, the
        # first testbench gets pulled from the list and passed to cace_measure.

        if simresult != 0:
            tbzero = self.testbenchlist[0]
            simulations = cace_measure(self.param, tbzero, self.paths, debug)
        else:
            simulations = 0

        # Clean up simulation files if "keep" not specified as an option to CACE
        keepmode = (
            self.runtime_options['keep']
            if 'keep' in self.runtime_options
            else False
        )

        if not keepmode:
            filename = testbench['filename']
            if os.path.isfile(filename):
                os.remove(filename)
            # Check for output files---suffix given in the "format" record
            simrec = self.param['simulate']
            if 'format' in simrec:
                formatline = simrec['format']
                suffix = formatline[1]
                outfilename = os.path.splitext(filename)[0] + suffix
                if os.path.isfile(outfilename):
                    os.remove(outfilename)

        return tbzero if simulations > 0 else None

    def collate_after_simulation(self, param, collnames, testbenchlist, debug):
        # Sanity check:  If there is only one testbench, then there is
        # nothing to collate.

        if len(testbenchlist) <= 1:
            return

        # Sanity check:  If 'collnames' is a single string, make it a list
        if isinstance(collnames, str):
            collnames = [collnames]

        # Step 1.  For each parameter name in 'collnames', add the
        # condition value after the result value, for each testbench.

        for name in collnames:
            for testbench in testbenchlist:
                conditions = testbench['conditions']
                try:
                    condition = next(
                        item for item in conditions if item[0] == name
                    )
                except:
                    print(
                        'Error:  Attempt to collate over condition '
                        + name
                        + ' which is not in the testbench condition list!'
                    )
                else:
                    value = condition[-1]
                    for result in testbench['results']:
                        result.append(value)

        # Step 2.  Extend the results of the first testbench by the
        # results of all the other testbenches.

        tbzero = testbenchlist[0]
        result = tbzero['results']
        for testbench in testbenchlist[1:]:
            result.extend(testbench['results'])

        # Step 3.  Remove the results from the other testbenches.

        for testbench in testbenchlist[1:]:
            testbench.pop('results')

        # Step 4.  Add the collated condition as a 'variables' record in
        # the testbench

        for condition in param['conditions']:
            if condition['name'] in collnames:
                # Only use entries 'name', 'display', 'unit', or 'note'
                newvariable = {}
                newvariable['name'] = condition['name']
                if 'display' in condition:
                    newvariable['display'] = condition['display']
                if 'unit' in condition:
                    newvariable['unit'] = condition['unit']
                if 'note' in condition:
                    newvariable['note'] = condition['note']
                condition.copy()
                if 'variables' in tbzero:
                    tbzero['variables'].append(newvariable)
                else:
                    tbzero['variables'] = [newvariable]

        # Step 5.  Remove the collated conditions from the first testbench

        prunedconditions = []
        for condition in tbzero['conditions']:
            if condition[0] not in collnames:
                prunedconditions.append(condition)
        tbzero['conditions'] = prunedconditions

        # Step 6.  Add the collated condition names to the format of the
        # first testbench.

        tbzero['format'].extend(collnames)

        # Step 7.  Remove the 'group_size' entry from the simulation dictionary
        simdict = param['simulate']
        if 'group_size' in simdict:
            simdict.pop('group_size')

    def simulate(self, testbench):
        result = 0
        filename = testbench['filename']
        fileprefix = self.param['name']

        nosimmode = (
            self.runtime_options['nosim']
            if 'nosim' in self.runtime_options
            else False
        )
        debug = (
            self.runtime_options['debug']
            if 'debug' in self.runtime_options
            else False
        )

        # Prepare the list of simulation results
        testbench['results'] = []

        # Get the simulation record(s)
        simulatedict = self.param['simulate']
        if isinstance(simulatedict, list):
            simulatedict = self.param['simulate'][0]
            cosimdict = self.param['simulate'][1]
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
        if 'variables' in self.param:
            for vardict in self.param['variables']:
                varnamelist.append(vardict['name'])

        # Format variables *must* exist in the parameter's "variables".
        for varname in formatvars:
            if varname != 'null' and varname != 'result':
                if 'variables' not in self.param or varname not in varnamelist:
                    print(
                        'Error:  Variable '
                        + varname
                        + ' is not in the variables list for parameter '
                        + self.param['name']
                    )
                    if debug:
                        print(
                            'Variables list is: '
                            + str(self.param['variables'])
                        )
                    vardict = {}
                    vardict['name'] = varname
                    self.param['variables'].append(vardict)

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
                        pdk_root, self.pdk, 'libs.tech', 'ngspice', 'spinit'
                    )
                    if os.path.exists(spinitfile):
                        print('Copying ngspice configuration file from PDK.')
                        shutil.copy(spinitfile, '.spiceinit')

            # Capture all output from stdout and stderr.  Print each line in
            # real-time, and flush the output buffer.  All output is ignored.
            # Note:  bufsize = 1 and universal_newlines = True sets line-buffered output

            print(
                'Running: '
                + simulator
                + ' '
                + ' '.join(simargs)
                + ' '
                + filename
            )
            print('Current working directory is: ' + os.getcwd())

            self.spiceproc = subprocess.Popen(
                [simulator, *simargs, filename],
                stdin=None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                preexec_fn=lambda: os.nice(10),
            )

            for line in self.spiceproc.stdout:
                print(line, end='')
                sys.stdout.flush()
                if 'Simulation interrupted' in line:
                    print('ngspice encountered an error. . . ending.')
                    self.spiceproc.kill()

            # self.spiceproc.stdout.close() TODO
            return_code = self.spiceproc.wait()

            if self.canceled:
                return result

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
            print(
                'Error:  No output file ' + simoutputfile + ' from simulation!'
            )

        return result
