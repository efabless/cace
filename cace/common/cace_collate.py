#!/usr/bin/env python3
# --------------------------------------------------------------------------
# cace_collate.py
# --------------------------------------------------------------------------
#
# This script follows cace_measure by taking the collection of output
# results generated for each set of conditions by the simulation and
# following measurements, calculating minimum/typical/maximum values
# for the set, and using the results to annotate the original
# characterization dataset.
#
# --------------------------------------------------------------------------

import os
import sys
import shutil
import json
import re
import math
import subprocess

from .spiceunits import spice_unit_unconvert
from .spiceunits import spice_unit_convert

from .cace_calculate import twos_complement

# ---------------------------------------------------------------------------
# find_limits ---
#
# Calculation of results from collected data for an output record, given
# the type of calculation to perform in 'calctype'.  The primary calculations
# are minimum, maximum, and typical, although these definitions are nuanced
# and the actual calculation performed is provided as a parameter.
#
# Future development:
# Add "minimax", "maximin", and "typical" to calctypes (needs extra record(s))
# Add "range" to limittypes (needs extra record or tuple for target)
#
#    "spectype" is one of "minimum", "maximum", or "typical".
#    "spec" is the list value of spectype in a parameter's "spec" dictionary.
# 	This is a numerical value that is the spec target, optionally followed
# 	by "pass" or "fail", where "fail" implies that exceeding the value is
# 	a failure to meet spec; and optionally followed by "calctype"-"limittype":
# 	"calctype" is one of:  average, minimum, maximum
# 	"limittype" is one of: above, below, exact
#    "results" is a list of rsult values
#    "units" is the units type (string) of the result value.
#
# The return value is a list in the same format as "spec" but where the
# first entry is the measured result, the second entry is the score
# ("pass" or "fail"), and there is no third entry.
#
# ---------------------------------------------------------------------------


def find_limits(spectype, spec, results, units, debug=False):

    # 'spec' is a list of [value, pass|fail, calculation-limit], but
    # if only "value" is present it may be interpreted as a string.

    if isinstance(spec, list):
        target = spec[0]
        penalty = spec[1] if len(spec) > 1 else 'pass'
        calcrec = spec[2] if len(spec) > 2 else spectype
    elif isinstance(spec, str):
        target = spec
        penalty = 'pass'
        calcrec = spectype

    # Prepare a list to return
    specresult = []

    binrex = re.compile(r'([0-9]*)\'([bodh])', re.IGNORECASE)

    # Note:
    # calctype = "minimum" alone implies "minimum-above"
    # calctype = "maximum" alone implies "maximum-below"
    # calctype = "average" alone implies "average-exact"
    # calctype = "typical" alone implies "average-exact"

    if debug:
        print('Diagnostic:  find_limits')
        print('spectype = ' + spectype)
        print('spec = ' + str(spec))
        print('results = ' + str(results))
        print('units = ' + units)
        print('target = ' + target)
        print('penalty = ' + penalty)
        print('calcrec = ' + calcrec)

    try:
        calctype, limittype = calcrec.split('-')
    except ValueError:
        calctype = calcrec
        if calctype == 'minimum':
            limittype = 'above'
        elif calctype == 'maximum':
            limittype = 'below'
        elif calctype == 'average':
            limittype = 'exact'
        elif calctype == 'typical':
            limittype = 'exact'
        elif calctype == 'diffmin':
            limittype = 'above'
        elif calctype == 'diffmax':
            limittype = 'below'
        else:
            # Diagnostic:
            print('Failure:  Unknown calculation type ' + calctype)
            return ['failure', 'fail']

    # Quick format sanity check---may need binary or hex conversion
    # using the units nomenclature of 'b or 'h, etc.
    # (to be done:  signed conversion, see cace_makeplot.py)

    if isinstance(results[0], str):
        bmatch = binrex.match(units)
        if bmatch:
            digits = bmatch.group(1)
            if digits == '':
                digits = len(results[0])
            else:
                digits = int(digits)
            base = bmatch.group(2)
            if base == 'b':
                a = list(int(x, 2) for x in results)
            elif base == 'o':
                a = list(int(x, 8) for x in results)
            elif base == 'd':
                a = list(int(x, 10) for x in results)
            else:
                a = list(int(x, 16) for x in results)
            results = list(twos_complement(x, digits) for x in a)
        elif results[0] != 'failure':
            print('Warning: result data do not correspond to specified units.')
            print('Data = ' + str(results))
            return ['failure', 'fail']

    # The target and result should both match the specified units, so convert
    # the target if it is a binary, hex, etc., value.
    if target != 'any':
        targval = target
        bmatch = binrex.match(units)
        if bmatch:
            digits = bmatch.group(1)
            base = bmatch.group(2)
            if digits == '':
                digits = len(targval)
            else:
                digits = int(digits)
            try:
                if base == 'b':
                    a = int(targval, 2)
                elif base == 'o':
                    a = int(targval, 8)
                elif base == 'd':
                    a = int(targval, 10)
                else:
                    a = int(targval, 16)
                targval = twos_complement(a, digits)
            except:
                print(
                    'Warning: target data do not correspond to units; assuming integer.'
                )

    # First run the calculation to get the single result value

    if calctype == 'minimum':
        # Result is the minimum of the data
        value = min(results)
    elif calctype == 'maximum':
        # Result is the maximum of the data
        value = max(results)
    elif calctype == 'average' or calctype == 'typical':
        # Result is the average of the data
        value = sum(results) / len(results)
    elif calctype[0:3] == 'std':
        # Result is the standard deviation of the data
        mean = sum(results) / len(results)
        value = pow(
            sum([((i - mean) * (i - mean)) for i in results]) / len(results),
            0.5,
        )
        # For "stdX", where "X" is an integer, multiply the standard deviation by X
        if len(calctype) > 3:
            value *= int(calctype[3])

        if len(calctype) > 4:
            # For "stdXn", subtract X times the standard deviation from the mean
            if calctype[4] == 'n':
                value = mean - value
            # For "stdXp", add X times the standard deviation to the mean
            elif calctype[4] == 'p':
                value = mean + value
    elif calctype == 'diffmax':
        value = max(results) - min(results)
    elif calctype == 'diffmin':
        value = min(results) - max(results)
    else:
        return ['failure', 'fail']

    try:
        specresult.append('{0:.4g}'.format(value))
    except ValueError:
        print(
            'Warning: Min/Typ/Max value is not not numeric; value is '
            + str(value)
        )
        return ['failure', 'fail']

    # Next calculate the score based on the limit type

    score = 'pass'
    if limittype == 'above':
        # Score a penalty if value is below the target
        if target != 'any' and penalty == 'fail':
            targval = float(target)

            if debug:
                print('minimum = ' + str(value))
            # NOTE: 0.0005 value corresponds to formatting above, so the
            # value is not marked in error unless it would show a different
            # value in the display.
            if value < targval - 0.0005:
                score = 'fail'
                if debug:
                    print('fail: target = ' + str(score) + '\n')
            elif math.isnan(value):
                score = 'fail'

    elif limittype == 'below':
        # Score a penalty if value is above the target
        if target != 'any' and penalty == 'fail':
            targval = float(target)

            if debug:
                print('maximum = ' + str(value))
            # NOTE: 0.0005 value corresponds to formatting above, so the
            # value is not marked in error unless it would show a different
            # value in the display.
            if value > targval + 0.0005:
                score = 'fail'
                if debug:
                    print('fail: target = ' + str(score))
            elif math.isnan(value):
                score = 'fail'

    elif limittype == 'exact':
        # Score a penalty if value is not equal to the target
        if target != 'any' and penalty == 'fail':
            targval = float(target)

            if value != targval:
                score = 'fail'
                if debug:
                    print('off-target failure')
            elif math.isnan(value):
                score = 'fail'

    # Note:  Calctype 'none' performs no calculation.  Record is unchanged,
    # and "score" is returned unchanged.

    specresult.append(score)
    return specresult


# ----------------------------------------------------------------------
# incompleteresult --
#
# Handle errors where simulation generated no output.
# This is the one case where 'typical' can be treated as pass-fail.
# score will be set to "incomplete" for any of "minimum", "maximum",
# and "typical" that exists in the electrical parameters record
# and which specifies a target value.  "value" is set to "failure"
# for display.
# ----------------------------------------------------------------------


def incompleteresult(param, noplotmode=False):

    resultdict = {}

    if 'plot' in param:
        if noplotmode == False:
            resultdict['status'] = 'incomplete'

    if 'spec' not in param:
        return resultdict

    spec = param['spec']

    if 'typical' in spec:
        typrec = spec['typical']
        typresult = ['failure']
        if typrec[0] != 'any':
            typresult.append('incomplete')
        resultdict['typical'] = typresult

    if 'maximum' in spec:
        maxrec = spec['maximum']
        maxresult = ['failure']
        if maxrec[0] != 'any':
            maxresult.append('incomplete')
        resultdict['maximum'] = maxresult

    if 'minimum' in spec:
        minrec = spec['minimum']
        minresult = ['failure']
        if minrec[0] != 'any':
            minresult.append('incomplete')
        resultdict['minimum'] = minresult

    return resultdict


# -------------------------------------------------------------
# addnewresult --
#
# If the result dictionary has the same name as one in the
# datasheet, then it replaces it.  Otherwise it is appended
# to the list.
# -------------------------------------------------------------


def addnewresult(param, resultdict):
    replaced = False
    if 'results' in param:
        newresultlist = []
        paramresults = param['results']
        if not isinstance(paramresults, list):
            paramresults = [paramresults]
        for result in paramresults:
            if result['name'] == resultdict['name']:
                newresultlist.append(resultdict)
                replaced = True
            else:
                newresultlist.append(result)
        if replaced == False:
            newresultlist.append(resultdict)
        param['results'] = newresultlist
    else:
        param['results'] = resultdict


# ---------------------------------------------------------------------------
# Main entry point of cace_collate
#
# "param" is an electrical parameter dictionary to be evaluated.
# The "param" dictionary is annotated with results; and the modified
# dictionary is returned.
#
# At the end of running all measurements, there should be a number of
# "testbench" records for the parameter, each containing a unique set of
# conditions, and a "results" section which is normally a single value
# (see code comments about dealing with multiple values).
# ---------------------------------------------------------------------------


def cace_collate(dsheet, param):

    runtime_options = dsheet['runtime_options']
    try:
        debug = runtime_options['debug']
    except:
        debug = False

    try:
        keepmode = runtime_options['keep']
    except:
        keepmode = False

    try:
        noplotmode = runtime_options['noplot']
    except:
        noplotmode = False

    if 'default_conditions' in dsheet:
        default_conditions = dsheet['default_conditions']
    else:
        default_conditions = []

    total = 0

    if 'status' in param:
        status = param['status']
    else:
        status = 'active'
        param['status'] = status

    if status == 'skip' or status == 'blocked' or 'testbenches' not in param:
        if debug:
            print('Parameter ' + param['name'] + ' skipped for evaluation.')
        return param

    paramname = param['name']
    status = param['status']

    # Process only entries in dataset that have 'testbenches' record
    if status == 'skip' or status == 'blocked':
        return param

    elif 'testbenches' not in param:
        if debug:
            print(
                'Error:  Parameter '
                + paramname
                + ' specified to be evaluated, but no testbench record exists.'
            )
        return param
    elif debug:
        print('Collating results for parameter ' + paramname)

    if 'spec' in param:
        spec = param['spec']
    else:
        spec = {}
    testbenches = param['testbenches']

    # Each item in "testbenches" has a filename (was simulated in
    # cace_launch and is no longer used), a set of conditions (prepared
    # by cace_gensim), and a set of results (read back from simulation
    # output by cace_launch).  There may be multiple results which are
    # dependent on variables not in the "conditions" list;  these
    # variables are listed in the "format" line of the "measure"
    # dictionary that was used to understand the simulation output.

    # This information is used to create a single large matrix of the
    # result vs. all conditions and variables for the electrical
    # parameter as a whole.  That matrix may be passed through additional
    # evaluators (specified in the "evaluate" dictionary) to modify the
    # result and potentially reduce the number of variables.  The final
    # output is stored in the "results" list for the electrical parameter.
    # Finally, the "results" list is scanned to extract minimum, typical,
    # and maximum values as required for the datasheet.

    # Policy regarding testbench failures:  If any testbench has failed,
    # the score is set to "incomplete".  If a portion of testbench
    # simulations ran and some failed, then the score may be changed to
    # "fail".

    score = 'pass'
    for testbench in testbenches:
        filename = testbench['filename']
        if 'results' not in testbench:
            print('Error: testbench ' + filename + ' has no results!')
            score = 'incomplete'
            break
        else:
            results = testbench['results']
            if len(results) == 0:
                print(
                    'Error: testbench '
                    + filename
                    + ' has zero-length results!'
                )
                score = 'incomplete'
                break

    typresults = []
    if 'typical' in spec:
        # Generate a list of results that were made under conditions
        # that were either typical or did not specify a typical value.

        for testbench in testbenches:
            istypical = True
            for condition in testbench['conditions']:
                # Pull record of the condition (by definition this must
                # exist in either the electrical parameter conditions list
                # or the default conditions list).
                try:
                    condrec = next(
                        item
                        for item in param['conditions']
                        if item['name'] == condition[0]
                    )
                except StopIteration:
                    condrec = next(
                        item
                        for item in default_conditions
                        if item['name'] == condition[0]
                    )

                if 'typical' in condrec:
                    typvalue = condrec['typical']
                    if typvalue != condition[-1]:
                        istypical = False
                        break
            if istypical == True:
                if 'results' in testbench:
                    typresults.extend(testbench['results'])

    allresults = []
    for testbench in testbenches:
        if 'results' in testbench:
            allresults.extend(testbench['results'])

    # Results is still a list of lists.  Pull out the inner list.
    # Flag a warning if the inner list isn't just a single item
    # (the result), unless 'plot' is specified and not 'spec',
    # in which case this is normal.

    isplotdata = True if 'spec' not in param and 'plot' in param else False

    if len(allresults) == 0:
        scaled_results = []
    else:
        reduced_results = []
        if isinstance(allresults[0], list):
            for result in allresults:
                if len(result) > 1:
                    if not isplotdata:
                        print(
                            'Error:  There are multiple results per testbench!'
                        )
                try:
                    rvalue = float(result[0])
                except:
                    try:
                        print(
                            'Error:  Result '
                            + str(result[0])
                            + ' is not numeric!'
                        )
                    except:
                        print('Error:  No result!')
                    rvalue = 0.0
                reduced_results.append(rvalue)
        else:
            for result in allresults:
                try:
                    rvalue = float(result)
                except:
                    print('Error:  Result ' + str(result) + ' is not numeric!')
                    rvalue = 0.0
                reduced_results.append(rvalue)

        # scaled_results is 'results' scaled to the units used by param.
        if 'unit' in param:
            scaled_results = spice_unit_unconvert(
                [param['unit'], reduced_results]
            )
        else:
            scaled_results = reduced_results

    # Now do the same to the typical result set.

    if len(typresults) == 0:
        scaled_typresults = []
    else:
        reduced_results = []
        if isinstance(typresults[0], list):
            for result in typresults:
                if len(result) > 1:
                    if not isplotdata:
                        print(
                            'Error:  There are multiple results per testbench!'
                        )
                try:
                    rvalue = float(result[0])
                except:
                    try:
                        print(
                            'Error:  Result '
                            + str(result[0])
                            + ' is not numeric!'
                        )
                    except:
                        print('Error:  No result!')
                    rvalue = 0.0
                reduced_results.append(rvalue)
        else:
            for result in typresults:
                try:
                    rvalue = float(result)
                except:
                    print('Error:  Result ' + str(result) + ' is not numeric!')
                    rvalue = 0.0
                reduced_results.append(rvalue)

        # scaled_results is 'results' scaled to the units used by param.
        if 'unit' in param:
            scaled_typresults = spice_unit_unconvert(
                [param['unit'], reduced_results]
            )
        else:
            scaled_typresults = reduced_results

    # Set the value of "units" passed to find_limits()
    if 'unit' in param:
        units = param['unit']
    else:
        units = ''

    # Diagnostic
    if debug:
        print('Scaled results are:')
        if len(scaled_results) > 20:
            print('(truncated due to length)')
            print(str(scaled_results[0:10]))
            print('...')
            print(str(scaled_results[-10:-1]))
        else:
            print(str(scaled_results))
        if 'typical' in spec:
            print('Scaled typical results are:')
            if len(scaled_typresults) > 20:
                print('(truncated due to length)')
                print(str(scaled_typresults[0:10]))
                print('...')
                print(str(scaled_typresults[-10:-1]))
            else:
                print(str(scaled_typresults))

    # Calculate minimum/typical/maximum results for the electrical parameter
    if len(scaled_results) == 0:
        if 'minimum' in spec or 'maximum' in spec:
            resultdict = incompleteresult(param, noplotmode)
        else:
            resultdict = {}
    else:
        resultdict = {}
        if 'minimum' in spec:
            spectype = 'minimum'
            minrec = spec['minimum']
            minresult = find_limits(
                spectype, minrec, scaled_results, units, debug
            )
            if score == 'incomplete' and minresult[1] == 'fail':
                score = 'fail'
            elif score != 'fail':
                score = minresult[1]
            resultdict['minimum'] = minresult

        if 'maximum' in spec:
            spectype = 'maximum'
            maxrec = spec['maximum']
            maxresult = find_limits(
                spectype, maxrec, scaled_results, units, debug
            )
            if score == 'incomplete' and maxresult[1] == 'fail':
                score = 'fail'
            elif score != 'fail':
                score = maxresult[1]
            resultdict['maximum'] = maxresult

    if len(scaled_typresults) == 0:
        if 'typical' in spec:
            resultdict = incompleteresult(param, noplotmode)
    else:
        if 'typical' in spec:
            spectype = 'typical'
            typrec = spec['typical']
            typresult = find_limits(
                spectype, typrec, scaled_typresults, units, debug
            )
            if score == 'incomplete' and typresult == 'fail':
                score = 'fail'
            elif score != 'fail':
                score = typresult[1]
            resultdict['typical'] = typresult

    # Results belong to a key name in the electrical parameter that
    # depends on where the source netlists came from.

    resultdict['name'] = runtime_options['netlist_source']
    if debug:
        print(
            'Adding new result set '
            + resultdict['name']
            + ' for '
            + param['name']
        )
    addnewresult(param, resultdict)

    # Return the annotated electrical parameter
    return param


# ---------------------------------------------------------------------------
