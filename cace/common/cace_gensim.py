#!/usr/bin/env python3
#
# cace_gensim.py
#
# This is the main part of the automatic characterization engine.  It takes
# a simulation template file as input and parses it for information on
# how to construct files for the characterization simulations.  Output is
# a number of simulation files (for now, at least, in ngspice format).
#
# Note:  Unlike the former version of this script, the simulations are
# done independently by cace_launch., which is not invoked from
# cace_gensim.  cace_gensim only generates the set of simulation netlists.
#
# There is no command line usage of cace_gensim.py.  It is called from
# either cace.py (command line) or cace_gui.py (GUI)
#

import os
import sys
import json
import re
import time
import shutil
import subprocess
from functools import reduce

from .spiceunits import spice_unit_convert
from .spiceunits import numeric

from .cace_write import *
from .cace_regenerate import get_pdk_root
from .safe_eval import safe_eval

# -----------------------------------------------------------------------
# Read the indicated file, find the .subckt line, and copy out the
# pin names and DUT name.  Complain if pin names don't match pin names
# in the datasheet.
# NOTE:  There may be more than one subcircuit in the netlist, so
# insist upon the actual DUT (pname)
# -----------------------------------------------------------------------


def construct_dut_from_path(pname, pathname, pinlist):

    subrex = re.compile('^[^\*]*[ \t]*.subckt[ \t]+(.*)$', re.IGNORECASE)
    outline = ''
    dutname = ''
    if not os.path.isfile(pathname):
        print('Error:  No design netlist file ' + pathname + ' found.')
        return outline

    # First pull in all lines of the file and concatenate all continuation
    # lines.
    with open(pathname, 'r') as ifile:
        duttext = ifile.read()

    dutlines = duttext.replace('\n+', ' ').splitlines()
    found = 0
    for line in dutlines:
        lmatch = subrex.match(line)
        if lmatch:
            rest = lmatch.group(1)
            tokens = rest.split()
            dutname = tokens[0]
            if dutname == pname:
                outline = outline + 'X' + dutname + ' '
                for pin in tokens[1:]:
                    upin = pin.upper()
                    try:
                        pinmatch = next(
                            item
                            for item in pinlist
                            if item['name'].upper() == upin
                        )
                    except StopIteration:
                        # Maybe this is not the DUT?
                        found = 0
                        # Try the next line (to be done)
                        break
                    else:
                        outline = outline + pin + ' '
                        found += 1
                break

    if found == 0 and dutname == '':
        print('File ' + pathname + ' does not contain any subcircuits!')
        raise SyntaxError(
            'File ' + pathname + ' does not contain any subcircuits!'
        )
    elif found == 0:
        if dutname != pname:
            print(
                'File '
                + pathname
                + ' does not have a subcircuit named '
                + pname
                + '!'
            )
            raise SyntaxError(
                'File '
                + pathname
                + ' does not have a subcircuit named '
                + pname
                + '!'
            )
        else:
            print('Pins in schematic: ' + str(tokens[1:]))
            print('Pins in datasheet: ', end='')
            for pin in pinlist:
                print(pin['name'] + ' ', end='')
            print('')
            print(
                'File '
                + pathname
                + ' subcircuit '
                + pname
                + ' does not have expected pins!'
            )
            raise SyntaxError(
                'File '
                + pathname
                + ' subcircuit '
                + pname
                + ' does not have expected pins!'
            )
    elif found != len(pinlist):
        print(
            'File ' + pathname + ' does not contain the project DUT ' + pname
        )
        print('or not all pins of the DUT were found.')
        print('Pinlist is : ', end='')
        for pinrec in pinlist:
            print(pinrec['name'] + ' ', end='')
        print('')

        print('Length of pinlist is ' + str(len(pinlist)))
        print('Number of pins found in subcircuit call is ' + str(found))
        raise SyntaxError(
            'File ' + pathname + ' does not contain the project DUT!'
        )
    else:
        outline = outline + dutname + '\n'
    return outline


# -----------------------------------------------------------------------
# floating-point linear numeric sequence generator, to be used with
# condition generator
# -----------------------------------------------------------------------


def linseq(condition, unit, start, stop, step):
    a = numeric(start)
    e = numeric(stop)
    s = numeric(step)
    while a < e + s:
        if a > e:
            yield (condition, unit, stop)
        else:
            yield (condition, unit, str(a))
        a = a + s


# -----------------------------------------------------------------------
# floating-point logarithmic numeric sequence generator, to be used with
# condition generator
# -----------------------------------------------------------------------


def logseq(condition, unit, start, stop, step):
    a = numeric(start)
    e = numeric(stop)
    s = numeric(step)
    while a < e * s:
        if a > e:
            yield (condition, unit, stop)
        else:
            yield (condition, unit, str(a))
        a = a * s


# -----------------------------------------------------------------------
# binary (integer) numeric sequence generators, to be used with
# condition generator
# -----------------------------------------------------------------------


def bindigits(n, bits):
    s = bin(n & int('1' * bits, 2))[2:]
    return ('{0:0>%s}' % (bits)).format(s)


# -----------------------------------------------------------------------
# compute the 2's compliment of integer value val
# -----------------------------------------------------------------------


def twos_comp(val, bits):
    if (
        val & (1 << (bits - 1))
    ) != 0:   # if sign bit is set e.g., 8bit: 128-255
        val = val - (1 << bits)        # compute negative value
    return val                         # return positive value as is


# -----------------------------------------------------------------------
# Binary sequence counter (used for linear stepping of binary vectors)
# -----------------------------------------------------------------------


def bcount(condition, unit, start, stop, step):
    blen = len(start)
    a = safe_eval('0b' + start)
    e = safe_eval('0b' + stop)
    if a > e:
        a = twos_comp(a, blen)
        e = twos_comp(e, blen)
    s = int(step)
    while a < e + s:
        if a > e:
            bstr = bindigits(e, blen)
        else:
            bstr = bindigits(a, blen)
        yield (condition, unit, bstr)
        a = a + s


# -----------------------------------------------------------------------
# Binary sequence shifter (used for logarithmic stepping of binary
# vectors)
# -----------------------------------------------------------------------


def bshift(condition, unit, start, stop, step):
    a = safe_eval('0b' + start)
    e = safe_eval('0b' + stop)
    if a > e:
        a = twos_comp(a, blen)
        e = twos_comp(e, blen)
    s = int(step)
    while a < e * s:
        if a > e:
            bstr = bindigits(e, blen)
        else:
            bstr = bindigits(a, blen)
        yield (condition, unit, bstr)
        a = a * s


# -----------------------------------------------------------------------
# Define a generator for conditions.  Given a condition (dictionary),
# return (as a yield) each specified condition as a 3-tuple
# (condition_type, value, unit)
# -----------------------------------------------------------------------


def condition_gen(cond):
    lcond = cond['name']
    if 'unit' in cond:
        unit = cond['unit']
    else:
        unit = ''

    if 'enumerate' in cond:
        for i in cond['enumerate']:
            yield (lcond, unit, i)
    elif 'maximum' in cond and 'step' in cond and cond['step'] == 'linear':
        minimum = cond['minimum'] if 'minimum' in cond else 1
        if unit == "'b" or '[' in lcond:
            yield from bcount(
                lcond, unit, minimum, cond['maximum'], cond['stepsize']
            )
        else:
            print('Diagnostic: yield from linseq')
            yield from linseq(
                lcond, unit, minimum, cond['maximum'], cond['stepsize']
            )
    elif (
        'maximum' in cond and 'step' in cond and cond['step'] == 'logarithmic'
    ):
        minimum = cond['minimum'] if 'minimum' in cond else 1
        if unit == "'b" or '[' in lcond:
            yield from bshift(
                lcond, unit, minimum, cond['maximum'], cond['stepsize']
            )
        else:
            yield from logseq(
                lcond, unit, minimum, cond['maximum'], cond['stepsize']
            )
    elif 'minimum' in cond and 'maximum' in cond and 'typical' in cond:
        yield (lcond, unit, cond['minimum'])
        yield (lcond, unit, cond['typical'])
        yield (lcond, unit, cond['maximum'])
    elif 'minimum' in cond and 'maximum' in cond:
        yield (lcond, unit, cond['minimum'])
        yield (lcond, unit, cond['maximum'])
    elif 'minimum' in cond and 'typical' in cond:
        yield (lcond, unit, cond['minimum'])
        yield (lcond, unit, cond['typical'])
    elif 'maximum' in cond and 'typical' in cond:
        yield (lcond, unit, cond['typical'])
        yield (lcond, unit, cond['maximum'])
    elif 'minimum' in cond:
        yield (lcond, unit, cond['minimum'])
    elif 'maximum' in cond:
        yield (lcond, unit, cond['maximum'])
    elif 'typical' in cond:
        yield (lcond, unit, cond['typical'])


# -----------------------------------------------------------------------
# Find the maximum time to run a simulation.  This is the maximum of:
# (1) maximum value, if parameter is RISETIME or FALLTIME, and (2) maximum
# RISETIME or FALLTIME of any condition.
#
# "lcondlist" is the list of local conditions extended by the list of
# all global conditions that are not overridden by local values.
#
# NOTE:  This list is limited to rise and fall time values, as they are
# the only time constraints known to cace_gensim at this time.  This list
# will be extended as more simulation parameters are added.
# -----------------------------------------------------------------------


def findmaxtime(param, lcondlist):
    maxtime = 0.0
    try:
        simunit = param['unit']
    except KeyError:
        # Plots has no min/max/typ so doesn't require units.
        if 'plot' in param:
            return maxtime

    maxval = 0.0
    found = False
    if 'maximum' in param:
        prec = param['maximum']
        if 'target' in prec:
            pmax = prec['target']
            try:
                maxval = numeric(spice_unit_convert([simunit, pmax], 'time'))
                found = True
            except:
                pass
    if not found and 'typical' in param:
        prec = param['typical']
        if 'target' in prec:
            ptyp = prec['target']
            try:
                maxval = numeric(spice_unit_convert([simunit, ptyp], 'time'))
                found = True
            except:
                pass
    if not found and 'minimum' in param:
        prec = param['minimum']
        if 'target' in prec:
            pmin = prec['target']
            try:
                maxval = numeric(spice_unit_convert([simunit, pmin], 'time'))
                found = True
            except:
                pass
    if maxval > maxtime:
        maxtime = maxval
    for cond in lcondlist:
        condtype = cond['name'].split(':', 1)[0]
        if condtype == 'RISETIME' or condtype == 'FALLTIME':
            condunit = cond['unit']
            maxval = 0.0
            if 'maximum' in cond:
                maxval = numeric(
                    spice_unit_convert([condunit, cond['maximum']], 'time')
                )
            elif 'enumerate' in cond:
                maxval = numeric(
                    spice_unit_convert(
                        [condunit, cond['enumerate'][-1]], 'time'
                    )
                )
            elif 'typical' in cond:
                maxval = numeric(
                    spice_unit_convert([condunit, cond['typical']], 'time')
                )
            elif 'minimum' in cond:
                maxval = numeric(
                    spice_unit_convert([condunit, cond['minimum']], 'time')
                )
            if maxval > maxtime:
                maxtime = maxval

    return maxtime


# -----------------------------------------------------------------------
# Picked up from StackOverflow:  Procedure to remove non-unique entries
# in a list of lists (as always, thanks StackOverflow!).
# -----------------------------------------------------------------------


def uniquify(seq):
    seen = set()
    return [x for x in seq if str(x) not in seen and not seen.add(str(x))]


# -----------------------------------------------------------------------
# Replace the substitution token {INCLUDE_DUT} with the contents of the
# DUT subcircuit netlist file.  "functional" is a list of IP block names
# that are to be searched for in .include lines in the netlist and
# replaced with functional view equivalents (if such exist).
# -----------------------------------------------------------------------


def inline_dut(filename, functional, rootpath, ofile):

    # SPICE comment
    comtrex = re.compile(r'^\*')

    # SPICE include statement
    inclrex = re.compile(
        r'[ \t]*\.include[ \t]+["\']?([^"\' \t]+)["\']?', re.IGNORECASE
    )

    # Node name with brackets
    braktrex = re.compile(r'([^ \t]+)\[([^ \t])\]', re.IGNORECASE)

    # SPICE subcircuit line
    subcrex = re.compile(r'[ \t]*x([^ \t]+)[ \t]+(.*)$', re.IGNORECASE)

    librex = re.compile(r'(.*)__(.*)', re.IGNORECASE)
    endrex = re.compile(r'[ \t]*\.end[ \t]*', re.IGNORECASE)
    endsrex = re.compile(r'[ \t]*\.ends[ \t]*', re.IGNORECASE)

    # IP names in the form
    # <user_path>/design/<project>/spi/<spice-type>/<proj_netlist>

    locpathrex = re.compile(r'(.+)/design/([^/]+)/spi/([^/]+)/([^/ \t]+)')
    altpathrex = re.compile(r'(.+)/design/([^/]+)/([^/]+)/([^/]+)/([^/ \t]+)')

    # To be completed
    with open(filename, 'r') as ifile:
        nettext = ifile.read()

    netlines = nettext.replace('\n+', ' ').splitlines()
    for line in netlines:
        subsline = line
        cmatch = comtrex.match(line)
        if cmatch:
            print(line, file=ofile)
            continue
        # Check for ".end" which should be removed (but not ".ends", which must remain)
        ematch = endrex.match(line)
        if ematch:
            smatch = endsrex.match(line)
            if not smatch:
                continue
        imatch = inclrex.match(line)
        if imatch:
            incpath = imatch.group(1)
            # Substitution behavior is complicated due to the difference between netlist
            # files from schematic capture vs. layout and read-only vs. read-write IP.
            incroot = os.path.split(incpath)[1]
            incname = os.path.splitext(incroot)[0]
            lmatch = librex.match(incname)
            if lmatch:
                ipname = lmatch.group(2)
            else:
                ipname = incname
            if ipname.upper() in functional:
                # Search for functional view (depends on if this is a read-only IP or
                # read-write local subcircuit)
                funcpath = None
                ippath = ippathrex.match(incpath)
                if ippath:
                    userpath = ippath.group(1)
                    ipname2 = ippath.group(2)
                    ipversion = ippath.group(3)
                    spitype = ippath.group(4)
                    ipname3 = ippath.group(5)
                    ipnetlist = ippath.group(6)
                    funcpath = (
                        userpath
                        + '/design/ip/'
                        + ipname2
                        + '/'
                        + ipversion
                        + '/spice-func/'
                        + ipname
                        + '.spice'
                    )
                else:
                    locpath = locpathrex.match(incpath)
                    if locpath:
                        userpath = locpath.group(1)
                        ipname2 = locpath.group(2)
                        spitype = locpath.group(3)
                        ipnetlist = locpath.group(4)
                        funcpath = (
                            userpath
                            + '/design/'
                            + ipname2
                            + '/spi/func/'
                            + ipname
                            + '.spice'
                        )
                    else:
                        altpath = altpathrex.match(incpath)
                        if altpath:
                            userpath = altpath.group(1)
                            ipname2 = altpath.group(2)
                            spitype = altpath.group(3)
                            ipname3 = altpath.group(4)
                            ipnetlist = altpath.group(5)
                            funcpath = (
                                userpath
                                + '/design/'
                                + ipname2
                                + '/spi/func/'
                                + ipname
                                + '.spice'
                            )

                funcpath = os.path.expanduser(funcpath)
                if funcpath and os.path.exists(funcpath):
                    print('Subsituting functional view for IP block ' + ipname)
                    print('Original netlist is ' + incpath)
                    print('Functional netlist is ' + funcpath)
                    subsline = '.include ' + funcpath
                elif funcpath:
                    print('Original netlist is ' + incpath)
                    print(
                        'Functional view specified but no functional view found.'
                    )
                    print('Tried looking for ' + funcpath)
                    print('Retaining original view.')
                else:
                    print('Original netlist is ' + incpath)
                    print(
                        'Cannot make sense of netlist path to find functional view.'
                    )

        # If include file name is in <lib>__<cell> format (from electric) and the
        # functional view is not, then find the subcircuit call and replace the
        # subcircuit name.  At least at the moment, the vice versa case does not
        # happen.

        smatch = subcrex.match(line)
        if smatch:
            subinst = smatch.group(1)
            tokens = smatch.group(2).split()
            # Need to test for parameters passed to subcircuit.  The actual subcircuit
            # name occurs before any parameters.
            params = []
            pins = []
            for token in tokens:
                if '=' in token:
                    params.append(token)
                else:
                    pins.append(token)

            subname = pins[-1]
            pins = pins[0:-1]
            lmatch = librex.match(subname)
            if lmatch:
                testname = lmatch.group(1)
                if testname.upper() in functional:
                    subsline = (
                        'X'
                        + subinst
                        + ' '
                        + ' '.join(pins)
                        + ' '
                        + testname
                        + ' '
                        + ' '.join(params)
                    )

        # Remove any array brackets from node names in the top-level subcircuit,
        # because they interfere with the array notation used by XSPICE which may
        # be present in functional views (replace bracket characters with
        # underscores).
        #
        # subsline = subsline.replace('[', '_').replace(']', '_')
        #
        # Do this *only* when there are no spaces inside the brackets, or else
        # any XSPICE primitives in the netlist containing arrays will get messed
        # up.
        subsline = braktrex.sub(r'\1_\2_', subsline)

        ofile.write(subsline + '\n')

    ofile.write('\n')


# -----------------------------------------------------------------------
# Read a template file and record all of the variable names that will
# be substituted, so it is clear which local and global conditions
# need to be enumerated.  Vectors are reduced to just the vector name.
#
# Returns a dictionary with keys corresponding to condition names;
# the dictionary values are unused and just set to "True".
# -----------------------------------------------------------------------


def get_condition_names_used(testbenchpath, testbench):

    template = os.path.join(testbenchpath, testbench)
    if not os.path.isfile(template):
        print('Error:  No such template file ' + template)
        return

    with open(template, 'r') as ifile:
        simtext = ifile.read()

    simlines = simtext.splitlines()
    condlist = {}

    # Regular expressions
    # varex:		variable name {name}
    varex = re.compile(r'\{([^ \}\t]+)\}')

    # Vectors in name[number|range] format
    vectrex = re.compile(r'([^\[]+)\[([0-9:]+)\]')

    for line in simlines:
        for patmatch in varex.finditer(line):
            pattern = patmatch.group(1)

            # For condition names in the form {cond=value}, use only the name
            if '=' in pattern:
                pattern = pattern.split('=')[0]

            # For condition names in the form {cond|value}, use only the name
            if '|' in pattern:
                pstart = pattern.split('|')[0]
                if pstart != 'PIN' and pstart != 'FUNCTIONAL':
                    pattern = pstart

            pmatch = vectrex.match(pattern)
            if pmatch:
                pattern = pmatch.group(1) + '['
            condlist[pattern] = True

    return condlist


# -----------------------------------------------------------------------
# Define how to write a simulation file by making substitutions into a
# template schematic.
#
# 	filename:  Root name of the simulatable output file
# 	paths:	   Dictionary of paths from the characterization file
# 	tool:	   Name of tool that uses the template (e.g., "ngspice")
# 	template:  Name of the template file to be substituted
# 	dutpath:   Path and filename of the design netlist
# 	simvals:   Complete list of conditions to be enumerated
# 	maxtime:   Value to use for {Tmax} substitution
# 	schemline: DUT pin list from schematic, for ordering
# 	pdkname:   Name of the PDK pulled from the datasheet
# -----------------------------------------------------------------------


def substitute(
    filename,
    paths,
    tool,
    template,
    dutpath,
    simvals,
    schemline,
    pdkname,
    debug,
):
    """Simulation derived by substitution into template schematic"""

    # Regular expressions
    # varex:		variable name {name}
    # defaultex:	name in {name=default} format
    # condex:		name in {cond} format
    # sweepex:		name in {cond|value} format
    # pinex:		name in {PIN|pin_name|net_name} format
    # funcrex:		name in {FUNCTIONAL|ip_name} format
    # colonsepex:	a:b (colon-separated values)
    # vectrex:		pin name is a vector signal
    # vect2rex:		pin name is a vector signal (alternate style)
    # vect3rex:		pin name is a vector signal (alternate style)
    # libdirrex:	pick up library name from .lib
    # vinclrex:		verilog include statement

    varex = re.compile(r'(\{[^ \}\t]+\})')
    defaultex = re.compile(r'\{([^=]+)=([^=\}]+)\}')
    condex = re.compile(r'\{([^\}]+)\}')
    sweepex = re.compile(r'\{([^|\}]+)\|([^|\}]+)\}')
    pinex = re.compile(r'PIN\|([^|]+)\|([^|]+)')
    funcrex = re.compile(r'FUNCTIONAL\|([^|]+)')
    colonsepex = re.compile(r'^([^:]+):([^:]+)$')
    vectrex = re.compile(r'([^\[]+)\[([0-9]+)\]')
    vect2rex = re.compile(r'([^<]+)<([0-9]+)>')
    vect3rex = re.compile(r'([a-zA-Z][^0-9]*)([0-9]+)')
    libdirrex = re.compile(r'.lib[ \t]+(.*)[ \t]+')
    vinclrex = re.compile(r'[ \t]*`include[ \t]+"([^"]+)"')
    brackrex = re.compile(r'(\[[^]]+\])')

    # Information about the DUT
    simfilepath = paths['simulation']
    schempath = paths['schematic']
    testbenchpath = paths['testbench']
    rootpath = paths['root']
    schempins = schemline.upper().split()[1:-1]
    simpins = [None] * len(schempins)

    suffix = os.path.splitext(template)[1]
    functional = []

    # Read ifile into a list
    # Concatenate any continuation lines
    with open(template, 'r') as ifile:
        simtext = ifile.read()

    simlines = simtext.replace('\n+', ' ').splitlines()

    # Make initial pass over contents of template file, looking for conditions
    # with values (e.g., "Vdd|maximum").  These indicate that the condition is
    # not enumerated over testbenches, so collapse simvals accordingly.

    # NOTE:  "simvals" have already been enumerated from the electrical parameter
    # description.  Values can be "minimum" or "maximum", "stepsize", or "steps".
    # The first three are recovered from the list.  The last one is calculated
    # by counting the number of values for the condition.

    # TO DO:  It may be useful to use both values from an enumeration AND keep
    # the enumeration;  e.g., have "{Vdd}" but also "{Vdd|maximum}" in the
    # template.  In that case make the sweeps entry but do not collapse simvals.

    sweeps = []
    for line in simlines:
        sublist = sweepex.findall(line)
        for pattern in sublist:
            condition = pattern[0]
            if pattern == 'FUNCTIONAL':
                # 'FUNCTIONAL' is a reserved name so don't throw an error.
                continue
            try:
                entry = next(
                    item for item in sweeps if item['name'] == condition
                )
            except (StopIteration, KeyError):
                if debug:
                    print('New sweeps entry ' + condition + ' found.')
                    # print('Line = ' + line)
                    # print('Substitution list = ' + str(sublist))
                entry = {'name': condition}
                sweeps.append(entry)

                # Find each entry in simvals with the same condition.
                # Record the minimum, maximum, and step for substitution, at the same
                # time removing that item from the entry.
                lvals = []
                units = ''
                for simval in simvals:
                    try:
                        simrec = next(
                            item for item in simval if item[0] == condition
                        )
                    except StopIteration:
                        print('No condition = ' + condition + ' in record:\n')
                        ptext = str(simval) + '\n'
                        sys.stdout.buffer.write(ptext.encode('utf-8'))
                    else:
                        units = simrec[1]
                        lvals.append(numeric(simrec[2]))
                        simval.remove(simrec)

                # Remove non-unique entries from lvals
                lvals = list(set(lvals))
                if not lvals:
                    print(
                        'CACE gensim error:  No substitution for "'
                        + condition
                        + '"'
                    )
                    continue

                # Now parse lvals for minimum/maximum
                entry['unit'] = units
                minval = min(lvals)
                maxval = max(lvals)
                entry['minimum'] = str(minval)
                entry['maximum'] = str(maxval)
                numvals = len(lvals)
                if numvals > 1:
                    entry['steps'] = str(numvals)
                    entry['stepsize'] = str((maxval - minval) / (numvals - 1))
                else:
                    entry['steps'] = '1'
                    entry['stepsize'] = str(minval)

    # Remove non-unique entries from simvals
    simvals = uniquify(simvals)

    simnum = 0
    testbenches = []
    for simval in simvals:
        # Create the file
        simnum += 1
        testbenchname = filename + '_' + str(simnum)
        simfilename = os.path.join(simfilepath, testbenchname + suffix)
        with open(simfilename, 'w') as ofile:
            for line in simlines:

                # This will be replaced
                subsline = line

                # Find all variables to substitute
                for patmatch in varex.finditer(line):
                    pattern = patmatch.group(1)
                    # If variable is in {x=y} format, it declares a default value
                    # Remove the =y default part and keep it for later if needed.
                    defmatch = defaultex.match(pattern)
                    if defmatch:
                        default = defmatch.group(2)
                        vpattern = '{' + defmatch.group(1) + '}'
                    else:
                        default = []
                        vpattern = pattern

                    repl = []
                    no_repl_ok = False
                    vtype = -1
                    sweeprec = sweepex.match(vpattern)
                    if sweeprec:
                        sweeptype = sweeprec.group(2)
                        condition = sweeprec.group(1)

                        entry = next(
                            item
                            for item in sweeps
                            if item['name'] == condition
                        )
                        if 'unit' in entry:
                            uval = spice_unit_convert(
                                (entry['unit'], entry[sweeptype])
                            )
                            repl = str(uval)
                    else:
                        cond = condex.match(vpattern)
                        if cond:
                            condition = cond.group(1)

                            # Check if the condition contains a pin vector
                            lmatch = vectrex.match(condition)
                            if lmatch:
                                pinidx = int(lmatch.group(2))
                                vcondition = lmatch.group(1)
                                vtype = 0
                            else:
                                lmatch = vect2rex.match(condition)
                                if lmatch:
                                    pinidx = int(lmatch.group(2))
                                    vcondition = lmatch.group(1)
                                    vtype = 1
                                else:
                                    lmatch = vect3rex.match(condition)
                                    if lmatch:
                                        pinidx = int(lmatch.group(2))
                                        vcondition = lmatch.group(1)
                                        vtype = 3

                            try:
                                entry = next(
                                    (
                                        item
                                        for item in simval
                                        if item[0] == condition
                                    )
                                )
                            except (StopIteration, KeyError):
                                # check against known keys that are not conditions
                                if condition == 'N':
                                    repl = str(simnum)
                                elif condition == 'PDK_ROOT':
                                    repl = get_pdk_root()
                                elif condition == 'PDK':
                                    repl = pdkname
                                elif condition == 'steptime':
                                    maxtime = simvals('Tmax')
                                    repl = str(maxtime / 100)
                                elif condition == 'DUT_path':
                                    repl = dutpath + '\n'
                                elif condition == 'include_DUT':
                                    if len(functional) == 0:
                                        repl = '.include ' + dutpath + '\n'
                                    else:
                                        inline_dut(
                                            dutpath,
                                            functional,
                                            rootpath,
                                            ofile,
                                        )
                                        repl = (
                                            '** End of in-line DUT subcircuit'
                                        )
                                elif condition == 'DUT_call':
                                    repl = schemline
                                elif condition == 'DUT_name':
                                    # This verifies pin list of schematic vs. the netlist.
                                    repl = schemline.split()[-1]
                                elif condition == 'filename':
                                    repl = filename
                                elif condition == 'simpath':
                                    repl = simfilepath
                                elif condition == 'random':
                                    repl = str(
                                        int(time.time() * 1000) & 0x7FFFFFFF
                                    )
                                # Stack math operators.  Perform specified math
                                # operation on the last two values and replace.
                                #
                                # Note that ngspice is finicky about space around "=" so
                                # handle this in a way that keeps ngspice happy.
                                elif condition == '+':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                numeric(ltok[-2])
                                                + numeric(ltok[-1])
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition == '-':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                numeric(ltok[-2])
                                                - numeric(ltok[-1])
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition == '*':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                numeric(ltok[-2])
                                                * numeric(ltok[-1])
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition == '/':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                numeric(ltok[-2])
                                                / numeric(ltok[-1])
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition == 'MAX':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                max(
                                                    numeric(ltok[-2]),
                                                    numeric(ltok[-1]),
                                                )
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition == 'MIN':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    if len(ltok) >= 2:
                                        ntok = ltok[:-2]
                                        ntok.append(
                                            str(
                                                min(
                                                    numeric(ltok[-2]),
                                                    numeric(ltok[-1]),
                                                )
                                            )
                                        )
                                        subsline = (
                                            ' '.join(ntok).replace(' = ', '=')
                                            + line[patmatch.end() :]
                                        )
                                    else:
                                        print(
                                            'CACE gensim: substitution error in "'
                                            + subsline
                                            + '"'
                                        )
                                    repl = ''
                                    no_repl_ok = True
                                # 'NEG' acts on only the previous value in the string.
                                elif condition == 'NEG':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    ntok = ltok[:-1]
                                    ntok.append(str(-numeric(ltok[-1])))
                                    subsline = (
                                        ' '.join(ntok).replace(' = ', '=')
                                        + line[patmatch.end() :]
                                    )
                                    repl = ''
                                    no_repl_ok = True
                                # 'INT' also acts on only the previous value in the string.
                                elif condition == 'INT':
                                    smatch = varex.search(subsline)
                                    watchend = smatch.start()
                                    ltok = (
                                        subsline[0:watchend]
                                        .replace('=', ' = ')
                                        .split()
                                    )
                                    ntok = ltok[:-1]
                                    ntok.append(str(int(ltok[-1])))
                                    subsline = (
                                        ' '.join(ntok).replace(' = ', '=')
                                        + line[patmatch.end() :]
                                    )
                                    repl = ''
                                    no_repl_ok = True
                                elif condition.find('PIN|') == 0:
                                    # Parse for {PIN|<pin_name>|<net_name>}
                                    # Replace <pin_name> with index of pin from DUT subcircuit
                                    pinrec = pinex.match(condition)
                                    if pinrec:
                                        pinname = pinrec.group(1).upper()
                                        netname = pinrec.group(2).upper()
                                    else:
                                        print(
                                            'Error: Bad PIN variable '
                                            + condition
                                            + ' in DUT!'
                                        )
                                        continue
                                    try:
                                        idx = schempins.index(pinname)
                                    except ValueError:
                                        repl = netname
                                    else:
                                        repl = '{PIN}'
                                        simpins[idx] = netname
                                elif condition.find('FUNCTIONAL|') == 0:
                                    # Parse for {FUNCTIONAL|<ip_name>}
                                    # Add <ip_name> to "functional" array.
                                    # 'FUNCTIONAL' declarations must come before 'INCLUDE_DUT' or else
                                    # substitution will not be made.  'INCLUDE_DUT' must be used in place
                                    # of 'DUT_path' to get the correct behavior.
                                    funcrec = funcrex.match(condition)
                                    ipname = funcrec.group(1)
                                    functional.append(ipname.upper())
                                    repl = (
                                        '** Using functional view for '
                                        + ipname
                                    )
                                else:
                                    if lmatch:
                                        try:
                                            entry = next(
                                                (
                                                    item
                                                    for item in simval
                                                    if item[0]
                                                    .split('[')[0]
                                                    .split('<')[0]
                                                    == vcondition
                                                )
                                            )
                                        except:
                                            if vtype == 3:
                                                for entry in simval:
                                                    lmatch = vect3rex.match(
                                                        entry[0]
                                                    )
                                                    if lmatch:
                                                        if (
                                                            lmatch.group(1)
                                                            == vcondition
                                                        ):
                                                            vlen = len(
                                                                entry[2]
                                                            )
                                                            uval = entry[2][
                                                                (vlen - 1)
                                                                - pinidx
                                                            ]
                                                            repl = str(uval)
                                                            break
                                            else:
                                                # if no match, subsline remains as-is.
                                                pass
                                        else:
                                            # Handle as vector bit slice (see below)
                                            vlen = len(entry[2])
                                            uval = entry[2][
                                                (vlen - 1) - pinidx
                                            ]
                                            repl = str(uval)
                                    # else if no match, subsline remains as-is.

                            else:
                                if lmatch:
                                    # pull signal at pinidx out of the vector.
                                    # Note: DIGITAL assumes binary value.  May want to
                                    # allow general case of real-valued vectors, which would
                                    # require a spice unit conversion routine without indexing.
                                    vlen = len(entry[2])
                                    uval = entry[2][(vlen - 1) - pinidx]
                                else:
                                    uval = spice_unit_convert(entry[1:])
                                repl = str(uval)

                    if not repl and default:
                        # Use default if no match was found and default was specified
                        repl = default

                    if repl:
                        # Make the variable substitution
                        subsline = subsline.replace(pattern, repl)
                    elif not no_repl_ok:
                        print(
                            'Warning: Variable '
                            + pattern
                            + ' had no substitution'
                        )

                # Check if {PIN} are in line.  If so, order by index and
                # rewrite pins in order
                for i in range(len(simpins)):
                    if '{PIN}' in subsline:
                        if simpins[i]:
                            subsline = subsline.replace('{PIN}', simpins[i], 1)
                        else:
                            print('Error:  simpins is ' + str(simpins) + '\n')
                            print('        subsline is ' + subsline + '\n')
                            print('        i is ' + str(i) + '\n')

                # Check for a verilog include file, and if any is found, copy it
                # to the target simulation directory.  Replace any leading path
                # with the local current working directory '.'.
                vmatch = vinclrex.match(subsline)
                if vmatch:
                    incfile = vmatch.group(1)
                    incroot = os.path.split(incfile)[1]
                    curpath = os.path.split(template)[0]
                    incpath = os.path.abspath(os.path.join(curpath, incfile))
                    shutil.copy(incpath, simfilepath + '/' + incroot)
                    subsline = '   `include "./' + incroot + '"'

                # Check if there is a bracket expression.  This is a simplified
                # and cleaner way of handling the RPN notation, and allows for
                # any expression to be used as long as it evaluates to a
                # number in python.

                for bmatch in brackrex.finditer(subsline):
                    brackexpr = bmatch.group(1)
                    bexpr = brackexpr.strip('[]')
                    try:
                        # Avoid catching simple array indexes like "v[0]".
                        # Other non-expressions will just throw exceptions
                        # when passed to safe_eval().
                        btest = int(bexpr)
                    except:
                        try:
                            brackval = str(safe_eval(bexpr))
                        except:
                            pass
                        else:
                            subsline = subsline.replace(brackexpr, brackval)

                # Write the modified output line (with variable substitutions)
                ofile.write(subsline + '\n')

        # Add information about testbench file and conditions to datasheet,
        # which can be parsed by cace_launch.py.
        testbench = {}

        testbench['filename'] = simfilename
        testbench['conditions'] = simval
        testbenches.append(testbench)

    return testbenches


# -----------------------------------------------------------------------
# cace_gensim
#
# Generate simulation testbenches for a single electrical parameter.
#
# "dataset" is the datasheet characterization dictionary.
# "param" is the dictionary of one parameter in the dataset.
# -----------------------------------------------------------------------


def cace_gensim(dataset, param):

    runtime_options = dataset['runtime_options']
    debug = runtime_options['debug']
    source = runtime_options['netlist_source']
    pdkname = dataset['PDK']

    # Grab values held in 'paths'
    paths = dataset['paths']
    testbenchpath = paths['testbench']
    root_path = paths['root']

    paramname = param['name']

    # Electrical parameter list comes from argument "parameters" if non-NULL.
    # Otherwise, enumerate all electrical parameters.

    if 'status' in param:
        status = param['status']
    else:
        status = 'active'
    if status == 'skip' or status == 'blocked':
        if debug:
            print('Parameter ' + paramname + ' is marked for skipping.')

        return param

    if debug:
        print('Generating simulation files for parameter ' + paramname)

    # Get list of default conditions and generate a list of the condition names
    defcondlist = dataset['default_conditions']
    defcondnames = []
    for defcond in defcondlist:
        defcondnames.append(defcond['name'])

    # Make a copy of the pin list in the datasheet, and expand any vectors.
    pinlist = []
    vectrex = re.compile(r'([^\[]+)\[([0-9]+):([0-9]+)\]')
    vect2rex = re.compile(r'([^<]+)\<([0-9]+):([0-9]+)\>')
    vect3rex = re.compile(r'([^0-9]+)([0-9]+):([0-9]+)')

    for pinrec in dataset['pins']:
        vmatch = vectrex.match(pinrec['name'])
        if vmatch:
            pinname = vmatch.group(1)
            pinmin = vmatch.group(2)
            pinmax = vmatch.group(3)
            if int(pinmin) > int(pinmax):
                pinmin = vmatch.group(3)
                pinmax = vmatch.group(2)
            for i in range(int(pinmin), int(pinmax) + 1):
                newpinrec = pinrec.copy()
                pinlist.append(newpinrec)
                newpinrec['name'] = pinname + '[' + str(i) + ']'
        else:
            vmatch = vect2rex.match(pinrec['name'])
            if vmatch:
                pinname = vmatch.group(1)
                pinmin = vmatch.group(2)
                pinmax = vmatch.group(3)
                if int(pinmin) > int(pinmax):
                    pinmin = vmatch.group(3)
                    pinmax = vmatch.group(2)
                for i in range(int(pinmin), int(pinmax) + 1):
                    newpinrec = pinrec.copy()
                    pinlist.append(newpinrec)
                    newpinrec['name'] = pinname + '<' + str(i) + '>'
            else:
                vmatch = vect3rex.match(pinrec['name'])
                if vmatch:
                    pinname = vmatch.group(1)
                    pinmin = vmatch.group(2)
                    pinmax = vmatch.group(3)
                    if int(pinmin) > int(pinmax):
                        pinmin = vmatch.group(3)
                        pinmax = vmatch.group(2)
                    for i in range(int(pinmin), int(pinmax) + 1):
                        newpinrec = pinrec.copy()
                        pinlist.append(newpinrec)
                        newpinrec['name'] = pinname + str(i)
                else:
                    pinlist.append(pinrec)

    # Find DUT netlist file and capture the subcircuit call line
    pname = dataset['name']

    if source != 'schematic':
        if source == 'layout':
            layoutpath = os.path.join(paths['netlist'], 'layout')
        elif source == 'pex':
            layoutpath = os.path.join(paths['netlist'], 'pex')
        else:
            layoutpath = os.path.join(paths['netlist'], 'rcx')
        layoutname = pname + '.spice'
        dutpath = os.path.join(root_path, layoutpath, layoutname)

    if source == 'schematic' or not os.path.isfile(dutpath):
        if source == 'schematic':
            schempath = os.path.join(paths['netlist'], 'schematic')
            schemname = pname + '.spice'
            dutpath = os.path.join(root_path, schempath, schemname)

    if not os.path.isfile(dutpath):
        if 'verilog' not in paths:
            print(
                'No SPICE netlist exists at '
                + dutpath
                + ' and no verilog path exists.'
            )
            print('This is an error condition.')
            return param

    # Get the DUT definition from the SPICE netlist.  Note that this
    # only applies to parameters being simulated with SPICE, so only
    # flag an error when applicable.

    try:
        schemline = construct_dut_from_path(pname, dutpath, pinlist)
    except SyntaxError:
        schemline = ''

    # Dictionary "simulate" key "template" is the name of the template
    # file to use as source.  The output file is the name (key "name")
    # of the electrical parameter followed by an index suffix uniquely
    # identifying it.
    #
    # There is no check here for duplicate electrical parameter names,
    # which is not allowed.
    #
    # In the following code:
    #   "condnames" is the full list of conditions found in the template
    # 		testbench netlists that will need substitution, looking
    # 		at all testbenches that are required by the parameter.
    #   "pcondnames" is the list of conditions found in the datasheet
    # 		for the parameter.
    # 	"defcondnames" is a list of conditions found in the default set.
    # 	"lcondnames" is the list of parameter conditions + defaults that
    # 		should match the "condnames" list.

    # Get the simulation dictionary and find the tool and template
    # NOTE:  The "simulate" value could be a list in the case of, for
    # example, co-simulation.

    simulatedict = param['simulate']
    if isinstance(simulatedict, list):
        tools = []
        testbenches = []
        for simulation in simulatedict:
            tools.append(simulation['tool'])
            testbenches.append(simulation['template'])
    else:
        tools = [simulatedict['tool']]
        testbenches = [simulatedict['template']]

    # Get the list of parameters that get substituted in the template
    condnames = []
    for testbench in testbenches:
        newnames = get_condition_names_used(testbenchpath, testbench)
        if not newnames:
            print('Error:  No conditions for testbench ' + testbench)
        else:
            # Convert the dictionary of names into a list
            for name in newnames:
                if name not in condnames:
                    condnames.append(name)

    # Get the list of parameters specific to the electrical parameter
    # definition
    pcondlist = param['conditions']
    pcondnames = []
    for pcond in pcondlist:
        pcondnames.append(pcond['name'])

    # Add any missing unit types that exist in the default conditions
    # but have been made implicit in the parameter's condition list
    # need to be added so that units are handled correctly everywhere.

    newpcondlist = []
    for pcond in pcondlist:
        newpcond = pcond
        if 'unit' not in pcondlist:
            try:
                defcond = next(
                    item
                    for item in defcondlist
                    if item['name'] == pcond['name']
                )
            except:
                pass
            else:
                if 'unit' in defcond:
                    newpcond = pcond.copy()
                    newpcond['unit'] = defcond['unit']
        newpcondlist.append(newpcond)
    pcondlist = newpcondlist

    # For each vector type in pcondlist and defcondlist, reduce to
    # just the name portion of the vector and the opening delimiter.

    vectrex = re.compile(r'([^\[]+)\[([0-9:]+)\]')  # name[number]

    newdefcondnames = []
    for defcondname in defcondnames:
        vmatch = vectrex.match(defcondname)
        if vmatch:
            newdefcondnames.append(vmatch.group(1) + '[')
        else:
            newdefcondnames.append(defcondname)

    defcondnames = newdefcondnames

    newpcondnames = []
    for pcondname in pcondnames:
        vmatch = vectrex.match(pcondname)
        if vmatch:
            newpcondnames.append(vmatch.group(1) + '[')
        else:
            newpcondnames.append(pcondname)

    pcondnames = newpcondnames

    # Get the full list of conditions for which the parameter will be
    # simulated by merging together both the conditions defined for
    # the electrical parameter and the fallback of the default conditions,
    # only keeping those conditions that get substituted.
    # Run a sanity check:  All names in "condnames" should be found in
    # either the parameter list or the defaults list except for specific
    # items that have reserved names, and the pins which have a fixed
    # format.

    reserved = [
        'filename',
        'simpath',
        'DUT_name',
        'N',
        'DUT_path',
        'PDK_ROOT',
        'PDK',
        'include_DUT',
        'DUT_call',
        'steptime',
        'random',
        '+',
        '-',
        '*',
        '/',
        'MIN',
        'NEG',
        'INT',
        'FUNCTIONAL',
    ]

    lcondlist = []
    for cond in condnames:
        if cond[-1] == '[':
            if cond in pcondnames:
                lcondlist.extend(
                    list(
                        item
                        for item in pcondlist
                        if item['name'].startswith(cond)
                    )
                )
            elif cond in defcondnames:
                lcondlist.extend(
                    list(
                        item
                        for item in defcondlist
                        if item['name'].startswith(cond)
                    )
                )
            elif not cond.startswith('PIN|') and not '=' in cond:
                if cond not in reserved:
                    print(
                        'Error:  Unknown/unhandled condition name "'
                        + cond
                        + '"'
                    )
        else:
            if cond in pcondnames:
                lcondlist.extend(
                    list(item for item in pcondlist if item['name'] == cond)
                )
            elif cond in defcondnames:
                lcondlist.extend(
                    list(item for item in defcondlist if item['name'] == cond)
                )
            elif not cond.startswith('PIN|') and not '=' in cond:
                if cond not in reserved:
                    print(
                        'Error:  Unknown/unhandled condition name "'
                        + cond
                        + '"'
                    )

    # Get the list of parameters that are collated (simulated together
    # and results passed as a list to the measurement).  These go first
    # in the list so that their testbenches are all grouped together:
    collnames = []
    if 'collate' in simulatedict:
        if isinstance(simulatedict['collate'], list):
            collnames = simulatedict['collate']
        else:
            collnames = [simulatedict['collate']]

        # Now reorder lcondlist so that conditions listed in 'collate' are at
        # the beginning of the list.

        collnames.reverse()
        goodcollnames = collnames.copy()
        for collname in collnames:
            try:
                collidx = next(
                    (
                        index
                        for (index, d) in enumerate(lcondlist)
                        if d['name'] == collname
                    )
                )
            except:
                print(
                    'Error:  Request to collate '
                    + collname
                    + ' which is not a condition of parameter '
                    + paramname
                )
                goodcollnames.remove(collname)
            else:
                lcondlist.insert(0, lcondlist.pop(collidx))
        # It would presumably be a serious error if a wrong name is in the
        # 'collate' list, but try to track the good entries so the count of
        # testbenches to collate doesn't get messed up.
        collnames = goodcollnames

    # Now revise the list of condition names to contain only the 'name'
    # records from the condition dictionaries.
    lcondnames = []
    for lcond in lcondlist:
        lcondnames.append(lcond['name'])

    # Find the maximum simulation time required by this parameter
    # Simulations are ordered so that "risetime" and "falltime" simulations
    # on a pin will set the simulation time of any simulation of any other
    # electrical parameter on that same pin.

    if 'Tmax' in condnames:
        if 'Tmax' not in lcondnames:
            maxtime = findmaxtime(param, lcondlist)
            print('maxtime is ' + str(maxtime))
            maxtimedict = {}
            maxtimedict['name'] = 'Tmax'
            maxtimedict['unit'] = 's'
            maxtimedict['maximum'] = maxtime
            lcondlist.append(maxtimedict)

    if lcondlist == []:
        print('Error:  Empty condition list for electrical parameter.')
        if debug:
            print('conditions in testbench: ' + ' '.join(condnames))
            print('conditions in parameter: ' + ' '.join(pcondnames))
        return param

    # Find the length of each generator
    cgenlen = []
    for cond in lcondlist:
        cgenlen.append(len(list(condition_gen(cond))))

    if debug:
        print('Full condition list (lcondlist) is:')
        print('   ' + ' '.join(lcondnames))

    # The lengths of all generators multiplied together is the number of
    # simulations to be run
    numsims = reduce(lambda x, y: x * y, cgenlen)
    rlen = [x for x in cgenlen]

    # The portion of cgenlen that corresponds to collated results is used
    # to find the number of simulations that are grouped together for
    # collation after simulaton.

    if collnames:
        numcolvars = len(collnames)
        numcollated = reduce(lambda x, y: x * y, cgenlen[0:numcolvars])
        # Record the group size
        simulatedict['group_size'] = numcollated

        # Diagnostic
        if debug:
            print('Collated variables = ' + ' '.join(collnames))
            print('Number of grouped testbenches = ' + str(numcollated))
    else:
        if debug:
            print('No collation in parameter ' + param['name'])

    # This code repeats each condition as necessary such that the final list
    # (transposed) is a complete set of unique condition combinations.
    cgensim = []
    for i in range(len(rlen)):
        mpre = reduce(lambda x, y: x * y, rlen[0:i], 1)
        mpost = reduce(lambda x, y: x * y, rlen[i + 1 :], 1)
        clist = list(condition_gen(lcondlist[i]))
        duplist = [
            item
            for item in list(condition_gen(lcondlist[i]))
            for j in range(mpre)
        ]
        cgensim.append(duplist * mpost)

    # Transpose this list
    simvals = list(map(list, zip(*cgensim)))

    # Make parameter substitutions into each template file and generate
    # an output simulatable file.  Record the names of the testbenches
    # created.

    for testbench, tool in zip(testbenches, tools):
        template = os.path.join(testbenchpath, testbench)
        if os.path.isfile(template):
            param['testbenches'] = substitute(
                paramname,
                paths,
                tool,
                template,
                dutpath,
                simvals,
                schemline,
                pdkname,
                debug,
            )
        else:
            print('Error:  No testbench file ' + template + '.')

    return param


# ------------------------------------------------------------------------
