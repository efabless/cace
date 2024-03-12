#!/usr/bin/env python3
# ----------------------------------------------------------------------
# netlist_precheck.py
# ----------------------------------------------------------------------
#
# Do a pre-check on a schematic-captured netlist to see if it can
# be made into a layout without generating errors due to devices that
# cannot be physically realized.
#
# ----------------------------------------------------------------------
# Written by Tim Edwards
# Efabless Corporation
# December 28, 2016
# Version 1.0
# Revised December 19, 2023
# ----------------------------------------------------------------------

import os
import re
import sys
import subprocess

from .safe_eval import safe_eval

# ---------------------------------------------------------------
# run_precheck
#
# This routine is called after the schematic-captured netlist
# has been read and processed for the subcircuit information.
# ---------------------------------------------------------------


def run_precheck(
    subname,
    subpins,
    complist,
    pdkpath,
    library,
    debug=False,
    keep=False,
    logname='',
):
    parmrex = re.compile('([^=]+)=([^=]+)', re.IGNORECASE)
    exprrex = re.compile("'([^']+)'", re.IGNORECASE)

    logfile = sys.stdout
    if logname != '':
        try:
            logfile = open(logname, 'w')
        except:
            print(
                'Cannot open log file ' + logname + ' for writing.',
                file=sys.stderr,
            )

    # Write out a TCL script to generate and measure component layouts
    #
    with open('precheck_script.tcl', 'w') as ofile:

        # Write a couple of simplifying procedures
        print('#!/usr/bin/env wish', file=ofile)
        print('#--------------------------------------------', file=ofile)
        print('# Script to check schematic for valid layout', file=ofile)
        print('# Source this in magic.', file=ofile)
        print('#--------------------------------------------', file=ofile)
        print('', file=ofile)
        print('suspendall', file=ofile)
        print('box 0um 0um 0um 0um', file=ofile)
        print('set failures 0', file=ofile)
        print('', file=ofile)

        for comp in complist:
            tokens = comp.split()
            instname = tokens[0]
            device = instname[0].lower()
            if device == 'x':
                for token in tokens[1:]:
                    rmatch = parmrex.match(token)
                    if rmatch:
                        break
                    # Last one that isn't a parameter will be kept
                    devtype = token
            else:
                devtype = device[1:]

            # devtype is assumed to exist in the library. If not, increment failures
            print(
                'set device [info commands '
                + library
                + '::'
                + devtype
                + '_draw]',
                file=ofile,
            )
            # on failure, check for a different library by looking at the namespaces
            print('if {$device == ""} {', file=ofile)
            print(
                '    set templib [lindex [namespace children] 0]', file=ofile
            )
            print(
                '    set device [info commands ${templib}::'
                + devtype
                + '_draw]',
                file=ofile,
            )
            print('    if {$device != ""} {', file=ofile)
            print(
                '        puts stdout "Found cell '
                + devtype
                + ' in namespace ${templib}."',
                file=ofile,
            )
            print('    }', file=ofile)
            print('}', file=ofile)
            # on failure, check if the cell can be read from a known directory in the path
            print('if {$device == ""} {', file=ofile)
            print('    foreach dir [path search] {', file=ofile)
            print(
                '        if {![catch {set device [glob ${dir}/'
                + devtype
                + '.mag]}]} {break}',
                file=ofile,
            )
            print('    }', file=ofile)
            print('    if {$device != ""} {', file=ofile)
            print(
                '        puts stdout "Found cell '
                + devtype
                + ' in search path ${dir}."',
                file=ofile,
            )
            print('    }', file=ofile)
            print('}', file=ofile)

        print('resumeall', file=ofile)
        print('refresh', file=ofile)
        print('puts stdout "number of failures = $failures"', file=ofile)
        print('quit -noprompt', file=ofile)

    # Construct the full path to the magicrc file
    magicopts = ['magic', '-dnull', '-noconsole']
    if pdkpath != '':
        pdkname = os.path.split(pdkpath)[1]
        magicrc = os.path.join(
            pdkpath, 'libs.tech', 'magic', pdkname + '.magicrc'
        )
    magicopts.append('-rcfile')
    magicopts.append(magicrc)

    # Run the script now, and wait for it to finish
    faillines = []
    with open('precheck_script.tcl', 'r') as ifile:
        with subprocess.Popen(
            magicopts,
            stdout=subprocess.PIPE,
            stdin=ifile,
            universal_newlines=True,
        ) as script:
            failline = re.compile('.*\[ \t\]*\[([0-9]+)\[ \t\]*')
            output = script.communicate()[0]
            for line in output.splitlines():
                if debug:
                    print(line)
                else:
                    lmatch = failline.match(line)
                    if lmatch:
                        faillines.append(line)
                if logfile:
                    print(line, file=logfile)

    if logname != '':
        logfile.close()

    if not keep:
        os.remove('precheck_script.tcl')

    return faillines


# ---------------------------------------------------------------
# netlist_precheck
#
# Main routine for netlist_precheck.py if called from python
#
# 'inputfile' is the layout-extracted netlist
# If 'debug' is True, then output diagnostic information and
# retain all generated files.
# If logfile is an empty string, then write results to stdout,
# otherwise write results to the named log file.
# ---------------------------------------------------------------


def netlist_precheck(
    inputfile, pdkpath, library, debug=False, keep=False, logfile=''
):
    # Read SPICE netlist

    with open(inputfile, 'r') as ifile:
        spicetext = ifile.read()

    subrex = re.compile('.subckt[ \t]+(.*)$', re.IGNORECASE)
    namerex = re.compile('([^= \t]+)[ \t]+(.*)$', re.IGNORECASE)
    endsrex = re.compile('^[ \t]*\.ends', re.IGNORECASE)
    # All device instances
    devrex = re.compile('[a-z]([^ \t]+)[ \t](.*)$', re.IGNORECASE)
    # Specifically subcircuit device instances (unused)
    xrex = re.compile('x([^ \t]+)[ \t](.*)$', re.IGNORECASE)
    # Zero volt DC sources and zero ohm resistors should be acceptable
    # (future enhancement)
    rrex = re.compile(r'([ \t]*)[*][ \t]*$', re.IGNORECASE)
    vrex = re.compile(r'([ \t]+)[ \t]*<([^>]+)>', re.IGNORECASE)

    # Concatenate continuation lines
    spicelines = spicetext.replace('\n+', ' ').splitlines()

    insub = False
    subname = ''
    subpins = []
    complist = []
    subdict = {}
    pindict = {}
    for line in spicelines:
        if not insub:
            lmatch = subrex.match(line)
            if lmatch:
                rest = lmatch.group(1)
                smatch = namerex.match(rest)
                if smatch:
                    subname = smatch.group(1)
                    subpins = smatch.group(2)
                    insub = True
        else:
            lmatch = endsrex.match(line)
            if lmatch:
                subdict[subname] = complist
                pindict[subname] = subpins
                insub = False
                subname = None
                subpins = None
                complist = []
            else:
                dmatch = devrex.match(line)
                if dmatch:
                    complist.append(line)

    # For each circuit, expand any subcircuits for which components were listed
    # Keep doing this until there is nothing left to expand.

    parmrex = re.compile('([^=]+)=([^=]+)', re.IGNORECASE)
    expanded = True
    while expanded:
        expanded = False
        for key in subdict:
            complist = subdict[key]
            newcomps = []
            for comp in complist:
                mult = 1
                tokens = comp.split()
                device = tokens[0][0].lower()
                for token in tokens[1:]:
                    rmatch = parmrex.match(token)
                    if rmatch:
                        parmname = rmatch.group(1).upper()
                        if parmname.upper() == 'M':
                            parmval = rmatch.group(2)
                            try:
                                mult = int(parmval)
                            except ValueError:
                                mult = safe_eval(parmval)
                    else:
                        # Last one that isn't a parameter will be kept
                        # (only applies to subcircuit instances)
                        devtype = token
                if device == 'x' and devtype in subdict:
                    expanded = True
                    # Replace this component by its subcell expansion
                    for i in range(mult):
                        newcomps.extend(subdict[devtype])
                else:
                    newcomps.append(comp)
            subdict[key] = newcomps

    toppath = os.path.split(inputfile)[1]
    topname = os.path.splitext(toppath)[0]

    if topname == '':
        print('Issue with schematic netlist: ')
        print('Input filename is ' + toppath)

    if topname not in pindict:
        print(
            'Precheck error:  Top cell name '
            + topname
            + ' not in pin dictionary!'
        )
        return -1

    if topname not in subdict:
        print(
            'Precheck error:  Top cell name '
            + topname
            + ' not in subcircuit dictionary!'
        )
        return -1

    return run_precheck(
        topname,
        pindict[topname],
        subdict[topname],
        pdkpath,
        library,
        debug,
        keep,
        logfile,
    )


# --------------------------------------------------------------------
# Print usage information
# --------------------------------------------------------------------


def usage():
    print('')
    print('Usage:')
    print('netlist_precheck.py <netlist_file> <pdk_library> [-options]')
    print('   where [-options] can be one of:')
    print('      -help')
    print('      -debug')
    print('      -keep')
    print('      -log=<logfile>')
    print('')


# --------------------------------------------------------------------
# Main routine for layout_precheck.py if called from the command line
# --------------------------------------------------------------------

if __name__ == '__main__':

    # Parse command line for options and arguments
    options = []
    arguments = []
    for item in sys.argv[1:]:
        if item.find('-', 0) == 0:
            options.append(item)
        else:
            arguments.append(item)

    if len(arguments) > 1:
        inputfile = arguments[0]
        library = arguments[1]
    else:
        usage()
        sys.exit(1)

    debug = False
    keep = False
    logfile = ''
    pdkpath = ''
    for item in options:
        result = item.split('=')
        if result[0] == '-help':
            usage()
            sys.exit(0)
        elif result[0] == '-debug':
            debug = True
        elif result[0] == '-keep':
            keep = True
        elif result[0] == '-log':
            if len(result) == 2:
                logfile = result[1]
            else:
                logfile = 'precheck.log'
        elif result[0] == '-pdkpath':
            if len(result) == 2:
                pdkpath = result[1]
            else:
                usage()
                sys.exit(1)
        else:
            print('Bad option ' + item)
            usage()
            sys.exit(1)

    netlist_precheck(inputfile, pdkpath, library, debug, keep, logfile)
