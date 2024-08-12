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
import datetime
import subprocess

from .cace_regenerate import printwarn, get_pdk_root
from .common import (
    xschem_generate_svg,
    magic_generate_svg,
    klayout_generate_png,
)
from .spiceunits import spice_unit_convert, spice_unit_unconvert
from ..parameter.parameter import ResultType
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


def generate_documentation(datasheet):
    """
    Generate documentation

    Generates a Markdown file for the design under the documentation path
    Another Markdown file is generated for the results based on the netlist source
    Exports the schematic and symbol as svg, and saves the layout as png
    """

    doc_file = os.path.join(
        datasheet['paths']['root'],
        datasheet['paths']['documentation'],
        f'{datasheet["name"]}.md',
    )

    with open(doc_file, 'w') as ofile:
        ofile.write(f'# {datasheet["name"]}\n\n')

        if 'description' in datasheet:
            ofile.write(f'- Description: {datasheet["description"]}\n')

        if 'commit' in datasheet:
            ofile.write(f'- Commit: {datasheet["commit"]}\n')

        if 'PDK' in datasheet:
            ofile.write(f'- PDK: {datasheet["PDK"]}\n')

        if 'authorship' in datasheet:

            ofile.write(f'\n## Authorship\n\n')

            known_fields = {
                'designer': 'Designer',
                'company': 'Company',
                'institution': 'Institution',
                'email': 'Contact',
                'creation_date': 'Created',
                'modification_date': 'Last modified',
                'license': 'License',
            }

            for entry in datasheet['authorship']:
                if entry in known_fields:
                    ofile.write(
                        f'- {known_fields[entry]}: {datasheet["authorship"][entry]}\n'
                    )
                else:
                    warn(f'Unknown entry in authorship: {entry}')

        if 'pins' in datasheet:

            ofile.write(f'\n## Pins\n\n')

            known_fields = {
                'display': 'Display',
                'description': 'Description',
                'type': 'Type',
                'direction': 'Direction',
                'Vmin': 'Vmin',
                'Vmax': 'Vmax',
                'note': 'Note',
            }

            for pin in datasheet['pins']:
                ofile.write(f'- {pin}\n')

                for entry in datasheet['pins'][pin]:
                    if entry in known_fields:
                        ofile.write(
                            f'  + {known_fields[entry]}: {datasheet["pins"][pin][entry]}\n'
                        )
                    else:
                        warn(f'Unknown entry in pins: {entry}')

        if 'default_conditions' in datasheet:

            ofile.write(f'\n## Default Conditions\n\n')

            known_fields = {
                'display': 'Display',
                'description': 'Description',
                'unit': 'Unit',
                'direction': 'Direction',
                'minimum': 'Minimum',
                'typical': 'Typical',
                'maximum': 'Maximum',
                'enumerate': 'Enumerate',
                'step': 'Step',
                'stepsize': 'Stepsize',
                'note': 'Note',
            }

            for default_condition in datasheet['default_conditions']:
                ofile.write(f'- {default_condition}\n')

                for entry in datasheet['default_conditions'][
                    default_condition
                ]:
                    if entry in known_fields:
                        ofile.write(
                            f'  + {known_fields[entry]}: {datasheet["default_conditions"][default_condition][entry]}\n'
                        )
                    else:
                        warn(f'Unknown entry in default_conditions: {entry}')

        # Add symbol image
        ofile.write(f'\n## Symbol\n\n')
        ofile.write(
            f'![Symbol of {datasheet["name"]}]({datasheet["name"]}_symbol.svg)\n'
        )

        # Add schematic image
        ofile.write(f'\n## Schematic\n\n')
        ofile.write(
            f'![Schematic of {datasheet["name"]}]({datasheet["name"]}_schematic.svg)\n'
        )

        # Add layout images
        ofile.write(f'\n## Layout\n\n')
        ofile.write(
            f'![Layout of {datasheet["name"]} with white background]({datasheet["name"]}_w.png)\n'
        )
        ofile.write(
            f'![Layout of {datasheet["name"]} with black background]({datasheet["name"]}_b.png)\n'
        )

    # Generate xschem symbol svg
    svgpath = os.path.join(
        datasheet['paths']['root'],
        datasheet['paths']['documentation'],
        f'{datasheet["name"]}_symbol.svg',
    )

    symname = datasheet['name'] + '.sym'
    sympath = os.path.join(
        datasheet['paths']['root'], datasheet['paths']['schematic'], symname
    )

    if xschem_generate_svg(sympath, svgpath):
        err(f'Error generating SVG for symbol.')

    # Generate xschem schematic svg
    svgpath = os.path.join(
        datasheet['paths']['root'],
        datasheet['paths']['documentation'],
        f'{datasheet["name"]}_schematic.svg',
    )

    schemname = datasheet['name'] + '.sch'
    schempath = os.path.join(
        datasheet['paths']['root'], datasheet['paths']['schematic'], schemname
    )

    if xschem_generate_svg(schempath, svgpath):
        err(f'Error generating SVG for schematic.')

    # Generate KLayout image

    svgpath = os.path.join(
        datasheet['paths']['root'],
        datasheet['paths']['documentation'],
        f'{datasheet["name"]}_klayout.svg',
    )

    # Use GDSII
    if 'layout' in datasheet['paths']:
        layout_directory = datasheet['paths']['layout']
        layoutname = datasheet['name'] + '.gds'
        layout_path = os.path.join(layout_directory, layoutname)
        # Search for compressed layout
        if not os.path.exists(layout_path):
            layoutname = datasheet['name'] + '.gds.gz'
            layout_path = os.path.join(layout_directory, layoutname)
    else:
        err('No "layout" specified in datasheet paths.')

    klayout_generate_png(
        layout_path,
        os.path.join(
            datasheet['paths']['root'], datasheet['paths']['documentation']
        ),
    )

    # Generate magic image

    svgpath = os.path.join(
        datasheet['paths']['root'],
        datasheet['paths']['documentation'],
        f'{datasheet["name"]}_magic.svg',
    )

    # Prefer magic layout
    if 'magic' in datasheet['paths']:
        magic_directory = datasheet['paths']['magic']
        magicname = datasheet['name'] + '.mag'
        layout_path = os.path.join(magic_directory, magicname)
        is_mag = True
    # Else use GDSII
    elif 'layout' in datasheet['paths']:
        layout_directory = datasheet['paths']['layout']
        layoutname = datasheet['name'] + '.gds'
        layout_path = os.path.join(layout_directory, layoutname)
        # Search for compressed layout
        if not os.path.exists(layout_path):
            layoutname = datasheet['name'] + '.gds.gz'
            layout_path = os.path.join(layout_directory, layoutname)
    else:
        err('Neither "magic" nor "layout" specified in datasheet paths.')

    # magic_generate_svg(layout_path, svgpath)


def markdown_summary(datasheet, runtime_options, results):
    """
    Returns a brief summary of the datasheet and its parameters
    The summary is formatted in Markdown and can either be printed
    directly or via rich to get a nice formatting
    """

    result = ''

    # Table spacings
    sp = [20, 20, 10, 12, 10, 12, 10, 12, 8]

    result += f'\n# CACE Summary for {datasheet["name"]}\n\n'

    result += f'**netlist source**: {runtime_options["netlist_source"]}\n\n'

    # Print the table headings
    result += ''.join(
        [
            f'| {"Parameter": ^{sp[0]}} ',
            f'| {"Tool": ^{sp[1]}} ',
            f'| {"Min Limit": ^{sp[2]}} ',
            f'| {"Min Value": ^{sp[3]}} ',
            f'| {"Typ Target": ^{sp[4]}} ',
            f'| {"Typ Value": ^{sp[5]}} ',
            f'| {"Max Limit": ^{sp[6]}} ',
            f'| {"Max Value": ^{sp[7]}} ',
            f'| {"Status": ^{sp[8]}} |\n',
        ]
    )
    # Print the separators
    result += ''.join(
        [
            f'| :{"-"*(sp[0]-1)} ',
            f'| :{"-"*(sp[1]-1)} ',
            f'| {"-"*(sp[2]-1)}: ',
            f'| {"-"*(sp[3]-1)}: ',
            f'| {"-"*(sp[4]-1)}: ',
            f'| {"-"*(sp[5]-1)}: ',
            f'| {"-"*(sp[6]-1)}: ',
            f'| {"-"*(sp[7]-1)}: ',
            f'| :{"-"*(sp[8]-2)}: |\n',
        ]
    )

    for param in datasheet['parameters'].values():

        # Get the unit
        unit = param['unit'] if 'unit' in param else None

        limits = {'minimum': '', 'typical': '', 'maximum': ''}

        # Get the limits from the spec
        if 'spec' in param:
            for spec_type in ['minimum', 'typical', 'maximum']:
                if spec_type in param['spec']:
                    limits[spec_type] = param['spec'][spec_type]['value']

        values = {'minimum': '', 'typical': '', 'maximum': ''}

        # Must be skipped, TODO set somewhere else
        status = ResultType.SKIPPED

        # Get the results
        for result_type in ['minimum', 'typical', 'maximum']:
            if param['name'] in results:
                if result_type in results[param['name']]:
                    if results[param['name']][result_type]:
                        if 'value' in results[param['name']][result_type]:
                            values[result_type] = results[param['name']][
                                result_type
                            ]['value']

                    # Get the status message
                    status = results[param['name']]['type']

        # Get the tool
        tool = param['tool']

        # Get the name of the tool
        if isinstance(tool, str):
            toolname = tool
        else:
            toolname = list(tool.keys())[0]

        # Don't print any unit if empty or "any"
        no_unit = ['', 'any', None]

        # Print the row for the parameter
        parameter_str = param['display']
        tool_str = toolname
        min_limit_str = (
            f'{limits["minimum"]} {unit}'
            if unit and not limits['minimum'] in no_unit
            else limits['minimum']
        )
        min_value_str = (
            f'{spice_unit_unconvert((str(unit), values["minimum"])):.3f} {unit}'
            if unit and not values['minimum'] in no_unit
            else values['minimum']
        )
        typ_limit_str = (
            f'{limits["typical"]} {unit}'
            if unit and not limits['typical'] in no_unit
            else limits['typical']
        )
        typ_value_str = (
            f'{spice_unit_unconvert((str(unit), values["typical"])):.3f} {unit}'
            if unit and not values['typical'] in no_unit
            else values['typical']
        )
        max_limit_str = (
            f'{limits["maximum"]} {unit}'
            if unit and not limits['maximum'] in no_unit
            else limits['maximum']
        )
        max_value_str = (
            f'{spice_unit_unconvert((str(unit), values["maximum"])):.3f} {unit}'
            if unit and not values['maximum'] in no_unit
            else values['maximum']
        )
        status_str = status

        # Workaround for rich: replace empty cells with one invisible space character
        inv_char = '\u200B'
        result += ''.join(
            [
                f'| {parameter_str if parameter_str != "" and parameter_str != None else inv_char: <{sp[0]}} ',
                f'| {tool_str if tool_str != "" and tool_str != None else inv_char: <{sp[1]}} ',
                f'| {min_limit_str if min_limit_str != "" and min_limit_str != None else inv_char: >{sp[2]}} ',
                f'| {min_value_str if min_value_str != "" and min_value_str != None else inv_char: >{sp[3]}} ',
                f'| {typ_limit_str if typ_limit_str != "" and typ_limit_str != None else inv_char: >{sp[4]}} ',
                f'| {typ_value_str if typ_value_str != "" and typ_value_str != None else inv_char: >{sp[5]}} ',
                f'| {max_limit_str if max_limit_str != "" and max_limit_str != None else inv_char: >{sp[6]}} ',
                f'| {max_value_str if max_value_str != "" and max_value_str != None else inv_char: >{sp[7]}} ',
                f'| {status_str if status_str != "" and status_str != None else inv_char: ^{sp[8]-1}} |\n',
            ]
        )

    result += '\n'
    return result


def uchar_sub(string):
    """
    Convert from unicode to text format
    """

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

    idx = 0
    for item in ucode_list:
        if item in string:
            string = string.replace(item, text_list[idx])
        idx = idx + 1

    return string
