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

"""
Do a pre-check on a schematic-captured netlist to see if it can
be made into a layout without generating errors due to devices that
cannot be physically realized.
"""

import os
import re
import sys
import subprocess

from .safe_eval import safe_eval

from ..logging import (
    verbose,
    info,
    rule,
    success,
    warn,
    err,
)
from ..logging import subprocess as subproc
from ..logging import debug as dbg


def run_precheck(
    subname,
    subpins,
    complist,
    pdkpath,
    library,
    keep=False,
):
    """
    This routine is called after the schematic-captured netlist
    has been read and processed for the subcircuit information.
    """

    parmrex = re.compile('([^=]+)=([^=]+)', re.IGNORECASE)
    exprrex = re.compile("'([^']+)'", re.IGNORECASE)

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
                dbg(line)
                lmatch = failline.match(line)
                if lmatch:
                    faillines.append(line)

    if not keep:
        os.remove('precheck_script.tcl')

    return faillines


# ---------------------------------------------------------------
# netlist_precheck
#
# Main routine for netlist_precheck.py if called from python
#
# 'inputfile' is the layout-extracted netlist
# ---------------------------------------------------------------


def netlist_precheck(inputfile, pdkpath, library, keep=False):
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
        err('Issue with schematic netlist:')
        err(f'Input filename is {toppath}')

    if topname not in pindict:
        err(f'Precheck error: Top cell name {topname} not in pin dictionary!')
        return -1

    if topname not in subdict:
        err(
            f'Precheck error:  Top cell name {topname} not in subcircuit dictionary!'
        )
        return -1

    return run_precheck(
        topname,
        pindict[topname],
        subdict[topname],
        pdkpath,
        library,
        keep,
    )
