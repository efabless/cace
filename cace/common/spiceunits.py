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

"""spice_units.py: Converts tuple of (unit, value) into standard unit numeric value."""

import re

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

# set of metric prefixes and the value needed to multiply by to
# get the "standard" unit for SPICE.  Only standard units will
# be written into the SPICE file, for reasons of universal
# compatibility.

prefixtypes = {
    'T': 1e12,
    'tera': 1e12,
    'G': 1e9,
    'giga': 1e9,
    'M': 1e6,
    'mega': 1e6,
    'MEG': 1e6,
    'meg': 1e6,
    'K': 1e3,
    'kilo': 1e3,
    'k': 1e3,
    'D': 1e1,
    'deca': 1e1,
    'd': 1e-1,
    'deci': 1e-1,
    'c': 1e-2,
    'centi': 1e-2,
    '%': 1e-2,
    'm': 1e-3,
    'milli': 1e-3,
    'u': 1e-6,
    'micro': 1e-6,
    '\u00b5': 1e-6,
    'ppm': 1e-6,
    'n': 1e-9,
    'nano': 1e-9,
    'ppb': 1e-9,
    'p': 1e-12,
    'pico': 1e-12,
    'ppt': 1e-12,
    'f': 1e-15,
    'femto': 1e-15,
    'a': 1e-18,
    'atto': 1e-15,
}

# set of known unit types, including some with suffixes, along with a
# keyword that can be used to limit the search if an expected type for
# the value is known.  Keys are used in regular expressions, and so
# may use any regular expression syntax.

unittypes = {
    '[Ff]': 'capacitance',
    '[Ff]arad[s]*': 'capacitance',
    '\u03a9': 'resistance',
    '[Oo]hm[s]*': 'resistance',
    '[Vv]': 'voltage',
    '[Vv]olt[s]*': 'voltage',
    '[Aa]': 'current',
    '[Aa]mp[s]*': 'current',
    '[Aa]mpere[s]*': 'current',
    '[Ss]': 'time',
    '[Ss]econd[s]*': 'time',
    '[Hh]': 'inductance',
    '[Hh]enry[s]*': 'inductance',
    '[Hh]enries': 'inductance',
    '[Hh]z': 'frequency',
    '[Hh]ertz': 'frequency',
    '[Mm]': 'distance',
    '[Mm]eter[s]*': 'distance',
    '[\u00b0]*[Cc]': 'temperature',
    '[\u00b0]*[Cc]elsius': 'temperature',
    '[\u00b0]*[Kk]': 'temperature',
    '[\u00b0]*[Kk]elvin': 'temperature',
    '[Ww]': 'power',
    '[Ww]att[s]*': 'power',
    '[Vv]-rms': 'noise',
    '[Vv]olt[s]*-rms': 'noise',
    "'[bohd]": 'digital',
    '': 'none',
}

# Convert string to either integer or float, with priority on integer
# If argument is not a string, just return the argument.


def numeric(s):
    if isinstance(s, str):
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                err(f'CACE gensim error: Value "{s}" is not numeric!')
                return 0
    else:
        return s


# Define how to convert SI units to spice values
#
# NOTE: spice_unit_unconvert can act on a tuple of (units, value) where
# value is either a single value or a list of values.  spice_unit_convert
# only acts on a tuple with a single value.  This is because the only large
# vectors are produced by ngspice, and these values need unconverting back
# into the units specified by the datasheet.  Values being converted to
# ngspice units are from the datasheet and are only computed a few at a
# time, so handling vectors is not particularly efficient.


def spice_unit_convert(valuet, restrict=[]):
    """Convert SI units into spice values"""
    # valuet is a tuple of (unit, value), where "value" is numeric
    # and "unit" is a string.  "restrict" may be used to require that
    # the value be of a specific class like "time" or "resistance".

    # Recursive handling of '/' and multiplicatioon dot in expressions
    if '/' in valuet[0]:
        parts = valuet[0].split('/', 1)
        result = numeric(spice_unit_convert([parts[0], valuet[1]], restrict))
        result /= numeric(spice_unit_convert([parts[1], '1.0'], restrict))
        return str(result)

    if '\u22c5' in valuet[0]:  	# multiplication dot
        parts = valuet[0].split('\u22c5')
        result = numeric(spice_unit_convert([parts[0], valuet[1]], restrict))
        result *= numeric(spice_unit_convert([parts[1], '1.0'], restrict))
        return str(result)

    if '\u00b2' in valuet[0]:  	# squared
        part = valuet[0].split('\u00b2')[0]
        result = numeric(spice_unit_convert([part, valuet[1]], restrict))
        result *= numeric(spice_unit_convert([part, '1.0'], restrict))
        return str(result)

    if valuet[0] == '':  # null case, no units
        return valuet[1]

    for unitrec in unittypes:  	# case of no prefix
        if re.match('^' + unitrec + '$', valuet[0]):
            if restrict:
                if unittypes[unitrec] == restrict.lower():
                    return valuet[1]
            else:
                return valuet[1]

    for prerec in prefixtypes:
        for unitrec in unittypes:
            if re.match('^' + prerec + unitrec + '$', valuet[0]):
                if restrict:
                    if unittypes[unitrec] == restrict.lower():
                        newvalue = numeric(valuet[1]) * prefixtypes[prerec]
                        return str(newvalue)
                else:
                    newvalue = numeric(valuet[1]) * prefixtypes[prerec]
                    return str(newvalue)

    # Check for "%", which can apply to anything.
    if valuet[0][0] == '%':
        newvalue = numeric(valuet[1]) * 0.01
        return str(newvalue)

    if restrict:
        raise ValueError(
            'units ' + valuet[0] + ' cannot be parsed as ' + restrict.lower()
        )
    else:
        # raise ValueError('units ' + valuet[0] + ' cannot be parsed')
        # (Assume value is not in SI units and will be passed back as-is)
        return valuet[1]


# Define how to convert spice values back into SI units


def spice_unit_unconvert(valuet, restrict=[]):
    """Convert spice values back into SI units"""
    # valuet is a tuple of (unit, value), where "value" is numeric
    # and "unit" is a string.  "restrict" may be used to require that
    # the value be of a specific class like "time" or "resistance".

    # Recursive handling of '/' and multiplicatioon dot in expressions
    if '/' in valuet[0]:
        parts = valuet[0].split('/', 1)
        result = spice_unit_unconvert([parts[0], valuet[1]], restrict)
        if isinstance(result, list):
            result = list(
                item / spice_unit_unconvert([parts[1], 1.0], restrict)
                for item in result
            )
        else:
            result /= spice_unit_unconvert([parts[1], 1.0], restrict)
        return result

    if '\u22c5' in valuet[0]:  	# multiplication dot
        parts = valuet[0].split('\u22c5')
        result = spice_unit_unconvert([parts[0], valuet[1]], restrict)
        if isinstance(result, list):
            result = list(
                item * spice_unit_unconvert([parts[1], 1.0], restrict)
                for item in result
            )
        else:
            result *= spice_unit_unconvert([parts[1], 1.0], restrict)
        return result

    if '\u00b2' in valuet[0]:  	# squared
        part = valuet[0].split('\u00b2')[0]
        result = spice_unit_unconvert([part, valuet[1]], restrict)
        if isinstance(result, list):
            result = list(
                item * spice_unit_unconvert([part, 1.0], restrict)
                for item in result
            )
        else:
            result *= spice_unit_unconvert([part, 1.0], restrict)
        return result

    if valuet[0] == '':  # null case, no units
        return valuet[1]

    for unitrec in unittypes:  	# case of no prefix
        if re.match('^' + unitrec + '$', valuet[0]):
            if restrict:
                if unittypes[unitrec] == restrict.lower():
                    return valuet[1]
            else:
                return valuet[1]

    for prerec in prefixtypes:
        for unitrec in unittypes:
            if re.match('^' + prerec + unitrec + '$', valuet[0]):
                if restrict:
                    if unittypes[unitrec] == restrict.lower():
                        if isinstance(valuet[1], list):
                            return list(
                                item / prefixtypes[prerec]
                                for item in valuet[1]
                            )
                        else:
                            return valuet[1] / prefixtypes[prerec]
                else:
                    if isinstance(valuet[1], list):
                        return list(
                            item / prefixtypes[prerec] for item in valuet[1]
                        )
                    else:
                        return valuet[1] / prefixtypes[prerec]

    # Check for "%", which can apply to anything.
    if valuet[0][0] == '%':
        if isinstance(valuet[1], list):
            return list(item * 100 for item in valuet[1])
        else:
            return valuet[1] * 100

    if restrict:
        raise ValueError(
            'units ' + valuet[0] + ' cannot be parsed as ' + restrict.lower()
        )
    else:
        # raise ValueError('units ' + valuet[0] + ' cannot be parsed')
        # (Assume value is not in SI units and will be passed back as-is)
        return valuet[1]
