#!/usr/bin/env python3
#--------------------------------------------------------------------------
# cace_unused.py
#--------------------------------------------------------------------------
#
# Location of any code written for the original CACE system that has not
# been folded into the new code but may be relevant.
#
#--------------------------------------------------------------------------

import os
import sys
import shutil
import json
import re
import datetime
import subprocess


def cace_measure_orig(testbench):

    results = testbench['results']
    format = testbench['format']

    for rlist in results:

        # "variables" are similar to conditions but describe what is
        # being output from ngspice.  There should be one entry for
        # each (unique) column in the data file, matching the names
        # given in the testbench file.

        if 'variables' in param:
            pvars = param['variables']
        else:
            pvars = []

        # Parse all additional variables.  At least one (the
        # analysis variable) must be specified.
        data_args = []
        extra = rest.split()

        if len(extra) == 1:
            # If the testbench specifies no vectors, then they
            # must all be specified in order in 'variables' in
            # the datasheet entry for the electrical parameters.
            for var in pvars:
                extra.append(var['condition'])
            if not pvars:
                print('Error:  No variables specified in testbench or datasheet.')
                rest = ''

        if len(extra) > 1:
            for varname in extra[1:]:
                if varname not in locvarresult:
                    locvarresult[varname] = []
                data_args.append(locvarresult[varname])

            rsize = read_ascii_datafile(extra[0], *data_args)
            # print('Read data file, rsize = ' + str(rsize))

            # All values in extra[1:] should be param['variables'].  If not, add
            # an entry and flag a warning because information may be incomplete.

            for varname in extra[1:]:
                try:
                    var = next(item for item in pvars if item['condition'] == varname)
                except StopIteration:
                    print('Variable ' + varname + ' not specified;  ', end='')
                    print('information may be incomplete.')
                    var = {}
                    var['condition'] = varname
                    pvars.append(var)                                    

            # By default, the 2nd result is the result
            if len(extra) > 2:
                varname = extra[2]
                varrec = next(item for item in pvars if item['condition'] == varname)
                varrec['result'] = True
                print('Setting condition ' + varname + ' as the result vector.')

            # "measure" records are applied to individual simulation outputs,
            # usually to reduce a time-based vector to a single value by
            # measuring a steady-state value, peak-peak, frequency, etc.

            if 'measure' in param:
                # Diagnostic
                # print('Applying measurements.')

                for measure in param['measure']:
                    rsize = apply_measure(locvarresult, measure, pvars)
                    # Diagnostic
                    # print("after measure, rsize = " + str(rsize))
                    # print("locvarresult = " + str(locvarresult))

                # Now recast locvarresult back into loccondresult.
                for varname in locvarresult:
                    varrec = next(item for item in pvars if item['condition'] == varname)
                    if 'result' in varrec:
                        # print('Result for ' + varname + ' = ' + str(locvarresult[varname]))
                        locparamresult = locvarresult[varname]
                        paramname = varname
                    else:
                        # print('Condition ' + varname + ' = ' + str(locvarresult[varname]))
                        loccondresult[varname] = locvarresult[varname]
                    # Diagnostic
                    # print("Variable " + varname + " length = " + str(len(locvarresult[varname])))

            else:
                # For plots, there is not necessarily any measurements.  Just
                # copy values into locparamresult and loccondresult.
                if len(locvarresult) == 0:
                    print('Warning: No result data for plot!')
                for varname in locvarresult:
                    varrec = next(item for item in pvars if item['condition'] == varname)
                    if 'result' in varrec:
                        # print('Result for ' + varname + ' = ' + str(locvarresult[varname]))
                        locparamresult = locvarresult[varname]
                        rsize = len(locparamresult)
                        paramname = varname
                    else:
                        # print('Condition ' + varname + ' = ' + str(locvarresult[varname]))
                        loccondresult[varname] = locvarresult[varname]
                rest = ''
    else:
        rsize = 0

    # Simple outputs are followed by a single value
    outrex = re.compile("[ \t]*\"?([^ \t\"]+)\"?(.*)$", re.IGNORECASE)
    # conditions always follow as key=value pairs
    dictrex = re.compile("[ \t]*([^ \t=]+)=([^ \t=]+)(.*)$", re.IGNORECASE)
    # conditions specified as min:step:max match a result vector.
    steprex = re.compile("[ \t]*([^:]+):([^:]+):([^:]+)$", re.IGNORECASE)
    # specification of units as a binary, hex, etc., string in verilog format
    binrex = re.compile(r'([0-9]*)\'([bodh])', re.IGNORECASE)


                    # To-do:  Handle raw files in similar manner to ASCII files.
                      
                    while rest:
                        # This code depends on values coming first, followed by conditions.
                        matchtext = dictrex.match(rest)
                        if matchtext:
                            # Diagnostic!
                            condname = matchtext.group(1)
                            # Append to the condition list
                            if condname not in loccondresult:
                                loccondresult[condname] = []

                            # Find the condition name in the condition list, so values can
                            # be converted back to the expected units.
                            try:
                                condrec = next(item for item in param['conditions'] if item['condition'] == condname)
                            except StopIteration:
                                condunit = ''
                            else:
                                condunit = condrec['unit']

                            rest = matchtext.group(3)
                            matchstep = steprex.match(matchtext.group(2))
                            if matchstep:
                                # condition is in form min:step:max, and the
                                # number of values must match rsize.
                                cmin = float(matchstep.group(1))
                                cstep = float(matchstep.group(2))
                                cmax = float(matchstep.group(3))
                                cnum = int(round((cmax + cstep - cmin) / cstep))
                                if cnum != rsize:
                                    print("Warning: Number of conditions (" + str(cnum) + ") is not")
                                    print("equal to the number of results (" + str(rsize) + ")")
                                    # Back-calculate the correct step size.  Usually this
                                    # means that the testbench did not add margin to the
                                    # DC or AC stop condition, and the steps fell 1 short of
                                    # the max.
                                    if rsize > 1:
                                        cstep = (float(cmax) - float(cmin)) / float(rsize - 1)

                                condvec = []
                                for r in range(rsize):
                                    condvec.append(cmin)
                                    cmin += cstep

                                cresult = spice_unit_unconvert([condunit, condvec])
                                condval = loccondresult[condname]
                                for cr in cresult:
                                    condval.append(str(cr))

                            else:
                                # If there is a vector of results but only one condition, copy the
                                # condition for each result.  Note that value may not be numeric.

                                # (To do:  Apply 'measure' records here)
                                condval = loccondresult[condname]
                                try:
                                    test = float(matchtext.group(2))
                                except ValueError:
                                    cval = matchtext.group(2)
                                else:
                                    cval = str(spice_unit_unconvert([condunit, test]))
                                for r in range(rsize):
                                    condval.append(cval)
                        else:
                            # Not a key=value pair, so must be a result value
                            matchtext = outrex.match(rest)
                            if matchtext:
                                rest = matchtext.group(2)
                                rsize += 1
                                # Result value units come directly from the param record.
                                if 'unit' in param:
                                    condunit = param['unit']
                                else:
                                    condunit = ''
                                if binrex.match(condunit):
                                    # Digital result with units 'b, 'h, etc. are kept as strings.
                                    locparamresult.append(matchtext.group(1))
                                else:
                                    locparamresult.append(float(matchtext.group(1)))
                            else:
                                print('Error:  Result line cannot be parsed.')
                                print('Bad part of line is: ' + rest)
                                print('Full line is: ' + line)
                                break

                    # Values passed in testbench['conditions'] are common to each result
                    # value.  From one line there are rsize values, so append each known
                    # condition to loccondresult rsize times.
                    for condrec in testbench['conditions']:
                        condname = condrec[0]
                        if condname in locvarresult:
                            print('Error:  name ' + condname + ' is both a variable and a condition!')
                            print('Ignoring the condition.')
                            continue
                        if condname not in loccondresult:
                            loccondresult[condname] = []
                        condval = loccondresult[condname]
                        if 'unit' in condrec:
                            condunit = condrec['unit']
                        else:
                            condunit = ''
                        for r in range(rsize):
                            if condname.split(':')[0] == 'DIGITAL' or condname == 'CORNER':
                                # Values that are known to be strings
                                condval.append(condrec[2])
                            elif binrex.match(condunit):
                                # Alternate digital specification using units 'b, 'h, etc.
                                condval.append(condrec[2])
                            elif condname == 'ITERATIONS':
                                # Values that are known to be integers
                                condval.append(int(float(condrec[2])))
                            else:
                                # All other values to be treated as floats unless
                                # they are non-numeric, in which case they are
                                # treated as strings and copied as-is.
                                try:
                                    condval.append(float(condrec[2]))
                                except ValueError:
                                    # Values that are not numeric just get copied
                                    condval.append(condrec[2])

            if len(locparamresult) > 0:
                # Fold local results into total results
                paramresult.extend(locparamresult)
                for key in loccondresult:
                    if not key in condresult:
                        condresult[key] = loccondresult[key]
                    else:
                        condresult[key].extend(loccondresult[key])

            else:
                # Catch simulation failures
                measurefailures += 1

            measurements += 1

        #------end of loop over testbenches

        # Evaluate concatentated results after all files for this electrical parameter
        # have been run through simulation.

        if paramresult:
            print(testbenchname + ':')

            # Diagnostic
            # print("paramresult length " + str(len(paramresult)))
            # for key in condresult:
            #     print("condresult length " + str(len(condresult[key])))

            # Write out all results into the JSON file.
            # Results are a list of lists;  the first list is a list of
            # methods, and the rest are sets of values corresponding to unique
            # conditions.  The first item in each lists is the result value
            # for that set of conditions.

            # Always keep results, even for remote CACE.

            outnames = [paramname]
            outunits = []

            if 'unit' in param:
                outunits.append(param['unit'])
            else:
                outunits.append('')
            for key in condresult:
                outnames.append(key)
                try:
                    condrec = next(item for item in param['conditions'] if item['condition'] == key) 
                except:
                    try:
                        condrec = next(item for item in param['variables'] if item['condition'] == key) 
                    except:
                        outunits.append('')
                    else:
                        if 'unit' in condrec:
                            outunits.append(condrec['unit'])
                            # 'variable' entries need to be unconverted
                            cconv = spice_unit_unconvert([condrec['unit'], condresult[key]])
                            condresult[key] = cconv
                        else:
                            outunits.append('')
                else:
                    if 'unit' in condrec:
                        outunits.append(condrec['unit'])
                    else:
                        outunits.append('')

            # Evaluate a script to transform the output, if there is a 'measure'
            # record in the electrical parameter.

            if 'measure' in param:

                evalrec = param['measure']
                try:
                    tool = evalrec['tool']
                except:
                    print("Error:  Evaluate record does not indicate a tool to run.")
                    break
                else:
                    if tool != 'octave' and tool != 'octave-cli' and tool != 'matlab':
                        print("Error:  CACE does not know how to use tool '" + tool + "'")
                        break

                # Use the command-line-interface version of octave.
                if tool == 'octave':
                    tool = 'octave-cli'

                try:
                    script = evalrec['filename']
                except:
                    print("Error:  Evaluate record does not indicate a script to run.")
                    break
                else:
                    if os.path.isdir(os.path.join(root_path, testbench_path)):
                        tb_path = os.path.join(root_path, testbench_path, script)
                        if not os.path.exists(tb_path):
                            if os.path.exists(tb_path + '.m'):
                                tb_path += '.m'
                            else:
                                print("Error:  No script '" + script + "' found in testbench path.")
                                break
                    else:
                        print("Error:  testbench directory not found in root path.")
                        break

                # General purpose tool-based measurement.  For complex operations of
                # any kind, dump the simulation results to a file "results.json" and
                # invoke the specified tool, which should read the results and
                # generate an output in the form of modified 'paramresult'.
                # e.g., input is an array of transient vectors, output is an FFT
                # analysis.  Input is a voltage, output is an INL value.  Note that
                # 'unit' is the unit produced by the script.  The script is supposed
                # to know what units it gets as input and what it produces as output.

            # pconv is paramresult scaled to the units used by param.
            if 'unit' in param:
                pconv = spice_unit_unconvert([param['unit'], paramresult])
            else:
                pconv = paramresult

            outresult = []
            outresult.append(outnames)
            outresult.append(outunits)

            for p in range(len(pconv)):
                outvalues = []
                outvalues.append(str(pconv[p]))
                for key, value in condresult.items():
                    try:
                        outvalues.append(str(value[p]))
                    except IndexError:
                        # Note:  This should not happen. . . 
                        print("Error:  number of values in result and conditions do not match!")
                        print("Result: " + str(len(pconv)))
                        print("Conditions: " + str(len(condresult)))
                        break

                outresult.append(outvalues)

            param['results'] = outresult

            if 'unit' in param:
                units = param['unit']
            else:
                units = ''

            # Catch simulation failures.
            if measurefailures > 0:
                print('Measurement failures:  ' + str(measurefailures))
                score = 'fail'

            if 'minimum' in param:
                minrec = param['minimum']
                if 'calc' in minrec:
                    calc = minrec['calc']
                else:
                    calc = 'min-above'
                minscore = calculate(minrec, pconv, condresult, calc, score, units, param)
                if score != 'fail':
                    score = minscore

            if 'maximum' in param:
                maxrec = param['maximum']
                if 'calc' in maxrec:
                    calc = maxrec['calc']
                else:
                    calc = 'max-below'
                maxscore = calculate(maxrec, pconv, condresult, calc, score, units, param)
                if score != 'fail':
                    score = maxscore

            if 'typical' in param:
                typrec = param['typical']
                if 'calc' in typrec:
                    calc = typrec['calc']
                else:
                    calc = 'avg-legacy'
                typscore = calculate(typrec, pconv, condresult, calc, score, units, param)
                if score != 'fail':
                    score = typscore

            if 'plot' in param:
                # If in plotmode then create a plot and save it to a file.
                plotrec = param['plot']
                if plotmode == True:
                    if 'variables' in param:
                        variables = param['variables']
                    else:
                        variables = []
                    result = cace_makeplot.makeplot(plotrec, param['results'], variables)
                    if result:
                        plotrec['status'] = 'done'
                        has_aux_files = True
                    else:
                        print('Failure:  No plot from file ' + filename + '\n')
                else:
                    plotrec['status'] = 'done'
        else:
            try:
                print('Failure:  No output from file ' + filename + '\n')
            except NameError:
                print('Failure:  No simulation file, so no output\n')
                continue

            # Handle errors where simulation generated no output.
            # This is the one case where 'typical' can be treated as pass-fail.
            # "score" will be set to "fail" for any of "minimum", "maximum",
            # and "typical" that exists in the electrical parameters record
            # and which specifies a target value.  "value" is set to "failure"
            # for display.
            score = 'fail'
            if 'typical' in param:
                typrec = param['typical']
                if 'target' in typrec:
                    typrec['score'] = 'fail'
                typrec['value'] = 'failure'
            if 'maximum' in param:
                maxrec = param['maximum']
                if 'target' in maxrec:
                    maxrec['score'] = 'fail'
                maxrec['value'] = 'failure'
            if 'minimum' in param:
                minrec = param['minimum']
                if 'target' in minrec:
                    minrec['score'] = 'fail'
                minrec['value'] = 'failure'

        # Pop the testbenches record, which has been replaced by the 'results' record.
        if keepmode == False:
            param.pop('testbenches')

    # Report the final score, and save it to the JSON data

    print('Completed ' + str(measurements) + ' of ' + str(totalmeasure) + ' measurements');
    print('Circuit pre-extraction simulation total score (lower is better) = '
			+ str(score))

    # Return 1 if measurements were successful, 0 if not
    return 0 if measurements == 0 else 1

#---------------------------------------------------------------------------
