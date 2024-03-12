#!/usr/bin/env python3
# --------------------------------------------------------------------------
# cace_launch.py
# --------------------------------------------------------------------------
#
# This script takes a dictionary in the CACE characterization format that
# has been read by either cace.py (command-line) or cace_gui.py (GUI) and
# processed by cace_gensim (cace_gensim.py) to produce a list of testbenches
# that need to be run for each specified electrical parameters.  It runs
# each specified simulation and produces an annotated dictionary with a
# list of all results.  It then passes the results of the simulation to
# the list of measurements specified in the parameter's "measure"
# dictionary to produce a final set of results per simulation.
#
# --------------------------------------------------------------------------

import os
import re
import sys
import shutil
import signal
import multiprocessing

from .cace_simulate import *
from .cace_measure import *

# ---------------------------------------------------------------------------
# collate_after_simulation
#
# If an electrical parameter's 'simulate' dictionary has a 'collate'
# entry, then "testbenchlist" is a list of testbenches for which to
# collate results.  Results from all testbenches are merged into the
# first testbench and removed from the others.  The results have the
# conditions specified in the 'collate' entry appended to each result
# list, and the testbench's 'format' entry is modified to include the
# names of the collated conditions.
#
# This routine can be used to collate *all* testbench simulations into
# a single record, but that is inefficient and forces all the simulations
# to be run sequentially (as currently coded).  Rather, the intention is
# that in some cases a measurement needs to operate on multiple results
# (such as gain error for a DAC needing to be measured at multiple points
# to calculate a slope for the gain), and those multiple results need to
# be passed to the measurement at the same time.  In cases were those
# multiple points can be produced by the simulation itself (such as with
# a DC sweep), all values will already be in a single testbench.  But in
# some cases (such as the DAC gain error) it is simpler/quicker to run
# an operating point in ngspice instead of a sweep or transient.
# ---------------------------------------------------------------------------


def collate_after_simulation(param, collnames, testbenchlist, debug):
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


# -----------------------------------------------------------------
# Exit the child process when SIGUSR1 is given to the process
# -----------------------------------------------------------------


def child_process_exit(signum, frame):
    print('CACE launch:  Received forced stop.')
    try:
        multiprocessing.current_process().terminate()
    except AttributeError:
        print('Terminate failed; Child PID is ' + str(os.getpid()))
        print('Waiting on process to finish.')


# ---------------------------------------------------------------------------
# simulate_and_measure:
#
# Run simulations and measurements on a single testbench or multiple
# testbenches whose output is to be collated before passing to the
# measurement.  Operations within simulate_and_measure() must be run
# in sequence and cannot be further parallelized (except see below).
# Return the altered testbench if the simulation and measurements were
# successful.
#
# To do:  Further parallelize the collated testbenches.
# ---------------------------------------------------------------------------


def simulate_and_measure(param, testbenchlist, pdk, paths, runtime_options):
    paramname = param['name']
    simresult = 0

    if 'pid' in runtime_options:
        os.setpgid(os.getpid(), runtime_options['pid'])
        signal.signal(signal.SIGUSR1, child_process_exit)

    for testbench in testbenchlist:
        simresult += cace_simulate(
            param, testbench, pdk, paths, runtime_options
        )

    debug = runtime_options['debug'] if 'debug' in runtime_options else False

    simdict = param['simulate']
    if 'collate' in simdict:
        collnames = simdict['collate']
        collate_after_simulation(param, collnames, testbenchlist, debug)

    # If results were collated, then all results have been moved to the first
    # testbench.  If not, then there is only one testbench.  Either way, the
    # first testbench gets pulled from the list and passed to cace_measure.

    if simresult != 0:
        tbzero = testbenchlist[0]
        simulations = cace_measure(param, tbzero, paths, debug)
    else:
        simulations = 0

    # Clean up simulation files if "keep" not specified as an option to CACE
    keepmode = runtime_options['keep'] if 'keep' in runtime_options else False

    if not keepmode:
        filename = testbench['filename']
        if os.path.isfile(filename):
            os.remove(filename)
        # Check for output files---suffix given in the "format" record
        simrec = param['simulate']
        if 'format' in simrec:
            formatline = simrec['format']
            suffix = formatline[1]
            outfilename = os.path.splitext(filename)[0] + suffix
            if os.path.isfile(outfilename):
                os.remove(outfilename)

    return tbzero if simulations > 0 else None


# ---------------------------------------------------------------------------
# Main entrypoint of cace_launch
#
# "dsheet" is a dictionary in the CACE characterization file format.
# "param" is the dictionary entry of a single electrical parameter.
#
# Return value is the modified parameter dictionary.
# ---------------------------------------------------------------------------


def cace_launch(dsheet, param):

    runtime_options = dsheet['runtime_options']
    pdk = dsheet['PDK']

    try:
        keepmode = runtime_options['keep']
    except:
        keepmode = False

    try:
        debug = runtime_options['debug']
    except:
        debug = False

    try:
        sequential = runtime_options['sequential']
    except:
        sequential = False

    paths = dsheet['paths']
    simfiles_path = paths['simulation']

    # Diagnostic:  find and print the number of files to be simulated
    # Names are methodname, pinname, and simulation number.
    totalsims = 0
    if 'testbenches' in param:
        totalsims += len(param['testbenches'])
        print('Total files to simulate: ' + str(totalsims))
    else:
        print('Skipping parameter ' + param['name'] + ' (no testbenches).')
        return param

    # Determine if testbenches are collated, and so need to be
    # simulated in groups
    idx = 0
    simdict = param['simulate']
    if 'group_size' in simdict:
        group_size = simdict['group_size']
    else:
        group_size = 1

    # Track how many simulations were successful
    simulations = 0

    # Each testbench of each electrical parameter can be run as an
    # independent simulation in parallel, so use multiprocessing
    # pools.  Note that the process forks do not share memory, so
    # the testbench returned from each process contains new data,
    # and the testbench records in the parameter must be rebuilt.

    if not sequential:
        alltestbenches = []
        with multiprocessing.Pool(
            processes=max(multiprocessing.cpu_count() - 1, 1)
        ) as pool:
            # "nice" this process to avoid throttling the OS
            os.nice(19)

            results = []

            # Run ngspice on each prepared simulation file
            # FYI; ngspice generates output directly to the TTY, bypassing stdout
            # and stdin, so that it can update the simulation time at the bottom
            # of the screen without scrolling.  Subvert this in ngspice, if possible.
            # It is a bad practice of ngspice to output to the TTY in batch mode. . .

            testbenches = param['testbenches']
            paramname = param['name']
            print(
                'Files to simulate method '
                + paramname
                + ': '
                + str(len(testbenches))
            )

            # Now run each simulation and read each simulation output file and
            # put together a composite 'results' record of result vs. condition
            # values.

            for i in range(0, len(testbenches), group_size):
                testbenchlist = testbenches[i : i + group_size]
                for testbench in testbenchlist:
                    testbench['sequence'] = idx
                results.append(
                    pool.apply_async(
                        simulate_and_measure,
                        (param, testbenchlist, pdk, paths, runtime_options),
                    )
                )
                idx += 1
            # Replace the testbench list in the parameter with the number of
            # testbenches.
            param['testbenches'] = len(param['testbenches'])

            for result in results:
                try:
                    presult = result.get(timeout=300)
                except Exception as e:
                    print('simulate_and_measure failed with exception:')
                    print(e)
                    presult = None
                if presult:
                    alltestbenches.append(presult)
                    simulations += group_size

        # After joining forks, 'results' contains an unordered list of
        # testbenches.  Because the forks do not share memory, these
        # testbenches are no longer the same as the ones in the datasheet,
        # so put everything back together here.

        # NOTE:  For collated testbenches, all testbenches within the
        # collated set *are* ordered, and the first one contains the
        # collated results, so the following code also serves to discard
        # the testbenches with empty results.

        maxidx = param['testbenches']

        param['testbenches'] = []
        for idx in range(0, maxidx):
            for testbench in alltestbenches:
                if testbench['sequence'] == idx:
                    param['testbenches'].append(testbench)
                    break

        for testbench in alltestbenches:
            testbench.pop('sequence')

    else:
        # Run simulations sequentially, not in multiprocessing mode
        paramname = param['name']
        testbenches = param['testbenches']
        print(
            'Files to simulate method '
            + paramname
            + ': '
            + str(len(testbenches))
        )
        for i in range(0, len(testbenches), group_size):
            testbenchlist = testbenches[i : i + group_size]
            if simulate_and_measure(
                param, testbenchlist, pdk, paths, runtime_options
            ):
                simulations += group_size

        # For grouped testbenches, remove all the testbenches that have no results
        if group_size > 1:
            newtestbenches = list(
                item for item in param['testbenches'] if 'results' in item
            )
            param['testbenches'] = newtestbenches

    # For all testbenches, remove the format
    for testbench in param['testbenches']:
        if 'format' in testbench:
            testbench.pop('format')

    print(
        'Completed '
        + str(simulations)
        + ' of '
        + str(totalsims)
        + ' simulations'
    )

    # Return the annotated electrical parameter
    return param


# ---------------------------------------------------------------------------
