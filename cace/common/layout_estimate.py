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
Generate an estimate of layout area from a SPICE netlist by
running magic in batch mode and calling up the PDK selections
non-interactively for each component in the netlist, and
querying the total device area.  It is up to the caller to
determine what overhead to apply for total layout area.
"""

import os
import re
import sys
import subprocess

from .cace_regenerate import get_magic_rcfile
from .safe_eval import safe_eval

from ..logging import (
    verbose,
    info,
    rule,
    success,
    warn,
    err,
    get_log_level,
    LogLevels,
)
from ..logging import subprocess as subproc
from ..logging import debug as dbg


def run_estimate(
    subname,
    subpins,
    complist,
    library,
    rcfile,
    keep=False,
):
    """
    This routine is called by layout_estimate after the netlist has been read
    in and the subcircuit has been identified and parsed.
    """

    parmrex = re.compile('([^=]+)=([^=]+)', re.IGNORECASE)

    areaum2 = 0

    # Write out a TCL script to generate the layout estimate
    #
    with open('estimate_script.tcl', 'w') as ofile:

        # Write a couple of simplifying procedures
        print('#!/usr/bin/env wish', file=ofile)
        print('#--------------------------------------------', file=ofile)
        print('# Script to create layout from netlist', file=ofile)
        print('# Source this in magic.', file=ofile)
        print('#--------------------------------------------', file=ofile)
        print('', file=ofile)
        print('suspendall', file=ofile)
        print('box 0um 0um 0um 0um', file=ofile)
        print('set totalarea 0', file=ofile)
        print('', file=ofile)

        for comp in complist:
            # Remove expressions, as they don't represent parameters that
            # can be interpreted by the cell generator, and whitespace
            # inside the quoted string messes up the tokenizing.
            comp = re.sub("='([^']*)'", '=0', comp)

            params = {}
            tokens = comp.split()
            instname = tokens[0]
            for token in tokens[1:]:
                rmatch = parmrex.match(token)
                if rmatch:
                    parmname = rmatch.group(1).upper()
                    parmval = rmatch.group(2)
                    params[parmname] = parmval
                else:
                    # Last one that isn't a parameter will be kept
                    devtype = token

            # devtype is first assumed to exist in the library. If not, check other
            # sources such as additional PDK namespaces and directories in the search
            # path. Finally, put call to read the subcell in a try/catch block to
            # avoid having it terminate the script.

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
            print('    set loclib [lindex [namespace children] 0]', file=ofile)
            print(
                '    if {[string first :: ${loclib}] == 0} {set loclib [string range $loclib 2 end]}',
                file=ofile,
            )
            print(
                '    set device [info commands ${loclib}::'
                + devtype
                + '_draw]',
                file=ofile,
            )
            print('} else {', file=ofile)
            print('    set loclib ' + library, file=ofile)
            print('}', file=ofile)

            print('if {$device != ""} {', file=ofile)
            print('    set is_gencell true', file=ofile)
            print('} else {', file=ofile)
            print('    set is_gencell false', file=ofile)
            print('}', file=ofile)

            outparts = []
            outparts.append(
                'magic::gencell ${loclib}::' + devtype + ' ' + instname
            )
            outparts.append('-spice')
            for item in params:
                outparts.append(str(item))
                outparts.append(params[item])

            outstring = ' '.join(outparts)
            print('set sv {0 0 0 0}', file=ofile)
            print('if {$is_gencell == true} {', file=ofile)
            print('   if {![catch {' + outstring + '}]} {', file=ofile)
            print('      select cell ' + instname, file=ofile)
            print('      set v [box values]', file=ofile)
            print('      delete', file=ofile)
            print('   }', file=ofile)
            print('} else {', file=ofile)
            # Subcircuit is not a PDK-generated cell, so try the usual "getcell"
            print('    if {![catch {getcell ${devtype}}]} {', file=ofile)
            print('        identify $instname', file=ofile)
            print('        set v [box values]', file=ofile)
            print('        delete', file=ofile)
            print('    }', file=ofile)
            print('}', file=ofile)

            print('set w [expr [lindex $v 2] - [lindex $v 0]]', file=ofile)
            print('set h [expr [lindex $v 3] - [lindex $v 1]]', file=ofile)
            print('set area [expr $w * $h]', file=ofile)

            if get_log_level() <= LogLevels.DEBUG:
                print(
                    'puts stdout "single device ' + instname + ' area is $a"',
                    file=ofile,
                )

            print('set totalarea [expr $totalarea + $area]', file=ofile)

        print('resumeall', file=ofile)
        print('refresh', file=ofile)
        print(
            'set total2area [expr int(ceil([magic::i2u [magic::i2u $totalarea]]))]',
            file=ofile,
        )
        print('puts stdout "total device area = $total2area um^2"', file=ofile)
        print('quit -noprompt', file=ofile)

    # Run the script now, and wait for it to finish

    with open('estimate_script.tcl', 'r') as ifile:
        with subprocess.Popen(
            ['magic', '-dnull', '-noconsole', '-rcfile', rcfile],
            stdout=subprocess.PIPE,
            stdin=ifile,
            universal_newlines=True,
        ) as script:
            arealine = re.compile('.*=[ \t]*([0-9]+)[ \t]*um\^2')
            output = script.communicate()[0]
            for line in output.splitlines():
                dbg(line)
                lmatch = arealine.match(line)
                if lmatch:
                    areaum2 = lmatch.group(1)

    if not keep:
        os.remove('estimate_script.tcl')

    return areaum2


def layout_estimate(inputfile, library, rcfile, keep):
    """
    This is the main routine if layout_estimate.py is called from python.

    'inputfile' is the name of a schematic-captured netlist to read.
    """

    # Read SPICE netlist

    with open(inputfile, 'r') as ifile:
        spicetext = ifile.read()

    subrex = re.compile('.subckt[ \t]+(.*)$', re.IGNORECASE)
    # All devices are going to be subcircuits
    xrex = re.compile('^x([^ \t]+)[ \t](.*)$', re.IGNORECASE)
    namerex = re.compile('([^= \t]+)[ \t]+(.*)$', re.IGNORECASE)
    endsrex = re.compile('^[ \t]*\.ends', re.IGNORECASE)

    # Concatenate continuation lines
    spicelines = spicetext.replace('\n+', ' ').splitlines()

    insub = False
    subname = ''
    subpins = ''
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
                    raise SyntaxError(
                        'File ' + inputfile + ': Failure to parse line ' + line
                    )
                    break
        else:
            lmatch = endsrex.match(line)
            if lmatch:
                subdict[subname] = complist
                pindict[subname] = subpins
                subname = None
                insub = False
                subpins = None
                complist = []
            else:
                xmatch = xrex.match(line)
                if xmatch:
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
                        devtype = token
                if devtype in subdict:
                    expanded = True
                    # Replace this component by its subcell expansion
                    for i in range(mult):
                        newcomps.extend(subdict[devtype])
                else:
                    newcomps.append(comp)
            subdict[key] = newcomps

    toppath = os.path.split(inputfile)[1]
    topname = os.path.splitext(toppath)[0]
    return run_estimate(
        topname, pindict[topname], subdict[topname], library, rcfile, keep
    )
