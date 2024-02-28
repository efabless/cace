#!/usr/bin/env python3
#
#--------------------------------------------------------
# CACE file writer
#
# This script takes a dictionary from CACE and writes
# a CACE 4.0 format text file.
#
# Input:  datasheet dictionary
# Output: file in CACE 4.0 format
#
#--------------------------------------------------------
# Written by Tim Edwards
# Efabless corporation
# November 22, 2023
#--------------------------------------------------------

import io
import re
import os
import sys
import json
import datetime

import cace_compat

#---------------------------------------------------------------
# cace_summarize_result
#
# Print a summary report of a single "results" block from a
# datasheet.
#---------------------------------------------------------------

def cace_summarize_result(param, result):
    spec = param['spec']
    unit = param['unit']

    keys = ['minimum', 'typical', 'maximum']

    print('   Source type: ' + result['name'])
    for key in keys:
        if key in spec and key in result:
            speclist = spec[key]
            if isinstance(speclist, str):
                specvalue = speclist
            else:
                specvalue = speclist[0]
            resultlist = result[key]

            # Use this complicated replacement for print()
            # to keep any unicode characters in the units
            # from mis-printing.

            # Output format is, e.g., :
            #   minimum(mA):  spec = any  measured = 12.7534 (pass)

            outline = '      ' + key + ' (' + unit + '):'
            outline += '  spec = ' + specvalue + '  measured = '
            outline += resultlist[0] + ' (' + resultlist[1] + ')\n'

            sys.stdout.buffer.write(outline.encode('latin1'))

    print('')

#---------------------------------------------------------------
# cace_summary
#
# Print a summary report of results from a datasheet
#
# "datasheet" is a CACE characterization dataset
# "paramname" is the name of a single parameter to summarize,
#	or if it is None, then all parameters should be output.
#---------------------------------------------------------------

def cace_summary(datasheet, paramname):

    if 'electrical_parameters' in datasheet:
        for eparam in datasheet['electrical_parameters']:
            if not paramname or paramname == eparam['name']:
                print('Electrical parameter ' + eparam['name'])
                if 'description' in eparam:
                    print('   ' + eparam['description'])
                if 'display' in eparam:
                    print('   ' + eparam['display'])
                if 'spec' not in eparam:
                    print('   (Parameter does not have a spec)')
                elif 'results' not in eparam:
                    print('   (No results to report)')
                else:
                    results = eparam['results']
                    if isinstance(results, list):
                        for result in eparam['results']:
                            cace_summarize_result(eparam, result)
                    else:
                        cace_summarize_result(eparam, results)

    if 'physical_parameters' in datasheet:
        for pparam in datasheet['physical_parameters']:
            if not paramname or paramname == pparam['name']:
                print('Physical parameter ' + pparam['name'])
                if 'description' in pparam:
                    print('   ' + pparam['description'])
                if 'display' in eparam:
                    print('   ' + eparam['display'])
                if 'spec' not in pparam:
                    print('   (Parameter does not have a spec)')
                elif 'results' not in pparam:
                    print('   (No results to report)')
                else:
                    results = pparam['results']
                    if isinstance(results, list):
                        for result in pparam['results']:
                            cace_summarize_result(pparam, result)
                    else:
                        cace_summarize_result(pparam, results)

#---------------------------------------------------------------
# Convert from unicode to text format
#---------------------------------------------------------------

def uchar_sub(string):
    ucode_list = ['\u00b5', '\u00b0', '\u03c3', '\u03a9',
		'\u00b2', '\u221a', '\u03c1']
    text_list = ['{micro}', '{degrees}', '{sigma}', '{ohms}',
		'{squared}', '{sqrt}', '{rho}']

    idx = 0
    for item in ucode_list:
        if item in string:
            string = string.replace(item, text_list[idx])
        idx = idx + 1

    return string

#---------------------------------------------------------------
# Output a list item
#---------------------------------------------------------------

def cace_output_list(dictname, itemlist, outlines, indent):
    tabs = ''
    for i in range(0, indent):
        tabs = tabs + '\t'
    newline = tabs
    
    first = True
    for item in itemlist:
        if not first:
            newline = ''
            outlines.append(newline)
            newline = tabs + '+'
            outlines.append(newline)
        if isinstance(item, dict):
            outlines = cace_output_known_dict(dictname, item, outlines, False, indent)
            first = False
        elif dictname == 'results':
            if isinstance(item, str):
                # Results passed back in "testbenches" record
                newline = tabs + uchar_sub(item).strip('\n')
            elif isinstance(item, float):
                newline = tabs + str(item)
            else:
                # Results passed back as stdout from simulation or evaluation
                asciiout = list(uchar_sub(word) for word in item)
                newline = tabs +  ' '.join(asciiout)
            outlines.append(newline)
        elif dictname == 'conditions':
            # Results passed back as stdout from simulation or evaluation
            asciiout = list(uchar_sub(word) for word in item)
            newline = tabs +  ' '.join(asciiout)
            outlines.append(newline)
        else:
            # This should not happen---list items other than "results"
            # are only supposed to be dictionaries
            newline = tabs + '# Failed: ' + str(item)
            outlines.append(newline)
    return outlines

#---------------------------------------------------------------
#---------------------------------------------------------------

def cace_output_item(key, value, outlines, indent):
    tabs = ''
    for i in range(0, indent):
        tabs = tabs + '\t'
    newline = tabs

    if isinstance(value, str):
        moretab = '\t' if len(key) < 7 else ''
        newline = tabs + key + ':\t' + moretab + uchar_sub(value)
    elif isinstance(value, int):
        moretab = '\t' if len(str(key)) < 7 else ''
        newline = tabs + key + ':\t' + moretab + str(value)
    elif isinstance(value, float):
        moretab = '\t' if len(str(key)) < 7 else ''
        newline = tabs + key + ':\t' + moretab + str(value)
    elif isinstance(value, dict):
        outlines = cace_output_standard_comments(key, outlines)
        newline = tabs + key + ' {'
        outlines.append(newline)
        outlines = cace_output_known_dict(key, value, outlines, False, indent + 1)
        newline = tabs + '}'
    elif isinstance(value, list):
        # Handle lists that are not dictionaries
        just_lists = ['minimum', 'maximum', 'typical', 'Vmin', 'Vmax', 'format', 'tool']
        if key in just_lists:
            moretab = '\t' if len(str(key)) < 7 else ''
            newline = tabs + key + ':\t' + moretab + ' '.join(value)
        elif key == 'enumerate':
            # Restrict enumeration lines to 35 characters and split with
            # backslash-newlines
            numenums = len(value)
            newline = tabs + key + ':\t'
            lidx = 0
            while lidx < numenums:
                ridx = lidx + 1
                while ridx <= numenums:
                    enumstring = ' '.join(value[lidx:ridx])
                    if len(enumstring) > 35:
                        newline = newline + ' '.join(value[lidx:ridx-1])
                        if ridx <= numenums:
                            newline = newline + ' \\'
                        outlines.append(newline)
                        newline = tabs + '\t\t'
                        lidx = ridx - 1
                        break
                    else:
                        ridx = ridx + 1
                if ridx >= numenums:
                    newline = newline + ' '.join(value[lidx:])
                    break
        else:
            outlines = cace_output_standard_comments(key, outlines)
            newline = tabs + key + ' {'
            outlines.append(newline)
            outlines = cace_output_list(key, value, outlines, indent + 1)
            newline = tabs + '}'
    else:   # Treat like a string?
        moretab = '\t' if len(str(key)) < 7 else ''
        newline = tabs + key + ':\t' + moretab + uchar_sub(str(value))

    outlines.append(newline)
    return outlines

#---------------------------------------------------------------
# Output an known dictionary item.  The purpose is to output
# keys in a sane and consistent order when possible.  Includes
# output of "standard comments" for specific sections.
#---------------------------------------------------------------

def cace_output_standard_comments(dictname, outlines):
    if dictname == 'pins':
        outlines.append('')
        newline = '# Pin names and descriptions'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    elif dictname == 'paths':
        outlines.append('')
        newline = '# Paths to various files'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    elif dictname == 'dependencies':
        outlines.append('')
        newline = '# Project dependencies'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    elif dictname == 'electrical_parameters':
        outlines.append('')
        newline = '# List of electrical parameters to be measured and their specified limits'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    elif dictname == 'physical_parameters':
        outlines.append('')
        newline = '# List of physical parameters to be measured and their specified limits'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    elif dictname == 'default_conditions':
        outlines.append('')
        newline = '# Default values for electrical parameter measurement conditions'
        outlines.append(newline)
        newline = '# if not otherwise specified'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    return outlines

#---------------------------------------------------------------
# Output an known dictionary item.  The purpose is to output
# keys in a sane and consistent order when possible.  Includes
# output of "standard comments" for specific sections.
#---------------------------------------------------------------

def cace_output_known_dict(dictname, itemdict, outlines, doruntime, indent):
    if dictname == 'topmost':
        orderedlist = ['name', 'description', 'category', 'note', 'commit',
		'PDK', 'foundry', 'cace_format', 'authorship', 'paths',
		'dependencies', 'pins', 'default_conditions',
		'electrical_parameters', 'physical_parameters',
		'runtime_options']
        if 'cace_format' not in itemdict:
            itemdict['cace_format'] = '4.0'

    elif dictname == 'pins':
        orderedlist = ['name', 'description', 'type', 'direction', 'Vmin', 'Vmax', 'note']

    elif dictname == 'paths':
        orderedlist = ['root', 'documentation', 'schematic', 'layout',
		'magic', 'lvs_netlist', 'rcx_netlist', 'schem_netlist',
		'netgen', 'verilog', 'testbench', 'simulation', 'plots',
		'logs']

    elif dictname == 'dependencies':
        orderedlist = ['name', 'path', 'repository', 'commit', 'note']

    elif dictname == 'electrical_parameters':
        orderedlist = ['name', 'status', 'description', 'display', 'unit',
		'spec', 'results', 'simulate', 'measure', 'plot', 'variables',
		'conditions', 'testbenches']

    elif dictname == 'physical_parameters':
        orderedlist = ['name', 'status', 'description', 'display', 'unit',
		'spec', 'evaluate', 'conditions', 'results']

    elif dictname == 'default_conditions':
        orderedlist = ['name', 'description', 'display', 'unit', 'minimum',
		'typical', 'maximum', 'enumerate', 'step', 'stepsize', 'note']

    elif dictname == 'testbenches':
        orderedlist = ['filename', 'conditions', 'variables', 'results', 'format']

    elif dictname == 'authorship':
        orderedlist = ['designer', 'company', 'institution', 'organization',
		'address', 'email', 'url',
		'creation_date', 'modification_date', 'license', 'note']
        # Date string formatted as, e.g., "November 22, 2023 at 01:16pm"
        datestring = datetime.datetime.now().strftime('%B %e, %Y at %I:%M%P')
        if 'creation_date' not in itemdict:
            itemdict['creation_date'] = datestring
        # Always update modification date to current datestamp
        itemdict['modification_date'] = datestring

    elif dictname == 'spec':
        orderedlist = ['minimum', 'typical', 'maximum', 'note']

    elif dictname == 'results':
        orderedlist = ['name', 'minimum', 'typical', 'maximum']

    elif dictname == 'simulate':
        orderedlist = ['tool', 'template', 'filename', 'format', 'collate',
		'group_size', 'note']

    elif dictname == 'measure':
        orderedlist = ['tool', 'filename', 'calc', 'note']

    elif dictname == 'evaluate':
        orderedlist = ['tool', 'filename', 'note']

    elif dictname == 'conditions':
        orderedlist = ['name', 'description', 'display', 'unit', 'minimum',
		'typical', 'maximum', 'enumerate', 'step', 'stepsize', 'note']
    elif dictname == 'plot':
        orderedlist = ['filename', 'title', 'xaxis', 'yaxis', 'note']
    elif dictname == 'variables':
        orderedlist = ['name', 'display', 'unit', 'note']
    elif dictname == 'runtime_options':
        orderedlist = ['filename', 'netlist_source', 'score', 'debug', 'force', 'note']
    else:
        orderedlist = []

    unknown = []
    for key in orderedlist:
        if not doruntime and key == 'runtime_options':
            continue
        elif key in itemdict:
            value = itemdict[key]
            outlines = cace_output_item(key, value, outlines, indent)

    for key in itemdict:
        if key not in orderedlist:
            unknown.append(key)

    if len(unknown) > 0:
        outlines.append('')

    for key in unknown:
        print('Diagnostic: Adding item with unrecognized key ' + key + ' in dictionary ' + dictname)
        value = itemdict[key]
        outlines = cace_output_item(key, value, outlines, indent)
 
    return outlines

#---------------------------------------------------------------
# Output an unknown dictionary item
#---------------------------------------------------------------

def cace_output_dict(itemdict, outlines, indent):
    tabs = ''
    for i in range(0, indent):
        tabs = tabs + '\t'
    newline = tabs
    
    for key in itemdict:
        value = itemdict[key]
        outlines = cace_output_item(key, value, outlines, indent)

        outlines.append(newline)

    return outlines

#---------------------------------------------------------------
# Write a format 4.0 text file from a CACE datasheet dictionary
#
# If 'doruntime' is True, then write the runtime options
# dictionary.  If False, then leave it out of the output.
#---------------------------------------------------------------

def cace_write(datasheet, filename, doruntime=False):
    outlines = []

    newline = '#---------------------------------------------------'
    outlines.append(newline)

    if filename:
        newline = '# CACE format 4.0 characterization file ' + filename
        outlines.append(newline)
        newline = '#---------------------------------------------------'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)
    
    outlines = cace_output_known_dict('topmost', datasheet, outlines, doruntime, 0)

    # If filename is None, then write to stdout.
    if not filename:
        for line in outlines:
            print(line)
        return 0

    try:
        with open(filename, 'w') as ofile:
            for line in outlines:
                print(line, file=ofile)
    except:
        return 1

    return 0

#------------------------------------------------------------------
# Print usage statement
#------------------------------------------------------------------

def usage():
    print('Usage:')
    print('')
    print('cace_write.py <filename> <outfilename>')
    print('  Where <filename> is a pre-format 4.0 CACE JSON file.')
    print('  and <outfilename> is the name for the output text file.')
    print('')
    print('When run from the top level, this program parses a CACE')
    print('format JSON file and outputs a CACE format 4.0 text file.')

#------------------------------------------------------------------
# If called from the command line, this can be used to read in a
# pre-format 4.0 CACE JSON file and write out a CACE format 4.0
# text file.  It does exactly the same thing as the cace_compat.py
# script when run from the command line.
#------------------------------------------------------------------

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

    if len(arguments) == 2 and len(options) == 0:
        infilename = arguments[0]
        outfilename = arguments[1]
        if not os.path.isfile(infilename):
            print('Error:  No such file ' + infilename)
            sys.exit(1)

        with open(infilename, 'r') as ifile:
            try:
                dataset = json.load(ifile)
            except json.decoder.JSONDecodeError as e:
                print("Error:  Parse error reading JSON file " + datasheet + ':')
                print(str(e))
                sys.exit(1)

        # If 'data-sheet' is a dictionary in 'dataset' then set that as the top
        if 'data-sheet' in dataset:
            dataset = dataset['data-sheet']
        new_dataset = cace_compat.cace_compat(dataset, debug)
        if debug:
            print('Diagnostic (not writing file)---dataset is:')
            print(str(new_dataset))
        else:
            result = cace_write(new_dataset, outfilename)

    else:
        usage()
        sys.exit(1)

    sys.exit(result)

