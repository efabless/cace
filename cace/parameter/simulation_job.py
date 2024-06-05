#!/usr/bin/env python3

import os
import re
import sys
import shutil
import threading
import subprocess

from ..common.cace_measure import *
from ..common.cace_regenerate import get_pdk_root
from ..common.ring_buffer import RingBuffer

from ..logging import (
    verbose,
    debug,
    info,
    rule,
    success,
    warn,
    err,
)

# TODO
from ..logging import subprocess as subproc
from ..logging import debug as dbg


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
        param_dir,
        idx,
        *args,
        **kwargs,
    ):
        self.param = param
        self.testbenchlist = testbenchlist
        self.pdk = pdk
        self.paths = paths
        self.runtime_options = runtime_options
        self.param_dir = param_dir
        self.idx = idx

        self.cb = None

        self.canceled = False
        self.spiceproc = None

        super().__init__(*args, **kwargs)
        self._return = None

    def cancel(self, cancel_cb):
        # print(f'{self.param["name"]}: Cancel simulation: {self.testbenchlist}')
        self.canceled = True

        if cancel_cb:
            self.cb = None

        if self.spiceproc:
            self.spiceproc.kill()

    def cancel_point(self):
        """If canceled, call the cb and exit the thread"""

        if self.canceled:
            if self.cb:
                self.cb(self.param['name'], self.testbenchlist, True)
            sys.exit()

    def run(self):
        paramname = self.param['name']
        simresult = 0

        self.cancel_point()

        for i, testbench in enumerate(self.testbenchlist):
            simresult += self.simulate(testbench, i)

            self.cancel_point()

        debug = (
            self.runtime_options['debug']
            if 'debug' in self.runtime_options
            else False
        )

        simdict = self.param['simulate']
        if 'collate' in simdict:
            collnames = simdict['collate']
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

        # For when the join function is called
        self._return = tbzero if simulations > 0 else None
        return self._return

    def join(self, *args):
        threading.Thread.join(self, *args)
        return self._return

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
                    err(
                        f'Attempt to collate over condition {name} which is not in the testbench condition list!'
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

    def simulate(self, testbench, idy):
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
                    err(
                        f'Error:  Variable {varname} is not in the variables list for parameter {self.param["name"]}'
                    )
                    dbg(f'Variables list is: {self.param["variables"]}')
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
                warn(
                    'Output file exists and nosimmode is set. No simulation is run.'
                )

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
                err('Cosimulation is not yet implemented in CACE!')

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
                        info(
                            'Copying ngspice ".spiceinit" configuration file from PDK.'
                        )
                        shutil.copy(spinitfile, '.spiceinit')

                # Run simulations in batch mode
                # (exit after end of simulation)
                if not '-b' in simargs and not '--batch' in simargs:
                    simargs.append('--batch')

            # Capture all output from stdout and stderr.  Print each line in
            # real-time, and flush the output buffer.  All output is ignored.
            # Note:  bufsize = 1 and universal_newlines = True sets line-buffered output

            dbg(f'Running: {simulator} {" ".join(simargs)} {filename}')
            dbg('Current working directory is: ' + os.getcwd())

            if len(self.testbenchlist) == 1:
                log_path = os.path.join(
                    self.param_dir, f'ngspice_{self.idx}.log'
                )
            else:
                log_path = os.path.join(
                    self.param_dir, f'ngspice_{self.idx}_{idy}.log'
                )

            log_file = open(log_path, 'w')

            info(
                f'Parameter {self.param["name"]}: Logging to [repr.filename][link=file://{os.path.abspath(log_path)}]{os.path.relpath(log_path)}[/link][/repr.filename]…'
            )

            self.spiceproc = subprocess.Popen(
                [simulator, *simargs, filename],
                stdin=None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                preexec_fn=lambda: os.nice(10),
            )

            line_buffer = RingBuffer(str, 10)
            for line in self.spiceproc.stdout:
                dbg(line.rstrip('\n'))
                # sys.stdout.flush()
                log_file.write(line)
                line_buffer.push(line)

                # TODO
                """if 'Simulation interrupted' in line:
                    print('ngspice encountered an error. . . ending.')
                    self.spiceproc.kill()"""

            # self.spiceproc.stdout.close() TODO needed?
            return_code = self.spiceproc.wait()

            if return_code != 0:
                err('Subprocess ngspice exited with non-zero status.')
                concatenated = ''
                for line in line_buffer:
                    concatenated += line
                if concatenated.strip() != '':
                    err(
                        f'Last {len(line_buffer)} line(s):\n'
                        + escape(concatenated)
                    )
                err(f"Full log file: '{os.path.relpath(log_path)}'")
                return result   # 0

            if self.canceled:
                return result

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
                            err(
                                'CACE Simulation error: format is missing entries'
                            )
                            err('simline is: ' + simline)
                            err('formatvars are: ' + ' '.join(formatvars))
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
            err(f'No output file {simoutputfile} from simulation')
            return 0

        return result
