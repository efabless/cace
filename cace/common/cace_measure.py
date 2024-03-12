#!/usr/bin/env python3
# --------------------------------------------------------------------------
# cace_measure.py
# --------------------------------------------------------------------------
#
# This script runs a measurement or sequence of measurements as specified
# in the "measure" section of an electrical parameter, processing the
# results of a specific testbench, and producing a new set of results,
# potentially with a reduced set of results.  Ideally, for final collation
# of results, each testbench resolves to a single result value.
#
# Measurements can be either a tool such as 'octave', which is run using
# subprocess and given a script input that is provided in the testbench
# directory, or uses one of the CACE built-in measurements, defined in
# cace_calculate.py.
#
# --------------------------------------------------------------------------

import os
import sys
import shutil
import json
import re
import subprocess

from .cace_calculate import *

from .spiceunits import spice_unit_unconvert
from .spiceunits import spice_unit_convert

# ---------------------------------------------------------------------------
# results_to_octave ---
#
#    Generate an output file named <testbench_name>.dat which contains the
#    matrix of results for the testbench, in a format for input to an
#    octave script.
# ---------------------------------------------------------------------------


def results_to_octave(testbench, units):

    testbenchname = os.path.splitext(testbench['filename'])[0]
    datfilename = testbenchname + '.dat'
    results = testbench['results']
    conditions = testbench['conditions']

    # First structure is a list of names.  The first is "result"
    # followed by the names of all the conditions.
    outnames = []
    outnames.append('result')
    for condition in conditions:
        outnames.append(condition[0])

    # Any variables called out in the format get added after the conditions
    formatlist = testbench['format']
    varnames = []
    if isinstance(formatlist, list):
        for varname in formatlist:
            if varname != 'result' and varname != 'null':
                varnames.append(varname)
                outnames.append(varname)

    # Second structure is a list of units corresponding to each name.
    outunits = []
    outunits.append(units)
    for condition in conditions:
        outunits.append(condition[1] if len(condition) == 3 else '')

    for varname in varnames:
        varrec = next(
            item for item in testbench['variables'] if item['name'] == varname
        )
        if 'unit' in varrec:
            outunits.append(varrec['unit'])
        else:
            outunits.append('')

    # Third structure is a list of values corresponding to each name.
    outvalues = []
    for result in results:
        outvalueline = []
        outvalueline.append(result[0])
        for condition in conditions:
            outvalueline.append(condition[-1])
        if len(result) > 1:
            outvalueline.append(result[1:])
        outvalues.append(outvalueline)

    # Now write the octave file

    with open(datfilename, 'w') as ofile:
        print('# Created by cace_measure.py', file=ofile)
        print('# name: results', file=ofile)
        print('# type: scalar struct', file=ofile)
        print('# ndims: 2', file=ofile)
        print('# 1 1', file=ofile)
        numentries = len(outnames)
        print('# length: ' + str(2 + numentries), file=ofile)
        print('# name: NAMES', file=ofile)
        print('# type: cell', file=ofile)
        print('# rows: ' + str(numentries), file=ofile)
        print('# columns: 1', file=ofile)
        for name in outnames:
            print('# name: <cell-element>', file=ofile)
            print('# type: sq_string', file=ofile)
            print('# elements: 1', file=ofile)
            print('# length: ' + str(len(name)), file=ofile)
            print(name, file=ofile)
            print('', file=ofile)
            print('', file=ofile)

        print('', file=ofile)
        print('', file=ofile)
        print('# name: UNITS', file=ofile)
        print('# type: cell', file=ofile)
        print('# rows: ' + str(len(outunits)), file=ofile)
        print('# columns: 1', file=ofile)
        for unit in outunits:
            print('# name: <cell-element>', file=ofile)
            print('# type: sq_string', file=ofile)
            print('# elements: 1', file=ofile)
            print('# length: ' + str(len(unit)), file=ofile)
            print(unit, file=ofile)
            print('', file=ofile)
            print('', file=ofile)
        print('', file=ofile)
        print('', file=ofile)

        # Each condition is output as a 1D array with structure
        # entry name equal to the condition name.  If the units
        # is empty then the array is a string.  Otherwise, the
        # array is numeric (as far as octave is concerned).

        # First entry is the testbench result.  This should never
        # be a string (at least not in this version of CACE)

        idx = 0
        print('# name: RESULT', file=ofile)
        units = outunits[idx]
        print('# type: matrix', file=ofile)
        print('# rows: ' + str(len(outvalues)), file=ofile)
        print('# columns: 1', file=ofile)
        for outvalueline in outvalues:
            print(' ' + str(outvalueline[idx]), file=ofile)
        print('', file=ofile)
        print('', file=ofile)

        idx += 1
        # The rest of the entries are the conditions.  Note that the
        # name must be a valid octave variable (letters, numbers,
        # underscores) and so cannot use the condition name.  However,
        # each condition name is held in the names list, so it can be
        # recovered.  Each condition is called CONDITION2, CONDITION3,
        # etc.

        while idx < len(outvalues[0]):

            print('# name: CONDITION' + str(idx + 1), file=ofile)
            units = outunits[idx]
            if units == '':
                # Use cell array for strings
                print('# type: cell', file=ofile)
                print('# rows: ' + str(len(outvalues)), file=ofile)
                print('# columns: 1', file=ofile)
                for outvalueline in outvalues:
                    # Check for list arrays.
                    value = outvalueline[idx]
                    if isinstance(value, list):
                        value = ' '.join(outvalueline[idx])
                    print('# name: <cell-element>', file=ofile)
                    print('# type: sq_string', file=ofile)
                    print('# elements: 1', file=ofile)
                    print('# length: ' + str(len(str(value))), file=ofile)
                    print(str(value), file=ofile)
                    print('', file=ofile)
                    print('', file=ofile)
            else:
                print('# type: matrix', file=ofile)
                print('# rows: ' + str(len(outvalues)), file=ofile)
                print('# columns: 1', file=ofile)
                for outvalueline in outvalues:
                    value = outvalueline[idx]
                    print(' ' + str(value), file=ofile)

            print('', file=ofile)
            print('', file=ofile)
            idx += 1

    return datfilename


# ---------------------------------------------------------------------------
# results_to_json:
#
#    Generate an output file named <testbench_name>.json which contains the
#    matrix of results for the testbench, in JSON format for input to any
#    script that can read JSON format.
# ---------------------------------------------------------------------------


def results_to_json(testbench):

    testbenchname = os.path.splitext(testbench['filename'])[0]
    datfilename = testbenchname + '.json'
    results = testbench['results']

    with open(datfilename, 'w') as ofile:
        json.dump(results, ofile, indent=4)

    return datfilename


# ---------------------------------------------------------------------------
# Execute one measurement on the simulation data
# ---------------------------------------------------------------------------


def cace_run_measurement(param, measure, testbench, paths, debug=False):

    testbench_path = paths['testbench']
    simulation_path = paths['simulation']
    root_path = paths['root']

    testbenchname = param['name']

    # "testbench" is a single dictionary from the list of testbenches
    # specified for an electrical parameter from a CACE datasheet.
    # It has a filename (was simulated in cace_simulate and is no longer
    # used), a set of conditions (originally prepared by cace_gensim), and
    # a set of results (read back after simulation by cace_simulate).  There
    # may be multiple results which are dependent on variables not in the
    # "conditions" list;  these variables are listed in the "format" line of
    # the "measure" dictionary that was used to understand the simulation output,
    # Any variable that is not either "results" or "null" must be in the
    # parameter's "variables" list.  Each measurement produces a modified
    # set of results.

    if 'calc' in measure:
        # Measurement is an internal calculation type.
        cace_calculate(param, measure, testbench, debug)

    elif 'tool' in measure:
        tool = measure['tool']
        scriptname = os.path.join(testbench_path, measure['filename'])

        if tool == 'octave' or tool == 'octave-cli' or tool == 'matlab':
            tool = 'octave-cli'
            units = param['unit']
            filename = results_to_octave(testbench, units)
        else:
            filename = results_to_json(testbench)

        # Now run the specified octave script on the result.  Script
        # generates an output file.  stdout/stderr can be ignored.
        # May want to watch stderr for error messages and/or handle
        # exit status.

        print('Measuring with: ' + tool + ' ' + scriptname + ' ' + filename)
        postproc = subprocess.Popen(
            [tool, scriptname, filename], stdout=subprocess.PIPE, cwd=root_path
        )
        rvalues = postproc.communicate()[0].decode('ascii').splitlines()

        # Replace testbench result with the numeric result
        testbench['results'] = list(float(item) for item in rvalues)
        return 1

    else:
        print(
            'Error: Measurement record does not contain either "tool" or "calc".'
        )
        return 0


# ---------------------------------------------------------------------------
# Main entry point for cace_measure
#
#    "param" is the dictionary from the datasheet for a single electrical
# 	parameter.
#    "testbench" is the dictionary for a single testbench of the parameter.
#    "paths" is the dictionary from the datasheet defining a number of
# 	locations of files in the workspace.
# ---------------------------------------------------------------------------


def cace_measure(param, testbench, paths, debug=False):
    measurements = 1

    testbench_path = paths['testbench']

    if 'measure' in param:
        if isinstance(param['measure'], list):
            measurelist = param['measure']
        else:
            measurelist = [param['measure']]
    else:
        measurelist = []

    for measure in measurelist:
        result = cace_run_measurement(param, measure, testbench, paths, debug)
        if result == 0:
            measurements = 0
            break

    if measurements == 1:
        # If the simulations were collated before measurement, then remove
        # the collated variable(s) from 'format':
        simdict = param['simulate']
        if 'collate' in simdict:
            collnames = simdict['collate']
            tbformat = list(
                item for item in testbench['format'] if item not in collnames
            )
            testbench['format'] = tbformat

        # If the parameter defines a "spec", then check that the testbench
        # results contain lists of only one item, the result.
        if 'spec' in param:
            if len(testbench['format']) != 1:
                print('Error:  Testbench result contains variables!')
                varlist = list(
                    item for item in testbench['format'] if item != 'result'
                )
                print('Variables found: ' + ' '.join(varlist))
                # However, don't terminate but pass this to collation anyway.

    return measurements


# ---------------------------------------------------------------------------
