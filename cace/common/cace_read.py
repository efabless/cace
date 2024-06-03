#!/usr/bin/env python3
#
# --------------------------------------------------------
# Circuit Automatic Characterization Engine (CACE) system
# cace_read.py ---
# Read a text file in CACE (ASCII) format 4.0
#
# --------------------------------------------------------
# Written by Tim Edwards
# Efabless Corporation
# November 21, 2023
# Version 4.0
# --------------------------------------------------------

import io
import re
import os
import sys
import json
import yaml

# Replace special character specifications with unicode characters


def specchar_sub(string):
    ucode_list = [
        '\u00b5',
        '\u00b0',
        '\u03c3',
        '\u03a9',
        '\u00b2',
        '\u221a',
        '\u03c1',
    ]
    text_list = [
        '{micro}',
        '{degrees}',
        '{sigma}',
        '{ohms}',
        '{squared}',
        '{sqrt}',
        '{rho}',
    ]

    if '{' not in string:
        return string

    idx = 0
    for item in text_list:
        if item in string:
            string = string.replace(item, ucode_list[idx])
        idx = idx + 1

    return string


# -----------------------------------------------------------------
# Read a CACE format file
# -----------------------------------------------------------------


def cace_read(filename, debug=False):
    if not os.path.isfile(filename):
        print('Error:  No such file ' + filename)
        return {}

    with open(filename, 'r') as ifile:
        clines = ifile.read()

    # These keys correspond to lists of dictionaries.  All other keys
    # must have a single value which is a string or a dictionary.
    listkeys = [
        'conditions',
        'default_conditions',
        'dependencies',
        'variables',
        'pins',
        'measure',
        'electrical_parameters',
        'physical_parameters',
        'testbenches',
        'results',
    ]

    # These keys have text string values with optional whitespace to end-of-line
    stringkeys = [
        'description',
        'display',
        'designer',
        'company',
        'creation_date',
        'modification_date',
        'license',
        'note',
        'comment',
    ]

    # All other keys are either single words or lists

    # This is the main dataset
    curdict = {}

    # The top level dataset cannot be a list
    curlist = None

    # Track hierarchical dictionaries and lists
    stack = []

    # First replay any backslash-newlines with spaces
    clines = clines.replace('\\\n', ' ')

    # Replace any tabs with spaces
    clines = clines.replace('\t', ' ')

    # Define regular expressions for parsing
    # Simple key:value entries
    kvrex = re.compile('^[ \t]*([^: \t]+)[ \t]*:[ \t]+(.*)$')

    # Key:dictionary entries
    kdrex = re.compile('^[ \t]*([^ \t\{]+)[ \t]*\{[ \t]*(.*)$')

    # New list-of-dictionaries entry
    listrex = re.compile('^[ \t]*\+[ \t]*(.*)$')

    # End of dictionary
    endrex = re.compile('^[ \t]*\}[ \t]*$')

    # End of list
    lendrex = re.compile('^[ \t]*\][ \t]*$')

    # Now split into lines
    for line in clines.splitlines():
        # Ignore comment lines (lines beginning with "#")
        if line.strip().startswith('#'):
            continue
        # Ignore blank lines
        elif line.strip() == '':
            continue

        # Find simple key: value pairs
        kmatch = kvrex.match(line)
        if kmatch:
            key = kmatch.group(1)
            value = specchar_sub(kmatch.group(2)).strip()

            # Only keys listed in "stringkeys" have multi-word values with
            # whitespace.  All other values are either single words or lists.
            if key in stringkeys:
                curdict[key] = value
            else:
                valuelist = value.split()
                if len(valuelist) == 1:
                    curdict[key] = value
                else:
                    curdict[key] = valuelist

        else:
            # Find key: dictionary entries
            # Avoid treating special character substitutions like "{degrees}"
            # as dictionaries.
            testline = specchar_sub(line)
            kmatch = kdrex.match(testline)
            if kmatch:
                kmatch = kdrex.match(line)
                newdict = {}
                key = kmatch.group(1)

                # If this is a list type, then create a new list and
                # start a new dictionary as the first list entry.  If
                # not, then just start a new dictionary.

                if key in listkeys:
                    if debug:
                        print('Diagnostic:  Starting list of ' + key)
                    newlist = []
                    newlist.append(newdict)
                    curdict[key] = newlist
                else:
                    if debug:
                        print('Diagnostic:  Starting dictionary of ' + key)
                    newlist = None
                    curdict[key] = newdict

                # Push the current dictionary or list
                if curlist:
                    stack.append(curlist)
                else:
                    stack.append(curdict)

                curdict = newdict
                curlist = newlist

            else:
                # Check for end of dictionary or list
                ematch = endrex.match(line)
                if ematch:
                    # Pop the dictionary or list
                    curtest = stack.pop()
                    if isinstance(curtest, dict):
                        if debug:
                            print('Diagnostic:  Returning to dictionary')
                        curlist = None
                        curdict = curtest
                    else:
                        if debug:
                            print('Diagnostic:  Returning to list')
                        curlist = curtest
                        curdict = curlist[-1]

                else:
                    # Check for new list item.
                    lmatch = listrex.match(line)
                    if lmatch:
                        if curlist == None:
                            print(
                                'Error:  Attempt to create list in non-list record'
                                + ' in "'
                                + line
                                + '"'
                            )
                        else:
                            newdict = {}
                            curlist.append(newdict)
                            curdict = newdict

                    elif isinstance(curlist, list):
                        # curdict should not exist in this case, so remove it
                        if isinstance(curlist[0], dict):
                            curlist.pop(0)
                            curdict = None
                        # Append item line by line.
                        tokens = line.strip().split(' ')
                        if len(tokens) == 1:
                            curlist.append(line.strip())
                        else:
                            curlist.append(tokens)

                    else:
                        print('Error:  Undefined syntax in "' + line + '"')

    # Run a few basic syntax checks.
    # All parameters must have a name and all names must be
    # alphanumeric-plus-underscore

    namerex = re.compile(r'^[A-Za-z0-9_]+$')

    if 'electrical_parameters' in curdict:
        eparams = curdict['electrical_parameters']
        for eparam in eparams:
            if 'name' not in eparam:
                print('Error:  Unnamed electrical parameter in datasheet!')
            else:
                paramname = eparam['name']
                pmatch = namerex.match(paramname)
                if not pmatch:
                    print(
                        'Error:  Parameter '
                        + paramname
                        + ' has an illegal name syntax!'
                    )

    if 'physical_parameters' in curdict:
        pparams = curdict['physical_parameters']
        for pparam in pparams:
            if 'name' not in pparam:
                print('Error:  Unnamed physical parameter in datasheet!')
            else:
                paramname = pparam['name']
                pmatch = namerex.match(paramname)
                if not pmatch:
                    print(
                        'Error:  Parameter '
                        + paramname
                        + ' has an illegal name syntax!'
                    )

    # Set up runtime options in the dictionary before returning.

    if 'runtime_options' in curdict:
        runtime_options = curdict['runtime_options']
    else:
        runtime_options = {}
        curdict['runtime_options'] = runtime_options

    runtime_options['debug'] = debug
    runtime_options['filename'] = filename

    return curdict


def cace_read_yaml(filename, debug=False):
    if not os.path.isfile(filename):
        print('Error:  No such file ' + filename)
        return {}

    with open(filename, 'r') as ifile:
        datasheet = yaml.safe_load(ifile)

    # For compatibility convert dictionaries to arrays with
    # dictionaries containing the key inside "name"
    # TODO Remove this step and change the remaining code
    # in CACE to work with dictionaries

    # Copy header
    new_datasheet = {}
    new_datasheet['name'] = datasheet['name']
    new_datasheet['description'] = datasheet['description']
    new_datasheet['commit'] = datasheet['commit']
    new_datasheet['PDK'] = datasheet['PDK']
    new_datasheet['cace_format'] = datasheet['cace_format']
    new_datasheet['authorship'] = datasheet['authorship']
    new_datasheet['paths'] = datasheet['paths']
    new_datasheet['dependencies'] = datasheet['dependencies']

    # Convert pins
    new_datasheet['pins'] = []
    for key, value in datasheet['pins'].items():
        value['name'] = key
        new_datasheet['pins'].append(value)

    # Convert conditions in electrical_parameters
    for parameter in datasheet['electrical_parameters'].values():
        new_conditions = []
        for key, value in parameter['conditions'].items():
            value['name'] = key
            new_conditions.append(value)
        parameter['conditions'] = new_conditions

    # Convert variables in electrical_parameters
    for parameter in datasheet['electrical_parameters'].values():
        new_variables = []
        if 'variables' in parameter:
            for key, value in parameter['variables'].items():
                value['name'] = key
                new_variables.append(value)
            parameter['variables'] = new_variables

    # Convert simulate in electrical_parameters
    for parameter in datasheet['electrical_parameters'].values():
        for key, value in parameter['simulate'].items():
            value['tool'] = key

            if 'format' in value:
                new_format = []
                new_format.append(value.pop('format'))
                new_format.append(value.pop('suffix'))
                new_format += value.pop('variables')

                value['format'] = new_format

        parameter['simulate'] = value

    # Convert spec entries in electrical_parameters
    for parameter in datasheet['electrical_parameters'].values():

        if 'spec' in parameter:
            for limit in ['minimum', 'typical', 'maximum']:
                if limit in parameter['spec']:
                    if 'fail' in parameter['spec'][limit]:
                        new_limit = []
                        new_limit.append(parameter['spec'][limit]['value'])

                        if parameter['spec'][limit]['fail'] == True:
                            new_limit.append('fail')
                            if 'calculation' in parameter['spec'][limit]:
                                new_limit.append(
                                    parameter['spec'][limit]['calculation']
                                )

                        parameter['spec'][limit] = new_limit
                    else:
                        parameter['spec'][limit] = parameter['spec'][limit][
                            'value'
                        ]

    # Convert evaluate in physical_parameters
    for parameter in datasheet['physical_parameters'].values():

        if isinstance(parameter['evaluate'], str):
            value = {'tool': parameter['evaluate']}
        else:
            for key, value in parameter['evaluate'].items():
                value['tool'] = key

                if 'script' in value:
                    value['tool'] = [value['tool'], value.pop('script')]

        parameter['evaluate'] = value

    # Convert spec entries in physical_parameters
    for parameter in datasheet['physical_parameters'].values():

        if 'spec' in parameter:
            for limit in ['minimum', 'typical', 'maximum']:
                if limit in parameter['spec']:
                    if 'fail' in parameter['spec'][limit]:
                        new_limit = []
                        new_limit.append(parameter['spec'][limit]['value'])

                        if parameter['spec'][limit]['fail'] == True:
                            new_limit.append('fail')
                            if 'calculation' in parameter['spec'][limit]:
                                new_limit.append(
                                    parameter['spec'][limit]['calculation']
                                )

                        parameter['spec'][limit] = new_limit
                    else:
                        parameter['spec'][limit] = parameter['spec'][limit][
                            'value'
                        ]

    # Convert default_conditions
    new_datasheet['default_conditions'] = []
    for key, value in datasheet['default_conditions'].items():
        value['name'] = key
        new_datasheet['default_conditions'].append(value)

    # Convert electrical_parameters
    new_datasheet['electrical_parameters'] = []
    for key, value in datasheet['electrical_parameters'].items():
        value['name'] = key
        new_datasheet['electrical_parameters'].append(value)

    # Convert physical_parameters
    new_datasheet['physical_parameters'] = []
    for key, value in datasheet['physical_parameters'].items():
        value['name'] = key
        new_datasheet['physical_parameters'].append(value)

    # Convert dependencies TODO
    if not new_datasheet['dependencies']:
        new_datasheet['dependencies'] = []

    # TODO Remove runtime options from datasheet
    # Set up runtime options in the dictionary before returning.

    if 'runtime_options' in datasheet:
        runtime_options = datasheet['runtime_options']
    else:
        runtime_options = {}
    new_datasheet['runtime_options'] = runtime_options

    runtime_options['debug'] = debug
    runtime_options['filename'] = filename

    return new_datasheet
