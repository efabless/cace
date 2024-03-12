#!/usr/bin/env python3
#
# --------------------------------------------------------
# CACE backwards-compatibility handler
#
# This script takes a dictionary from an older JSON-
# format CACE file (pre-2023) and converts various
# entries to make it compatible with CACE 4.0 format
# (November 2023).
#
# Input:  datasheet dictionary in any CACE format
# Output: datasheet dictionary in CACE 4.0 format
#
# --------------------------------------------------------
# Written by Tim Edwards
# Efabless corporation
# November 22, 2023
# --------------------------------------------------------

import io
import re
import os
import sys
import json

from .cace_write import *

from .cace_regenerate import get_pdk_root

# ---------------------------------------------------------------
# Modify CACE datasheet dictionary for version 4.0 compatibility
# ---------------------------------------------------------------


def cace_compat(datasheet, debug=False):

    # Backwards-compatibility stuff.
    # Make changes from older JSON format to newer format

    if 'ip-name' in datasheet and 'name' not in datasheet:
        datasheet['name'] = datasheet['ip-name']
        datasheet.pop('ip-name')
    if 'node' in datasheet and 'PDK' not in datasheet:
        datasheet['PDK'] = datasheet['node']
        datasheet.pop('node')
    if 'electrical-params' in datasheet:
        datasheet['electrical_parameters'] = datasheet['electrical-params']
        datasheet.pop('electrical-params')
    if 'physical-params' in datasheet:
        datasheet['physical_parameters'] = datasheet['physical-params']
        datasheet.pop('physical-params')
    if 'global-conditions' in datasheet:
        datasheet['default_conditions'] = datasheet['global-conditions']
        datasheet.pop('global-conditions')

    if 'paths' not in datasheet:
        pathdict = {}
        pathdict['documentation'] = 'doc'
        pathdict['schematic'] = 'xschem'
        pathdict['layout'] = 'gds'
        pathdict['netlist'] = 'netlist'
        pathdict['testbench'] = 'testbench'
        pathdict['simulation'] = 'ngspice'
        pathdict['plots'] = 'plots'
        pathdict['logs'] = os.path.join('ngspice', 'log')
        datasheet['paths'] = pathdict

    if 'foundry' not in datasheet:
        # Pick up foundry name using PDK_ROOT
        pdk_root = get_pdk_root()
        if pdk_root:
            pdk_config_file = (
                pdk_root + '/' + datasheet['PDK'] + '/.config/nodeinfo.json'
            )
            if os.path.isfile(pdk_config_file):
                with open(pdk_config_file, 'r') as ifile:
                    nodeinfo = json.load(ifile)
                    if 'foundry-name' in nodeinfo:
                        datasheet['foundry'] = nodeinfo['foundry-name']
                    elif 'foundry' in nodeinfo:
                        datasheet['foundry'] = nodeinfo['foundry']
            else:
                datasheet['foundry'] = 'Unknown'

        else:
            datasheet['foundry'] = 'Unknown'

    # More backwards compatibility:  Change all electrical parameter
    # "method" records to "measure", and move the min/max/typ records
    # into a dictionary called "spec", and various other stuff.

    namesused = []
    pindex = 1
    for eparam in datasheet['electrical_parameters']:
        if 'name' not in eparam:
            if 'method' in eparam:
                if eparam['method'] in namesused:
                    eparam['name'] = eparam['method'] + '_' + str(pindex)
                else:
                    eparam['name'] = eparam['method']
            else:
                eparam['name'] = 'parameter_' + str(pindex)
        namesused.append(eparam['name'])
        if 'method' in eparam:
            measuredict = {}
            eparam['measure'] = measuredict
            measuredict['tool'] = 'ngspice'
            measuredict['template'] = eparam['method']
            eparam.pop('method')
        if 'spec' not in eparam:
            specdict = {}
            if 'typ' in eparam:
                if isinstance(eparam['typ'], dict):
                    typdict = eparam['typ']
                    if 'target' in typdict:
                        typtarget = typdict['target']
                    else:
                        typtarget = None
                    if 'penalty' in typdict:
                        typpenalty = typdict['penalty']
                    else:
                        typpenalty = None
                    if typtarget and typpenalty:
                        specdict['typical'] = [typtarget, typpenalty]
                    elif typtarget:
                        specdict['typical'] = typtarget
                else:
                    specdict['typical'] = eparam['typ']
                eparam.pop('typ')
            if 'min' in eparam:
                if isinstance(eparam['min'], dict):
                    mindict = eparam['min']
                    if 'target' in mindict:
                        mintarget = mindict['target']
                    else:
                        mintarget = None
                    if 'penalty' in mindict:
                        minpenalty = mindict['penalty']
                    else:
                        minpenalty = None
                    if mintarget and minpenalty:
                        specdict['minimum'] = [mintarget, minpenalty]
                    elif mintarget:
                        specdict['minimum'] = mintarget
                else:
                    specdict['minimum'] = eparam['min']
                eparam.pop('min')
            if 'max' in eparam:
                if isinstance(eparam['max'], dict):
                    maxdict = eparam['max']
                    if 'target' in maxdict:
                        maxtarget = maxdict['target']
                    else:
                        maxtarget = None
                    if 'penalty' in maxdict:
                        maxpenalty = maxdict['penalty']
                    else:
                        maxpenalty = None
                    if maxtarget and maxpenalty:
                        specdict['maximum'] = [maxtarget, maxpenalty]
                    elif maxtarget:
                        specdict['maximum'] = maxtarget
                else:
                    specdict['maximum'] = eparam['max']
                eparam.pop('max')
            if specdict != {}:
                eparam['spec'] = specdict

        if 'conditions' in eparam:
            for condition in eparam['conditions']:
                if 'condition' in condition:
                    condition['name'] = condition['condition']
                    condition.pop('condition')
                if 'typ' in condition:
                    if isinstance(condition['typ'], dict):
                        typdict = condition['typ']
                        if 'target' in typdict:
                            typtarget = typdict['target']
                        else:
                            typtarget = None
                        if 'penalty' in typdict:
                            typpenalty = typdict['penalty']
                        else:
                            typpenalty = None
                        if typtarget and typpenalty:
                            condition['typical'] = [typtarget, typpenalty]
                        elif typtarget:
                            condition['typical'] = typtarget
                    else:
                        condition['typical'] = condition['typ']
                    condition.pop('typ')
                if 'min' in condition:
                    if isinstance(condition['min'], dict):
                        mindict = condition['min']
                        if 'target' in mindict:
                            mintarget = mindict['target']
                        else:
                            mintarget = None
                        if 'penalty' in mindict:
                            minpenalty = mindict['penalty']
                        else:
                            minpenalty = None
                        if mintarget and minpenalty:
                            condition['minimum'] = [mintarget, minpenalty]
                        elif mintarget:
                            condition['minimum'] = mintarget
                    else:
                        condition['minimum'] = condition['min']
                    condition.pop('min')
                if 'max' in condition:
                    if isinstance(condition['max'], dict):
                        maxdict = condition['max']
                        if 'target' in maxdict:
                            maxtarget = maxdict['target']
                        else:
                            maxtarget = None
                        if 'penalty' in maxdict:
                            maxpenalty = maxdict['penalty']
                        else:
                            maxpenalty = None
                        if maxtarget and maxpenalty:
                            condition['maximum'] = [maxtarget, maxpenalty]
                        elif maxtarget:
                            condition['maximum'] = maxtarget
                    else:
                        condition['maximum'] = condition['max']
                    condition.pop('max')
                if 'enum' in condition:
                    condition['enumerate'] = condition['enum']
                    condition.pop('enum')
        pindex = pindex + 1

        if 'variables' in eparam:
            vnamesused = []
            vindex = 1
            for variable in eparam['variables']:
                if 'result' in variable:
                    variable['name'] = 'result'
                    variable.pop('result')
                elif 'name' not in variable:
                    vname = '_'.join(variable['display'].lower().split())
                    if vname not in vnamesused:
                        variable['name'] = vname
                    else:
                        variable['name'] = vname + str(vindex)
                vnamesused.append(variable['name'])
                vindex = vindex + 1

        if 'plot' in eparam:
            plotdict = eparam['plot']
            for key in list(plotdict.keys()):
                if key == 'xlabel':
                    plotdict.pop('xlabel')
                elif key == 'ylabel':
                    plotdict.pop('ylabel')

    for pin in datasheet['pins']:
        if 'dir' in pin:
            pin['direction'] = pin['dir']
            pin.pop('dir')

    for condition in datasheet['default_conditions']:
        if 'condition' in condition:
            condition['name'] = condition['condition']
            condition.pop('condition')
        if 'typ' in condition:
            condition['typical'] = condition['typ']
            condition.pop('typ')
        if 'min' in condition:
            condition['minimum'] = condition['min']
            condition.pop('min')
        if 'max' in condition:
            condition['maximum'] = condition['max']
            condition.pop('max')
        if 'enum' in condition:
            condition['enumerate'] = condition['enum']
            condition.pop('enum')

    return datasheet


# Print usage statement


def usage():
    print('Usage:')
    print('')
    print('cace_compat.py <filename>')
    print('  Where <filename> is a pre-format 4.0 CACE JSON file.')
    print('')
    print('When run from the top level, this program parses the CACE')
    print('format file and outputs a CACE format 4.0 file.')


# ------------------------------------------------------
# If called from the command line. . .
# ------------------------------------------------------

if __name__ == '__main__':
    options = []
    arguments = []
    for item in sys.argv[1:]:
        if item.find('-', 0) == 0:
            options.append(item)
        else:
            arguments.append(item)

    debug = False
    for item in options:
        if item == '-debug':
            debug = True

    result = 0
    if len(arguments) == 1 and len(options) == 0:
        filename = arguments[0]
        if not os.path.isfile(filename):
            print('Error:  No such file ' + filename)
            sys.exit(1)

        with open(filename, 'r') as ifile:
            try:
                dataset = json.load(ifile)
            except json.decoder.JSONDecodeError as e:
                print(
                    'Error:  Parse error reading JSON file ' + datasheet + ':'
                )
                print(str(e))
                sys.exit(1)

        new_dataset = cace_compat(dataset, debug)
        if debug:
            print('Diagnostic---dataset is:')
            print(str(new_dataset))
        else:
            result = cace_write(new_dataset, debug)

    else:
        usage()
        sys.exit(1)

    sys.exit(result)
