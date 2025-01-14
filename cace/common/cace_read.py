# Copyright 2024 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import re
import os
import sys
import json
import yaml

from ..logging import (
    dbg,
    verbose,
    info,
    subproc,
    rule,
    success,
    warn,
    err,
)


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
    kvrex = re.compile(r'^[ \t]*([^: \t]+)[ \t]*:[ \t]+(.*)$')

    # Key:dictionary entries
    kdrex = re.compile(r'^[ \t]*([^ \t\{]+)[ \t]*\{[ \t]*(.*)$')

    # New list-of-dictionaries entry
    listrex = re.compile(r'^[ \t]*\+[ \t]*(.*)$')

    # End of dictionary
    endrex = re.compile(r'^[ \t]*\}[ \t]*$')

    # End of list
    lendrex = re.compile(r'^[ \t]*\][ \t]*$')

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

    # Conert to new datasheet format
    datasheet = {}

    # Copy metadata
    if 'name' in curdict:
        datasheet['name'] = curdict['name']
    else:
        datasheet['name'] = ''

    if 'description' in curdict:
        datasheet['description'] = curdict['description']
    else:
        datasheet['description'] = ''

    if 'commit' in curdict:
        datasheet['commit'] = curdict['commit']
    else:
        datasheet['commit'] = ''

    if 'PDK' in curdict:
        datasheet['PDK'] = curdict['PDK']
    else:
        datasheet['PDK'] = ''

    datasheet['cace_format'] = 5.0

    # Copy authorship
    if 'authorship' in curdict:
        datasheet['authorship'] = curdict['authorship']
    else:
        datasheet['authorship'] = {}

    # Copy paths
    if 'paths' in curdict:
        datasheet['paths'] = curdict['paths']
    else:
        datasheet['paths'] = {}

    # Copy pins
    datasheet['pins'] = {}
    if 'pins' in curdict:

        for pin in curdict['pins']:
            datasheet['pins'][pin['name']] = pin

            datasheet['pins'][pin['name']].pop('name')

    # Copy default_conditions
    datasheet['default_conditions'] = {}
    if 'default_conditions' in curdict:
        for cond in curdict['default_conditions']:
            datasheet['default_conditions'][cond['name']] = cond

            datasheet['default_conditions'][cond['name']].pop('name')

    datasheet['parameters'] = {}

    # Copy parameters
    if 'electrical_parameters' in curdict:
        for eparam in curdict['electrical_parameters']:
            datasheet['parameters'][eparam['name']] = eparam

            if 'conditions' in eparam:
                new_conditions = {}
                for cond in eparam['conditions']:
                    new_conditions[cond['name']] = cond
                    new_conditions[cond['name']].pop('name')

                eparam['conditions'] = new_conditions

            if 'spec' in datasheet['parameters'][eparam['name']]:
                for limit in ['minimum', 'typical', 'maximum']:
                    if (
                        limit
                        in datasheet['parameters'][eparam['name']]['spec']
                    ):
                        spec = datasheet['parameters'][eparam['name']][
                            'spec'
                        ].pop(limit)
                        datasheet['parameters'][eparam['name']]['spec'][
                            limit
                        ] = {}

                        if isinstance(spec, str):
                            datasheet['parameters'][eparam['name']]['spec'][
                                limit
                            ]['value'] = spec

                        else:
                            datasheet['parameters'][eparam['name']]['spec'][
                                limit
                            ]['value'] = spec[0]

                            if len(spec) > 1:
                                if spec[1] == 'fail':
                                    datasheet['parameters'][eparam['name']][
                                        'spec'
                                    ][limit]['fail'] = True
                                else:
                                    datasheet['parameters'][eparam['name']][
                                        'spec'
                                    ][limit]['fail'] = False

                            if len(spec) > 2:
                                print(spec[2])
                                calculation, _limit = spec[2].split('-')
                                datasheet['parameters'][eparam['name']][
                                    'spec'
                                ][limit]['calculation'] = calculation
                                datasheet['parameters'][eparam['name']][
                                    'spec'
                                ][limit]['limit'] = _limit

            if 'simulate' in datasheet['parameters'][eparam['name']]:
                if (
                    'format'
                    in datasheet['parameters'][eparam['name']]['simulate']
                ):
                    format = datasheet['parameters'][eparam['name']][
                        'simulate'
                    ].pop('format')
                    datasheet['parameters'][eparam['name']]['simulate'][
                        'format'
                    ] = format[0]
                    datasheet['parameters'][eparam['name']]['simulate'][
                        'suffix'
                    ] = format[1]
                    datasheet['parameters'][eparam['name']]['simulate'][
                        'variables'
                    ] = format[2:]

                toolname = datasheet['parameters'][eparam['name']][
                    'simulate'
                ].pop('tool')

                if (
                    'template'
                    in datasheet['parameters'][eparam['name']]['simulate']
                ):
                    # Adjust the template from .spice to .sch
                    if toolname == 'ngspice':
                        datasheet['parameters'][eparam['name']]['simulate'][
                            'template'
                        ] = datasheet['parameters'][eparam['name']][
                            'simulate'
                        ][
                            'template'
                        ].replace(
                            '.spice', '.sch'
                        )

                datasheet['parameters'][eparam['name']]['tool'] = {
                    toolname: datasheet['parameters'][eparam['name']].pop(
                        'simulate'
                    )
                }

            datasheet['parameters'][eparam['name']].pop('name')

    if 'physical_parameters' in curdict:
        for pparam in curdict['physical_parameters']:
            datasheet['parameters'][pparam['name']] = pparam

            if 'conditions' in pparam:
                new_conditions = {}
                for cond in pparam['conditions']:
                    new_conditions[cond['name']] = cond
                    new_conditions[cond['name']].pop('name')

                pparam['conditions'] = new_conditions

            if 'spec' in datasheet['parameters'][pparam['name']]:
                for limit in ['minimum', 'typical', 'maximum']:
                    if (
                        limit
                        in datasheet['parameters'][pparam['name']]['spec']
                    ):
                        spec = datasheet['parameters'][pparam['name']][
                            'spec'
                        ].pop(limit)
                        datasheet['parameters'][pparam['name']]['spec'][
                            limit
                        ] = {}

                        if isinstance(spec, str):
                            datasheet['parameters'][pparam['name']]['spec'][
                                limit
                            ]['value'] = spec

                        else:
                            datasheet['parameters'][pparam['name']]['spec'][
                                limit
                            ]['value'] = spec[0]

                            if len(spec) > 1:
                                if spec[1] == 'fail':
                                    datasheet['parameters'][pparam['name']][
                                        'spec'
                                    ][limit]['fail'] = True
                                else:
                                    datasheet['parameters'][pparam['name']][
                                        'spec'
                                    ][limit]['fail'] = False

                            if len(spec) > 2:
                                print(spec[2])
                                calculation, _limit = spec[2].split('-')
                                datasheet['parameters'][pparam['name']][
                                    'spec'
                                ][limit]['calculation'] = calculation
                                datasheet['parameters'][pparam['name']][
                                    'spec'
                                ][limit]['limit'] = _limit

            if 'evaluate' in datasheet['parameters'][pparam['name']]:
                toolname = datasheet['parameters'][pparam['name']][
                    'evaluate'
                ].pop('tool')
                datasheet['parameters'][pparam['name']]['tool'] = {
                    toolname: datasheet['parameters'][pparam['name']].pop(
                        'evaluate'
                    )
                }

            datasheet['parameters'][pparam['name']].pop('name')

    return validate_datasheet(datasheet)


def cace_read_yaml(filename, debug=False):
    if not os.path.isfile(filename):
        err(f'No such file {filename}')
        return {}

    with open(filename, 'r') as ifile:
        datasheet = yaml.safe_load(ifile)

    return validate_datasheet(datasheet)


CACE_DATASHEET_VERSION = 5.2


def validate_datasheet(datasheet):

    # Check for missing field
    if not 'name' in datasheet:
        err('Field "name" is missing in datasheet.')
        return None
    if not 'description' in datasheet:
        err('Field "description" is missing in datasheet.')
        return None
    # if not 'commit' in datasheet:
    #    err('Field "commit" is missing in datasheet.')
    #    return None
    if not 'PDK' in datasheet:
        err('Field "PDK" is missing in datasheet.')
        return None

    # Check if 'cace_format' is a key of the datasheet
    if not 'cace_format' in datasheet:
        warn(
            f'No cace_format given, trying to read as {CACE_DATASHEET_VERSION}.'
        )
        datasheet['cace_format'] = CACE_DATASHEET_VERSION
    else:
        if datasheet['cace_format'] != CACE_DATASHEET_VERSION:
            warn(
                f'Unsupported format version. Please update to version {CACE_DATASHEET_VERSION}.'
            )
            warn(
                'More information in the reference manual: [link=https://cace.readthedocs.io/en/latest/reference_manual/index.html]https://cace.readthedocs.io/en/latest/reference_manual/index.html[/link].'
            )

        if datasheet['cace_format'] <= 5.0:
            warn(
                'Please convert CACE placeholders from `{condition}` and `[expression]` to `CACE{condition}` and `CACE[expression]`.'
            )

    # Check if 'authorship' is a key of the datasheet
    if not 'authorship' in datasheet:
        datasheet['authorship'] = {}
        warn('Could not find authorship entry.')

    if not 'designer' in datasheet['authorship']:
        datasheet['authorship']['designer'] = None
    if not 'company' in datasheet['authorship']:
        datasheet['authorship']['company'] = None
    if not 'creation_date' in datasheet['authorship']:
        datasheet['authorship']['creation_date'] = None
    if not 'modification_date' in datasheet['authorship']:
        datasheet['authorship']['modification_date'] = None
    if not 'license' in datasheet['authorship']:
        datasheet['authorship']['license'] = None

    # Check if 'paths' is a key of the datasheet
    if not 'paths' in datasheet:
        datasheet['paths'] = {}
        err('Could not find any paths.')
        return None

    # Check if 'pins' is a key of the datasheet
    if not 'pins' in datasheet:
        datasheet['pins'] = {}
        warn('Could not find any pins.')

    # Check if 'default_conditions' is a key of the datasheet
    if not 'default_conditions' in datasheet:
        datasheet['default_conditions'] = {}
        warn('Could not find any default conditions.')

    # Check if 'parameters' is a key of the datasheet
    if not 'parameters' in datasheet:
        datasheet['parameters'] = {}
        warn('Could not find any parameters.')

    # For each parameter, set the name to their key
    for key, param in datasheet['parameters'].items():
        param['name'] = key

    # For each parameter, set their display name
    # to their name if not specified
    for param in datasheet['parameters'].values():
        if not 'display' in param:
            param['display'] = param['name']

    # For each parameter, make sure spec is defined
    for key, param in datasheet['parameters'].items():
        if not 'spec' in param:
            param['spec'] = {}

    # For each parameter, make sure conditions is defined
    for key, param in datasheet['parameters'].items():
        if not 'conditions' in param:
            param['conditions'] = {}

    # Make sure there is only one tool listed
    for param in datasheet['parameters'].values():
        if 'tool' in param:
            if isinstance(param['tool'], str):
                pass
            elif len(list(param['tool'].keys())) > 1:
                warn(f'More than one tool listed in {param["name"]}.')
        else:
            err(f'No tool listed in {param["name"]}.')
            return None

    return datasheet
