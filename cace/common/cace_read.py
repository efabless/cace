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

from .cace_compat import *

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


# Print usage statement


def usage():
    print('Usage:')
    print('')
    print('cace_read.py <filename>')
    print('  Where <filename> is a format 4.0 ASCII CACE file.')
    print('')
    print('When run from the top level, this program parses the CACE')
    print('file and reports any syntax errors.  Otherwise it is meant')
    print('to be called internally by the CACE system to read a file')
    print('and return a dictionary of the contents.')


# Top level call to cace_read.py
# If called from the command line

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

        # If the file is a JSON file, read it with json.load
        if os.path.splitext(filename)[1] == '.json':
            if not os.path.isfile(filename):
                print('Error:  No such file ' + filename)
                result = 1
            else:
                with open(filename, 'r') as ifile:
                    dataset = json.load(ifile)
                    if dataset and 'data-sheet' in dataset:
                        dataset = dataset['data-sheet']
                        # Attempt to upgrade this to format 4.0
                        dataset = cace_compat(dataset, debug)
        else:
            dataset = cace_read(filename, debug)

        if dataset == {}:
            result = 1
        else:
            if debug:
                print('Diagnostic---dataset is:')
                print(str(dataset))
            else:
                print('CACE file has no syntax issues.')

    else:
        usage()
        sys.exit(1)

    sys.exit(result)
