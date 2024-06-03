#!/usr/bin/env python3
#
# --------------------------------------------------------
# CACE file writer
#
# This script takes a dictionary from CACE and writes
# a CACE 4.0 format text file.
#
# Input:  datasheet dictionary
# Output: file in CACE 4.0 format
#
# --------------------------------------------------------
# Written by Tim Edwards
# Efabless corporation
# November 22, 2023
# --------------------------------------------------------

import io
import re
import os
import sys
import json
import datetime
import subprocess

from .cace_regenerate import printwarn, get_pdk_root

# ---------------------------------------------------------------
# generate_svg
#
# Generate an SVG drawing of the schematic symbol using xschem
#
# Return the name of the SVG file if the drawing was generated,
# None if not.
# ---------------------------------------------------------------


def generate_svg(datasheet):

    debug = False
    if 'runtime_options' in datasheet:
        runtime_options = datasheet['runtime_options']
        if 'debug' in runtime_options:
            debug = runtime_options['debug']

    paths = datasheet['paths']
    if 'documentation' in paths:
        docdir = paths['documentation']
    else:
        docdir = '.'

    if 'schematic' in paths:
        schempath = paths['schematic']
        symname = datasheet['name'] + '.sym'
        sympath = os.path.join(schempath, symname)
        svgname = datasheet['name'] + '_sym.svg'
        svgpath = os.path.join(docdir, svgname)
        if os.path.isfile(sympath):

            if 'PDK_ROOT' in datasheet:
                pdk_root = datasheet['PDK_ROOT']
            else:
                pdk_root = get_pdk_root()

            if 'PDK' in datasheet:
                pdk = datasheet['PDK']
            else:
                pdk = get_pdk(None)

            newenv = os.environ.copy()
            if pdk_root and 'PDK_ROOT' not in newenv:
                newenv['PDK_ROOT'] = pdk_root
            if pdk and 'PDK' not in newenv:
                newenv['PDK'] = pdk

            xschemargs = [
                'xschem',
                '-b',
                '-x',
                '-q',
                '--svg',
                '--plotfile',
                svgpath,
            ]

            # Use the PDK xschemrc file for xschem startup
            xschemrcfile = os.path.join(
                pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
            )
            if os.path.isfile(xschemrcfile):
                xschemargs.extend(['--rcfile', xschemrcfile])

            xschemargs.append(sympath)

            if debug:
                print('Generating SVG of schematic symbol.')
                print('Running: ' + ' '.join(xschemargs))

            xproc = subprocess.Popen(
                xschemargs,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            xout = xproc.communicate()[0]
            if xproc.returncode != 0:
                for line in xout.splitlines():
                    print(line.decode('utf-8'))

                print(
                    'Xschem process returned error code '
                    + str(xproc.returncode)
                    + '\n'
                )
            else:
                printwarn(xout)
                return svgname

    return None


# ---------------------------------------------------------------
# cace_generate_html
#
# Convert the characterization data into a formatted datasheet
# in HTML format
#
# Filename is set to <project_name>.html and placed in the
# documents directory
#
# If filename is None, then filename is automatically generated
# from the project name with extension ".html" and placed in
# the documentation directory specified in 'paths'.
# ---------------------------------------------------------------


def cace_generate_html(datasheet, filename=None, debug=False):

    paths = datasheet['paths']
    if 'root' in paths:
        rootdir = paths['root']
    else:
        rootdir = '.'

    if 'documentation' in paths:
        docdir = paths['documentation']
    else:
        docdir = rootdir

    docname = datasheet['name'] + '.html'

    if not os.path.isdir(docdir):
        os.makedirs(docdir)

    if filename:
        ofilename = filename
        if os.path.splitext(ofilename)[1] == '':
            ofilename += '.html'
    else:
        ofilename = os.path.join(docdir, docname)

    svgname = generate_svg(datasheet)

    with open(ofilename, 'w') as ofile:
        ofile.write('<HTML>\n')
        ofile.write('<BODY>\n')

        if 'cace_format' in datasheet:
            vformat = datasheet['cace_format']
        else:
            vformat = ''
        ofile.write(' '.join(['<H1> CACE', vformat, 'datasheet </H1>\n']))

        ofile.write('\n\n<HR>\n\n')
        ofile.write('<FONT size=+1><B>' + datasheet['name'] + '</B></FONT>\n')
        ofile.write('\n\n<HR>\n\n')

        if 'description' in datasheet:
            ofile.write(
                ' '.join(['<I>', datasheet['description'], '</I><BR><BR>\n'])
            )

        # Output PDK and designer information as a table

        if 'PDK' in datasheet:
            ofile.write(
                '<TABLE border="1" frame="box" rules="none" width="40%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#ffffdd">\n')
            ofile.write('<TBODY>\n')
            ofile.write('<TR>\n')
            ofile.write('<TD> PDK:\n')
            ofile.write('<TD> ' + datasheet['PDK'] + '\n')
            ofile.write('</TR>\n')
            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')
            ofile.write('<BR>\n\n')

        # Output authorship information

        if 'authorship' in datasheet:
            authdict = datasheet['authorship']
            ofile.write(
                '<TABLE border="1" frame="box" rules="none" width="40%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#ffffdd">\n')
            ofile.write('<TBODY>\n')

            known_fields = [
                'designer',
                'company',
                'institution',
                'email',
                'creation_date',
                'modification_date',
                'license',
            ]

            if 'designer' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Designer:\n')
                ofile.write('<TD> ' + authdict['designer'] + '\n')
                ofile.write('</TR>\n')

            if 'company' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Company:\n')
                ofile.write('<TD> ' + authdict['company'] + '\n')
                ofile.write('</TR>\n')

            if 'institution' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Institution:\n')
                ofile.write('<TD> ' + authdict['institution'] + '\n')
                ofile.write('</TR>\n')

            if 'email' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Contact:\n')
                ofile.write('<TD> ' + authdict['email'] + '\n')
                ofile.write('</TR>\n')

            if 'creation_date' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Created:\n')
                ofile.write('<TD> ' + authdict['creation_date'] + '\n')
                ofile.write('</TR>\n')

            if 'modification_date' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> Last modified:\n')
                ofile.write('<TD> ' + authdict['modification_date'] + '\n')
                ofile.write('</TR>\n')

            if 'license' in authdict:
                ofile.write('<TR>\n')
                ofile.write('<TD> License:\n')
                ofile.write('<TD> ' + authdict['license'] + '\n')
                ofile.write('</TR>\n')

            for key in authdict.keys():
                if key not in known_fields:
                    ofile.write('<TR>\n')
                    ofile.write('<TD> ' + key + ':\n')
                    ofile.write('<TD> ' + authdict[key] + '\n')
                    ofile.write('</TR>\n')

            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')

        if 'dependencies' in datasheet:
            ofile.write('<H2> Project dependencies </H2>\n')
            dictlist = datasheet['dependencies']
            if isinstance(dictlist, dict):
                dictlist = [datasheet['dependencies']]

            numdepend = 0
            if len(dictlist) == 0 or len(dictlist) == 1 and dictlist[0] == {}:
                ofile.write('<BLOCKQUOTE>\n')
                ofile.write(
                    '   (<B>'
                    + datasheet['name']
                    + '</B> has no external dependencies.)\n'
                )
                ofile.write('</BLOCKQUOTE>\n')
            else:
                ofile.write('\n<UL>\n')
                for depend in dictlist:
                    if 'repository' in depend:
                        ofile.write(
                            '   <LI> <A HREF='
                            + depend['repository']
                            + '> '
                            + depend['name']
                            + '</A>\n'
                        )
                        numdepend += 1
                    elif 'name' in depend:
                        ofile.write('   <LI> ' + depend['name'] + '\n')
                        numdepend += 1

                ofile.write('</UL>\n\n')

        if 'pins' in datasheet:
            ofile.write('<H2> Pin names and descriptions </H2>\n')
            if svgname:
                ofile.write('\n<BLOCKQUOTE>\n   <CENTER>\n')
                ofile.write('      <IMG SRC=' + svgname + ' WIDTH=30%>\n')
                ofile.write(
                    '      <BR>\n      <I>Project schematic symbol</I>\n'
                )
                ofile.write('      <BR>\n')
                ofile.write('   </CENTER>\n</BLOCKQUOTE>\n\n')

            ofile.write(
                '<TABLE border="1" frame="box" rules="all" width="80%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#eeeeff">\n')
            ofile.write('<TBODY>\n<TR>\n')
            ofile.write('<TD> <I>pin name</I>')
            ofile.write('<TD> <I>description</I>')
            ofile.write('<TD> <I>type</I>')
            ofile.write('<TD> <I>direction</I>')
            ofile.write('<TD> <I>Vmin</I>')
            ofile.write('<TD> <I>Vmax</I>')
            ofile.write('<TD> <I>notes</I>')
            ofile.write('</TR>\n<TR>\n<TD>\n</TR>\n')

            for pin in datasheet['pins']:
                ofile.write('<TR>\n')
                if 'display' in pin:
                    pinname = pin['display']
                else:
                    pinname = pin['name']
                ofile.write('<TD> <B>' + pinname + '</B>\n')
                if 'description' in pin:
                    pindesc = pin['description']
                else:
                    pindesc = ''
                ofile.write('<TD> ' + pindesc + '\n')
                if 'type' in pin:
                    pintype = pin['type']
                else:
                    pintype = ''
                ofile.write('<TD> ' + pintype + '\n')

                if 'direction' in pin:
                    pindir = pin['direction']
                else:
                    pindir = ''
                ofile.write('<TD> ' + pindir + '\n')
                if 'Vmin' in pin:
                    pinvmin = pin['Vmin']
                else:
                    pinvmin = ''
                if isinstance(pinvmin, list):
                    ofile.write('<TD> ' + ' '.join(pinvmin) + '\n')
                else:
                    ofile.write('<TD> ' + pinvmin + '\n')
                if 'Vmax' in pin:
                    pinvmax = pin['Vmax']
                else:
                    pinvmax = ''
                if isinstance(pinvmax, list):
                    ofile.write('<TD> ' + ' '.join(pinvmax) + '\n')
                else:
                    ofile.write('<TD> ' + pinvmax + '\n')
                if 'note' in pin:
                    pinnote = pin['note']
                else:
                    pinnote = ''
                ofile.write('<TD> ' + pinnote + '\n')
                ofile.write('</TR>\n')

            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')

        if 'default_conditions' in datasheet:
            ofile.write('<H2> Default conditions </H2>\n')
            ofile.write(
                '<TABLE border="1" frame="box" rules="all" width="80%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#ddeeff">\n')
            ofile.write('<TBODY>\n<TR>\n')
            ofile.write('<TD> <I>name</I>')
            ofile.write('<TD> <I>description</I>')
            ofile.write('<TD> <I>unit</I>')
            ofile.write('<TD> <I>minimum</I>')
            ofile.write('<TD> <I>typical</I>')
            ofile.write('<TD> <I>maximum</I>')
            ofile.write('<TD> <I>notes</I>')
            ofile.write('</TR>\n<TR>\n<TD>\n</TR>\n')

            for cond in datasheet['default_conditions']:
                ofile.write('<TR>\n')
                if 'display' in cond:
                    condname = cond['display']
                else:
                    condname = cond['name']
                ofile.write('<TD> <B>' + condname + '</B>\n')
                if 'description' in cond:
                    conddesc = cond['description']
                else:
                    conddesc = ''
                ofile.write('<TD> ' + conddesc + '\n')
                if 'unit' in cond:
                    condunit = cond['unit']
                else:
                    condunit = ''
                ofile.write('<TD> ' + condunit + '\n')
                if 'minimum' in cond:
                    condmin = cond['minimum']
                else:
                    condmin = ''
                ofile.write('<TD> ' + condmin + '\n')
                if 'typical' in cond:
                    condtyp = cond['typical']
                else:
                    condtyp = ''
                ofile.write('<TD> ' + condtyp + '\n')
                if 'maximum' in cond:
                    condmax = cond['maximum']
                else:
                    condmax = ''
                ofile.write('<TD> ' + condmax + '\n')
                if 'note' in cond:
                    condnote = cond['note']
                else:
                    condnote = ''
                ofile.write('<TD> ' + condnote + '\n')
                ofile.write('</TR>\n')

            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')

        hasplots = False
        netlist_source = 'spec'

        if 'electrical_parameters' in datasheet:
            ofile.write('<H2> Electrical parameters </H2>\n')
            ofile.write(
                '<TABLE border="1" frame="box" rules="all" width="80%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#ddffff">\n')
            ofile.write('<TBODY>\n<TR>\n')
            ofile.write('<TD> <I>name</I>')
            ofile.write('<TD> <I>description</I>')
            ofile.write('<TD> <I>unit</I>')
            ofile.write('<TD> <I>minimum</I>')
            ofile.write('<TD> <I>typical</I>')
            ofile.write('<TD> <I>maximum</I>')
            ofile.write('<TD> <I>notes</I>')
            ofile.write('</TR>\n<TR>\n<TD>\n</TR>\n')

            for param in datasheet['electrical_parameters']:
                if 'spec' not in param and 'plot' in param:
                    hasplots = True
                    continue
                ofile.write('<TR>\n')
                if 'display' in param:
                    paramname = param['display']
                else:
                    paramname = param['name']
                ofile.write('<TD> <B>' + paramname + '</B>\n')
                if 'description' in param:
                    paramdesc = param['description']
                else:
                    paramdesc = ''
                ofile.write('<TD> ' + paramdesc + '\n')
                if 'unit' in param:
                    paramunit = param['unit']
                else:
                    paramunit = ''
                ofile.write('<TD> ' + paramunit + '\n')

                # NOTE: To do: Split between specification and result
                # Handle netlist source for result.

                netlist_source = 'spec'
                netlist_source_text = 'Specification'
                if 'results' in param:
                    results = param['results']
                    if isinstance(results, list):
                        for result in results:
                            if result['name'] == 'rcx':
                                netlist_source = 'rcx'
                                netlist_source_text = 'Parasitic R,C-extracted'
                                break
                            elif result['name'] == 'pex':
                                netlist_source = 'pex'
                                netlist_source_text = 'Parasitic C-extracted'
                                break
                            elif result['name'] == 'layout':
                                netlist_source = 'layout'
                                netlist_source_text = 'Layout extracted'
                                break
                            elif result['name'] == 'schematic':
                                netlist_source = 'schematic'
                                netlist_source_text = 'Schematic captured'
                                break
                    else:
                        result = results

                    if 'minimum' in result:
                        resultmin = result['minimum']
                    else:
                        resultmin = ''

                    if isinstance(resultmin, list):
                        if len(resultmin) > 1 and resultmin[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resultmin[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resultmin[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resultmin + '\n')
                    if 'typical' in result:
                        resulttyp = result['typical']
                    else:
                        resulttyp = ''
                    if isinstance(resulttyp, list):
                        if len(resulttyp) > 1 and resulttyp[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resulttyp[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resulttyp[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resulttyp + '\n')
                    if 'maximum' in result:
                        resultmax = result['maximum']
                    else:
                        resultmax = ''
                    if isinstance(resultmax, list):
                        if len(resultmax) > 1 and resultmax[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resultmax[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resultmax[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resultmax + '\n')

                elif 'spec' in param:
                    spec = param['spec']
                    if 'minimum' in spec:
                        specmin = spec['minimum']
                    else:
                        specmin = ''
                    if isinstance(specmin, list):
                        spectext = specmin[0]
                    else:
                        spectext = specmin
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')
                    if 'typical' in spec:
                        spectyp = spec['typical']
                    else:
                        spectyp = ''
                    if isinstance(spectyp, list):
                        spectext = spectyp[0]
                    else:
                        spectext = spectyp
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')
                    if 'maximum' in spec:
                        specmax = spec['maximum']
                    else:
                        specmax = ''
                    if isinstance(specmax, list):
                        spectext = specmax[0]
                    else:
                        spectext = specmax
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')

                if 'note' in param:
                    paramnote = param['note']
                else:
                    paramnote = ''
                ofile.write('<TD> ' + paramnote + '\n')
                ofile.write('</TR>\n')

            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')

            ofile.write(
                '<BR><I>Note:</I> Values taken from '
                + netlist_source_text
                + '<BR>\n'
            )

        if 'physical_parameters' in datasheet:
            ofile.write('<H2> Physical parameters </H2>\n')
            ofile.write(
                '<TABLE border="1" frame="box" rules="all" width="80%" cellspacing="0"\n'
            )
            ofile.write('\tcellpadding="2" bgcolor="#eeffff">\n')
            ofile.write('<TBODY>\n<TR>\n')
            ofile.write('<TD> <I>name</I>')
            ofile.write('<TD> <I>description</I>')
            ofile.write('<TD> <I>unit</I>')
            ofile.write('<TD> <I>minimum</I>')
            ofile.write('<TD> <I>typical</I>')
            ofile.write('<TD> <I>maximum</I>')
            ofile.write('<TD> <I>notes</I>')
            ofile.write('</TR>\n<TR>\n<TD>\n</TR>\n')

            for param in datasheet['physical_parameters']:
                ofile.write('<TR>\n')
                if 'display' in param:
                    paramname = param['display']
                else:
                    paramname = param['name']
                ofile.write('<TD> <B>' + paramname + '</B>\n')
                if 'description' in param:
                    paramdesc = param['description']
                else:
                    paramdesc = ''
                ofile.write('<TD> ' + paramdesc + '\n')
                if 'unit' in param:
                    paramunit = param['unit']
                else:
                    paramunit = ''
                ofile.write('<TD> ' + paramunit + '\n')

                # NOTE: To do: Split between specification and result
                # Handle netlist source for result.

                netlist_source = 'spec'
                netlist_source_text = 'Specification'
                if 'results' in param:
                    results = param['results']
                    if isinstance(results, list):
                        for result in results:
                            if result['name'] == 'rcx':
                                netlist_source = 'rcx'
                                netlist_source_text = 'Parasitic R,C-extracted'
                                break
                            elif result['name'] == 'pex':
                                netlist_source = 'pex'
                                netlist_source_text = 'Parasitic R,C-extracted'
                                netlist_source_text = 'Parasitic C-extracted'
                                break
                            elif result['name'] == 'layout':
                                netlist_source = 'layout'
                                netlist_source_text = 'Layout extracted'
                                break
                            elif result['name'] == 'schematic':
                                netlist_source = 'schematic'
                                netlist_source_text = 'Schematic captured'
                                break
                    else:
                        result = results

                    if 'minimum' in result:
                        resultmin = result['minimum']
                    else:
                        resultmin = ''

                    if isinstance(resultmin, list):
                        if len(resultmin) > 1 and resultmin[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resultmin[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resultmin[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resultmin + '\n')
                    if 'typical' in result:
                        resulttyp = result['typical']
                    else:
                        resulttyp = ''
                    if isinstance(resulttyp, list):
                        if len(resulttyp) > 1 and resulttyp[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resulttyp[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resulttyp[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resulttyp + '\n')
                    if 'maximum' in result:
                        resultmax = result['maximum']
                    else:
                        resultmax = ''
                    if isinstance(resultmax, list):
                        if len(resultmax) > 1 and resultmax[1] == 'fail':
                            ofile.write(
                                '<TD> <FONT COLOR=red>'
                                + resultmax[0]
                                + '</FONT>\n'
                            )
                        else:
                            ofile.write('<TD> ' + resultmax[0] + '\n')
                    else:
                        ofile.write('<TD> ' + resultmax + '\n')

                elif 'spec' in param:
                    spec = param['spec']
                    if 'minimum' in spec:
                        specmin = spec['minimum']
                    else:
                        specmin = ''
                    if isinstance(specmin, list):
                        spectext = specmin[0]
                    else:
                        spectext = specmin
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')
                    if 'typical' in spec:
                        spectyp = spec['typical']
                    else:
                        spectyp = ''
                    if isinstance(spectyp, list):
                        spectext = spectyp[0]
                    else:
                        spectext = spectyp
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')
                    if 'maximum' in spec:
                        specmax = spec['maximum']
                    else:
                        specmax = ''
                    if isinstance(specmax, list):
                        spectext = specmax[0]
                    else:
                        spectext = specmax
                    if spectext == 'any':
                        spectext = ' '
                    ofile.write('<TD> ' + spectext + '\n')

                if 'note' in param:
                    paramnote = param['note']
                else:
                    paramnote = ''
                ofile.write('<TD> ' + paramnote + '\n')
                ofile.write('</TR>\n')

            ofile.write('</TBODY>\n')
            ofile.write('</TABLE>\n')

            ofile.write(
                '<BR><I>Note:</I> Values taken from '
                + netlist_source_text
                + '<BR>\n'
            )

        ofile.write('</BODY>\n')
        ofile.write('</HTML>\n')

        # Plots to do:  Group plots in pairs and add two plots per row.
        # Plots really need to be embedded in the document, not referenced to
        # the local file system.

        if hasplots:
            for param in datasheet['electrical_parameters']:
                if 'spec' not in param and 'plot' in param:
                    plotrec = param['plot']
                    if 'filename' in plotrec:
                        plotfile = plotrec['filename']
                        if os.path.splitext(plotfile)[1] == '':
                            plotfile += '.png'
                        if 'plots' in paths:
                            plotpath = paths['plots']
                        elif 'simulation' in paths:
                            plotpath = paths['simulation']
                        else:
                            plotpath = ''

                        plottypes = [
                            'rcx',
                            'pex',
                            'layout',
                            'schematic',
                            'none',
                        ]
                        for plotsubdir in plottypes:
                            plotfilepath = os.path.join(
                                plotpath, plotsubdir, plotfile
                            )
                            absfilepath = os.path.abspath(plotfilepath)
                            if not filename:
                                fullfilepath = os.path.join('..', plotfilepath)
                            else:
                                fullfilepath = absfilepath
                            if os.path.isfile(absfilepath):
                                break

                        if plotsubdir == 'none':
                            plotfilepath = os.path.join(plotpath, plotfile)
                            absfilepath = os.path.abspath(plotfilepath)
                            if not filename:
                                fullfilepath = os.path.join('..', plotfilepath)
                            else:
                                fullfilepath = absfilepath

                        if os.path.isfile(absfilepath):
                            ofile.write('\n<BLOCKQUOTE>\n')
                            ofile.write('   <CENTER>\n')
                            ofile.write(
                                '      <IMG SRC=' + fullfilepath + '>\n'
                            )
                            if 'description' in param:
                                ofile.write('      <BR>\n')
                                ofile.write(
                                    '      <I>'
                                    + param['description']
                                    + '</I>\n'
                                )
                                if plotsubdir != 'none':
                                    ofile.write('      <BR>\n')
                                    ofile.write(
                                        '      (Values taken from '
                                        + plotsubdir
                                        + ' extraction)\n'
                                    )
                            ofile.write('   </CENTER>\n')
                            ofile.write('</BLOCKQUOTE>\n\n')
                        else:
                            print('Warning:  Cannot find plot ' + absfilepath)

    print('Done writing HTML output file ' + ofilename)


# ---------------------------------------------------------------
# cace_summarize_result
#
# Print a summary report of a single "results" block from a
# datasheet.
# ---------------------------------------------------------------


def cace_summarize_result(param, result):
    spec = param['spec']
    unit = param['unit'] if 'unit' in param else ''

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


def markdown_summary(datasheet, file=None):
    """
    Print a brief summary to either stdout or any file that is passed.
    The summary is formatted in Markdown and can be viewed with any
    Markdown viewer
    """

    # Table spacings
    sp = [20, 20, 10, 12, 10, 12, 10, 12, 8]

    skip_msg = 'Skip 🟧'
    fail_msg = 'Fail ❌'
    pass_msg = 'Pass ✅'

    print('\n# CACE Summary\n', file=file)

    print(
        f'**general**\n\n'
        f'- name: {datasheet["name"]}\n'
        f'- description: {datasheet["description"]}\n'
        f'- commit: {datasheet["commit"]}\n'
        f'- PDK: {datasheet["PDK"]}\n'
        f'- cace_format: {datasheet["cace_format"]}\n',
        file=file,
    )

    print(
        f'**authorship**\n\n'
        f'- designer: {datasheet["authorship"]["designer"]}\n'
        f'- company: {datasheet["authorship"]["company"]}\n'
        f'- creation_date: {datasheet["authorship"]["creation_date"]}\n'
        f'- license: {datasheet["authorship"]["license"]}\n',
        file=file,
    )

    print(
        f'**netlist source**: {datasheet["runtime_options"]["netlist_source"]}\n',
        file=file,
    )

    print('## Electrical Parameters\n', file=file)

    # Print the table headings
    print(
        f'| {"Parameter": ^{sp[0]}} '
        f'| {"Testbench": ^{sp[1]}} '
        f'| {"Min Limit": ^{sp[2]}} '
        f'| {"Min Value": ^{sp[3]}} '
        f'| {"Typ Target": ^{sp[4]}} '
        f'| {"Typ Value": ^{sp[5]}} '
        f'| {"Max Limit": ^{sp[6]}} '
        f'| {"Max Value": ^{sp[7]}} '
        f'| {"Status": ^{sp[8]}} |',
        file=file,
    )
    # Print the separators
    print(
        f'| :{"-"*(sp[0]-1)} '
        f'| :{"-"*(sp[1]-1)} '
        f'| {"-"*(sp[2]-1)}: '
        f'| {"-"*(sp[3]-1)}: '
        f'| {"-"*(sp[4]-1)}: '
        f'| {"-"*(sp[5]-1)}: '
        f'| {"-"*(sp[6]-1)}: '
        f'| {"-"*(sp[7]-1)}: '
        f'| :{"-"*(sp[8]-2)}: |',
        file=file,
    )

    if 'electrical_parameters' in datasheet:
        for eparam in datasheet['electrical_parameters']:

            # Get the unit
            unit = eparam['unit'] if 'unit' in eparam else None

            limits = {'minimum': '', 'typical': '', 'maximum': ''}

            # Get the limits from the spec
            if 'spec' in eparam:
                for spec_type in ['minimum', 'typical', 'maximum']:
                    if spec_type in eparam['spec']:
                        limits[spec_type] = eparam['spec'][spec_type]

                        if isinstance(limits[spec_type], list):
                            limits[spec_type] = limits[spec_type][0]

            values = {'minimum': '', 'typical': '', 'maximum': ''}

            # Get the results
            passing = None
            if 'results' in eparam:
                passing = True

                for result_type in ['minimum', 'typical', 'maximum']:
                    if result_type in eparam['results']:
                        values[result_type] = eparam['results'][result_type][0]

                        # Any fail fails the whole parameter
                        if eparam['results'][result_type][1] != 'pass':
                            passing = False

            # Get the status message
            status = pass_msg if passing else fail_msg

            if passing == None:
                status = skip_msg

            if 'status' in eparam and eparam['status'] == 'skip':
                status = skip_msg

            # Get the testbench
            testbench = ''
            if 'simulate' in eparam:
                testbench = eparam['simulate']['template']

            # Don't print any unit if empty or any
            no_unit = ['', 'any']

            # Print the row for the parameter
            parameter_str = eparam['name']
            testbench_str = testbench
            min_limit_str = (
                f'{limits["minimum"]} {unit}'
                if unit and not limits['minimum'] in no_unit
                else limits['minimum']
            )
            min_value_str = (
                f'{values["minimum"]} {unit}'
                if unit and not values['minimum'] in no_unit
                else values['minimum']
            )
            typ_limit_str = (
                f'{limits["typical"]} {unit}'
                if unit and not limits['typical'] in no_unit
                else limits['typical']
            )
            typ_value_str = (
                f'{values["typical"]} {unit}'
                if unit and not values['typical'] in no_unit
                else values['typical']
            )
            max_limit_str = (
                f'{limits["maximum"]} {unit}'
                if unit and not limits['maximum'] in no_unit
                else limits['maximum']
            )
            max_value_str = (
                f'{values["maximum"]} {unit}'
                if unit and not values['maximum'] in no_unit
                else values['maximum']
            )
            status_str = status

            print(
                f'| {parameter_str: <{sp[0]}} '
                f'| {testbench_str: <{sp[1]}} '
                f'| {min_limit_str: >{sp[2]}} '
                f'| {min_value_str: >{sp[3]}} '
                f'| {typ_limit_str: >{sp[4]}} '
                f'| {typ_value_str: >{sp[5]}} '
                f'| {max_limit_str: >{sp[6]}} '
                f'| {max_value_str: >{sp[7]}} '
                f'| {status_str: ^{sp[8]-1}} |',
                file=file,
            )

    print('\n## Physical Parameters\n', file=file)

    # Print the table headings
    print(
        f'| {"Parameter": ^{sp[0]}} '
        f'| {"Tool": ^{sp[1]}} '
        f'| {"Min Limit": ^{sp[2]}} '
        f'| {"Min Value": ^{sp[3]}} '
        f'| {"Typ Target": ^{sp[4]}} '
        f'| {"Typ Value": ^{sp[5]}} '
        f'| {"Max Limit": ^{sp[6]}} '
        f'| {"Max Value": ^{sp[7]}} '
        f'| {"Status": ^{sp[8]}} |',
        file=file,
    )
    # Print the separators
    print(
        f'| :{"-"*(sp[0]-1)} '
        f'| :{"-"*(sp[1]-1)} '
        f'| {"-"*(sp[2]-1)}: '
        f'| {"-"*(sp[3]-1)}: '
        f'| {"-"*(sp[4]-1)}: '
        f'| {"-"*(sp[5]-1)}: '
        f'| {"-"*(sp[6]-1)}: '
        f'| {"-"*(sp[7]-1)}: '
        f'| :{"-"*(sp[8]-2)}: |',
        file=file,
    )

    if 'physical_parameters' in datasheet:
        for pparam in datasheet['physical_parameters']:

            # Get the unit
            unit = pparam['unit'] if 'unit' in pparam else None

            limits = {'minimum': '', 'typical': '', 'maximum': ''}

            # Get the limits from the spec
            if 'spec' in pparam:
                for spec_type in ['minimum', 'typical', 'maximum']:
                    if spec_type in pparam['spec']:
                        limits[spec_type] = pparam['spec'][spec_type]

                        if isinstance(limits[spec_type], list):
                            limits[spec_type] = limits[spec_type][0]

            values = {'minimum': '', 'typical': '', 'maximum': ''}

            # Get the results
            passing = None
            if 'results' in pparam:
                passing = True

                for result_type in ['minimum', 'typical', 'maximum']:
                    if result_type in pparam['results']:
                        values[result_type] = pparam['results'][result_type][0]

                        # Any fail fails the whole parameter
                        if pparam['results'][result_type][1] != 'pass':
                            passing = False

            # Get the status message
            status = pass_msg if passing else fail_msg

            if passing == None:
                status = skip_msg

            if 'status' in pparam and pparam['status'] == 'skip':
                status = skip_msg

            # Get the tool
            tool = ''
            if 'evaluate' in pparam:
                tool = pparam['evaluate']['tool']
                if isinstance(tool, list):
                    tool = tool[0]

            # Don't print any unit if empty or any
            no_unit = ['', 'any']

            # Print the row for the parameter
            parameter_str = pparam['name']
            tool_str = tool
            min_limit_str = (
                f'{limits["minimum"]} {unit}'
                if unit and not limits['minimum'] in no_unit
                else limits['minimum']
            )
            min_value_str = (
                f'{values["minimum"]} {unit}'
                if unit and not values['minimum'] in no_unit
                else values['minimum']
            )
            typ_limit_str = (
                f'{limits["typical"]} {unit}'
                if unit and not limits['typical'] in no_unit
                else limits['typical']
            )
            typ_value_str = (
                f'{values["typical"]} {unit}'
                if unit and not values['typical'] in no_unit
                else values['typical']
            )
            max_limit_str = (
                f'{limits["maximum"]} {unit}'
                if unit and not limits['maximum'] in no_unit
                else limits['maximum']
            )
            max_value_str = (
                f'{values["maximum"]} {unit}'
                if unit and not values['maximum'] in no_unit
                else values['maximum']
            )
            status_str = status

            print(
                f'| {parameter_str: <{sp[0]}} '
                f'| {tool_str: <{sp[1]}} '
                f'| {min_limit_str: >{sp[2]}} '
                f'| {min_value_str: >{sp[3]}} '
                f'| {typ_limit_str: >{sp[4]}} '
                f'| {typ_value_str: >{sp[5]}} '
                f'| {max_limit_str: >{sp[6]}} '
                f'| {max_value_str: >{sp[7]}} '
                f'| {status_str: ^{sp[8]-1}} |',
                file=file,
            )

    print('', file=file)


# ---------------------------------------------------------------
# cace_summary
#
# Print a summary report of results from a datasheet
#
# "datasheet" is a CACE characterization dataset
# "paramname" is a list of parameters to summarize,
# 	or if it is None, then all parameters should be output.
# ---------------------------------------------------------------


def cace_summary(datasheet, paramnames):

    # Summarize all parameters
    if not paramnames:
        if 'electrical_parameters' in datasheet:
            for eparam in datasheet['electrical_parameters']:
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

    # Only summarize the parameters in the list
    else:
        for paramname in paramnames:
            if 'electrical_parameters' in datasheet:
                for eparam in datasheet['electrical_parameters']:
                    if paramname == eparam['name']:
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
                    if paramname == pparam['name']:
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


# ---------------------------------------------------------------
# Convert from unicode to text format
# ---------------------------------------------------------------


def uchar_sub(string):
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


# ---------------------------------------------------------------
# Output a list item
# ---------------------------------------------------------------


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
            outlines = cace_output_known_dict(
                dictname, item, outlines, False, indent
            )
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
                newline = tabs + ' '.join(asciiout)
            outlines.append(newline)
        elif dictname == 'conditions':
            # Results passed back as stdout from simulation or evaluation
            asciiout = list(uchar_sub(word) for word in item)
            newline = tabs + ' '.join(asciiout)
            outlines.append(newline)
        else:
            # This should not happen---list items other than "results"
            # are only supposed to be dictionaries
            newline = tabs + '# Failed: ' + str(item)
            outlines.append(newline)
    return outlines


# ---------------------------------------------------------------
# ---------------------------------------------------------------


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
        outlines = cace_output_known_dict(
            key, value, outlines, False, indent + 1
        )
        newline = tabs + '}'
    elif isinstance(value, list):
        # Handle lists that are not dictionaries
        just_lists = [
            'minimum',
            'maximum',
            'typical',
            'Vmin',
            'Vmax',
            'format',
            'tool',
        ]
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
                        newline = newline + ' '.join(value[lidx : ridx - 1])
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


# ---------------------------------------------------------------
# Output an known dictionary item.  The purpose is to output
# keys in a sane and consistent order when possible.  Includes
# output of "standard comments" for specific sections.
# ---------------------------------------------------------------


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
        newline = (
            '# Default values for electrical parameter measurement conditions'
        )
        outlines.append(newline)
        newline = '# if not otherwise specified'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    return outlines


# ---------------------------------------------------------------
# Output an known dictionary item.  The purpose is to output
# keys in a sane and consistent order when possible.  Includes
# output of "standard comments" for specific sections.
# ---------------------------------------------------------------


def cace_output_known_dict(dictname, itemdict, outlines, doruntime, indent):
    if dictname == 'topmost':
        orderedlist = [
            'name',
            'description',
            'category',
            'note',
            'commit',
            'PDK',
            'foundry',
            'cace_format',
            'authorship',
            'paths',
            'dependencies',
            'pins',
            'default_conditions',
            'electrical_parameters',
            'physical_parameters',
            'runtime_options',
        ]
        if 'cace_format' not in itemdict:
            itemdict['cace_format'] = '4.0'

    elif dictname == 'pins':
        orderedlist = [
            'name',
            'description',
            'type',
            'direction',
            'Vmin',
            'Vmax',
            'note',
        ]

    elif dictname == 'paths':
        orderedlist = [
            'root',
            'documentation',
            'schematic',
            'layout',
            'magic',
            'netlist',
            'netgen',
            'verilog',
            'testbench',
            'simulation',
            'plots',
            'logs',
            'reports',
        ]

    elif dictname == 'dependencies':
        orderedlist = ['name', 'path', 'repository', 'commit', 'note']

    elif dictname == 'electrical_parameters':
        orderedlist = [
            'name',
            'status',
            'description',
            'display',
            'unit',
            'spec',
            'results',
            'simulate',
            'measure',
            'plot',
            'variables',
            'conditions',
            'testbenches',
        ]

    elif dictname == 'physical_parameters':
        orderedlist = [
            'name',
            'status',
            'description',
            'display',
            'unit',
            'spec',
            'evaluate',
            'conditions',
            'results',
        ]

    elif dictname == 'default_conditions':
        orderedlist = [
            'name',
            'description',
            'display',
            'unit',
            'minimum',
            'typical',
            'maximum',
            'enumerate',
            'step',
            'stepsize',
            'note',
        ]

    elif dictname == 'testbenches':
        orderedlist = [
            'filename',
            'conditions',
            'variables',
            'results',
            'format',
        ]

    elif dictname == 'authorship':
        orderedlist = [
            'designer',
            'company',
            'institution',
            'organization',
            'address',
            'email',
            'url',
            'creation_date',
            'modification_date',
            'license',
            'note',
        ]
        # Date string formatted as, e.g., "November 22, 2023 at 01:16pm"
        datestring = datetime.datetime.now().strftime('%B %e, %Y at %I:%M%P')
        if 'creation_date' not in itemdict:
            itemdict['creation_date'] = datestring
        # Always update modification date to current datestamp
        itemdict['modification_date'] = datestring

    elif dictname == 'spec':
        orderedlist = ['minimum', 'typical', 'maximum', 'note']

    elif dictname == 'results':
        orderedlist = ['name', 'minimum', 'typical', 'maximum', 'status']

    elif dictname == 'simulate':
        orderedlist = [
            'tool',
            'template',
            'filename',
            'format',
            'collate',
            'group_size',
            'note',
        ]

    elif dictname == 'measure':
        orderedlist = ['tool', 'filename', 'calc', 'note']

    elif dictname == 'evaluate':
        orderedlist = ['tool', 'filename', 'note']

    elif dictname == 'conditions':
        orderedlist = [
            'name',
            'description',
            'display',
            'unit',
            'minimum',
            'typical',
            'maximum',
            'enumerate',
            'step',
            'stepsize',
            'note',
        ]
    elif dictname == 'plot':
        orderedlist = [
            'filename',
            'title',
            'type',
            'xaxis',
            'xlabel',
            'yaxis',
            'ylabel',
            'note',
        ]
    elif dictname == 'variables':
        orderedlist = ['name', 'display', 'unit', 'note']
    elif dictname == 'runtime_options':
        orderedlist = [
            'filename',
            'netlist_source',
            'score',
            'debug',
            'force',
            'note',
        ]
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
        print(
            'Diagnostic: Adding item with unrecognized key '
            + key
            + ' in dictionary '
            + dictname
        )
        value = itemdict[key]
        outlines = cace_output_item(key, value, outlines, indent)

    return outlines


# ---------------------------------------------------------------
# Output an unknown dictionary item
# ---------------------------------------------------------------


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


# ---------------------------------------------------------------
# Write a format 4.0 text file from a CACE datasheet dictionary
#
# If 'doruntime' is True, then write the runtime options
# dictionary.  If False, then leave it out of the output.
# ---------------------------------------------------------------


def cace_write(datasheet, filename, doruntime=False):
    outlines = []

    # Rewrite paths['root'] as the cwd relative to filename.
    oldroot = None
    if 'paths' in datasheet:
        paths = datasheet['paths']
        if 'root' in paths:
            oldroot = paths['root']
            filepath = os.path.split(filename)[0]
            newroot = os.path.relpath(os.curdir, filepath)
            paths['root'] = newroot

    newline = '#---------------------------------------------------'
    outlines.append(newline)

    if filename:
        newline = '# CACE format 4.0 characterization file ' + filename
        outlines.append(newline)
        newline = '#---------------------------------------------------'
        outlines.append(newline)
        newline = ''
        outlines.append(newline)

    outlines = cace_output_known_dict(
        'topmost', datasheet, outlines, doruntime, 0
    )

    # Put back the old value of paths['root'] (should be '.')
    if oldroot:
        paths['root'] = oldroot

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
