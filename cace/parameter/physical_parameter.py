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

import os
import re
import sys
import math
import json
import threading
import subprocess

from ..common.ring_buffer import RingBuffer

from ..common.layout_estimate import layout_estimate
from ..common.cace_collate import addnewresult, find_limits
from ..common.cace_regenerate import (
    get_magic_rcfile,
    get_pdk_root,
    get_netgen_setupfile,
)
from ..common.netlist_precheck import netlist_precheck
from .parameter import Parameter

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


class PhysicalParameter(Parameter):
    """
    The PhysicalParameter evaluates a physical parameter
    """

    def __init__(
        self,
        param,
        datasheet,
        pdk,
        paths,
        runtime_options,
        run_dir,
        start_cb=None,
        end_cb=None,
        cancel_cb=None,
        step_cb=None,
        *args,
        **kwargs,
    ):
        super().__init__(
            param,
            datasheet,
            pdk,
            paths,
            runtime_options,
            run_dir,
            start_cb,
            end_cb,
            cancel_cb,
            step_cb,
            *args,
            **kwargs,
        )

    def implementation(self):

        self.cancel_point()

        info(f'Parameter {self.param["name"]}: Evaluating physical parameter')
        self.cace_evaluate(self.datasheet, self.param)

        if self.step_cb:
            self.step_cb(self.param)

    def preprocess(self):
        pass

    def postprocess(self):
        pass

    def get_magic_namespace(self, dsheet):
        """
        Run magic to querty the PDKNAMESPACE variable, which should be set
        by the Tcl device generator script.
        """

        rcfilename = get_magic_rcfile(dsheet)

        mproc = subprocess.Popen(
            ['magic', '-dnull', '-noconsole', '-rcfile', rcfilename],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        mproc.stdin.write(
            'if {[catch {puts namespace=$PDKNAMESPACE}]} {puts namespace=$PDKPATH}\n'
        )
        outlines = mproc.communicate()[0]
        retcode = mproc.returncode
        if retcode != 0:
            err('Magic exited with non-zero return code!')
            return None

        magrex = re.compile('namespace=(.*)')
        for line in outlines.splitlines():
            lmatch = magrex.match(line)
            if lmatch:
                namespace = lmatch.group(1)
                return namespace

        return dsheet['PDK']

    def run_magic_geometry(self, dsheet, layout_filename):
        """
        Run magic to get the bounds of the design geometry

        Return triplet of area, width, and height
        """

        is_mag = (
            True if os.path.splitext(layout_filename)[1] == '.mag' else False
        )
        layout_path = os.path.split(layout_filename)[0]
        layout_locname = os.path.split(layout_filename)[1]
        layout_cellname = os.path.splitext(layout_locname)[0]

        if not os.path.exists(layout_filename):
            err('Layout ' + layout_filename + ' does not exist!')
            return 0, 0, 0

        rcfilename = get_magic_rcfile(dsheet)

        areaproc = subprocess.Popen(
            ['magic', '-dnull', '-noconsole', '-rcfile', rcfilename],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=layout_path,
            text=True,
        )
        if is_mag:
            areaproc.stdin.write('load ' + layout_cellname + '\n')
        else:
            areaproc.stdin.write('gds read ' + layout_locname + '\n')
            areaproc.stdin.write('set toplist [cellname list top]\n')
            areaproc.stdin.write('set numtop [llength $toplist]\n')
            areaproc.stdin.write('if {$numtop > 1} {\n')
            areaproc.stdin.write('   foreach topcell $toplist {\n')
            areaproc.stdin.write('      if {$topcell != "(UNNAMED)"} {\n')
            areaproc.stdin.write('         load $topcell\n')
            areaproc.stdin.write('         break\n')
            areaproc.stdin.write('      }\n')
            areaproc.stdin.write('   }\n')
            areaproc.stdin.write('}\n')

        areaproc.stdin.write('select top cell\n')
        areaproc.stdin.write('box\n')
        areaproc.stdin.write('quit -noprompt\n')
        outlines = areaproc.communicate()[0]
        retcode = areaproc.returncode

        if retcode != 0:
            err('Magic exited with non-zero return code!')
            return 0, 0, 0

        magrex = re.compile(
            'microns:[ \t]+([0-9.]+)[ \t]*x[ \t]*([0-9.]+)[ \t]+.*[ \t]+([0-9.]+)[ \t]*$'
        )
        for line in outlines.splitlines():
            lmatch = magrex.match(line)
            if lmatch:
                widthval = float(lmatch.group(1))
                heightval = float(lmatch.group(2))
                areaval = float(lmatch.group(3))

        return areaval, widthval, heightval

    def cace_area(self, datasheet, param, cond, toolargs=None):
        """
        Determine bounds of the design geometry

        "cond" should be one of "area", "width", or "height", and determines
        what value is returned by the routine.

        The routine reads the .mag or .gds file of the layout and returns
        the width and height values in microns.  This is captured from
        standard output and the requested result returned to the calling
        routine.

        In case of any failure, the return value is None.
        """
        areaest = 0
        projname = datasheet['name']

        if 'runtime_options' in datasheet:
            runtime_options = datasheet['runtime_options']
            source = runtime_options['netlist_source']
            debug = runtime_options['debug']
            if 'keep' in runtime_options:
                keep = runtime_options['keep']
            else:
                keep = False
        else:
            # Assume layout and flag an error if layout does not exist.
            source = 'layout'
            debug = False
            keep = False

        if 'unit' in param:
            units = param['unit']
        else:
            units = ''

        score = 'pass'

        if 'spec' in param:
            spec = param['spec']
        else:
            spec = {}

        resultdict = {}

        paths = datasheet['paths']
        pdk = datasheet['PDK']

        rcfile = get_magic_rcfile(datasheet)

        if source == 'schematic':
            info(
                'Source netlist is schematic: Physical parameters are estimated.'
            )
            netlist_path = os.path.join(paths['netlist'], 'schematic')
            netlist_filename = os.path.join(netlist_path, projname + '.spice')
            namespace = self.get_magic_namespace(datasheet)
            layoutest = layout_estimate(
                netlist_filename, namespace, rcfile, keep
            )
            try:
                areaest = float(layoutest)
            except:
                warn(
                    'Layout estimate returned non-numeric result '
                    + str(areaest)
                )
                areaest = 0

            # Assume a cell layout with a golden ratio aspect.  This is of course
            # meaningless but yields a useful target value placeholder.
            width = int(math.sqrt(1.62 * areaest))
            height = width / 1.62

            if areaest == 0:
                resultdict = incompleteresult(param)
            else:
                resultdict = {}
                if 'maximum' in spec:
                    spectype = 'maximum'
                    maxrec = spec['maximum']
                    maxresult = find_limits(
                        spectype, maxrec, [areaest], units, debug
                    )
                    if maxresult[1] == 'fail':
                        score = 'fail'
                    resultdict['maximum'] = maxresult

        else:
            layout_filename = None
            if 'layout' in paths:
                layout_path = paths['layout']
                layoutname = projname + '.gds'
                layout_filename = os.path.join(layout_path, layoutname)
                if not os.path.exists(layout_filename):
                    layoutname = projname + '.gds.gz'
                    layout_filename = os.path.join(layout_path, layoutname)
                    if not os.path.exists(layout_filename):
                        layout_filename = None

            if not layout_filename:
                if 'magic' in paths:
                    magic_path = paths['magic']
                    magicname = projname + '.mag'
                    layout_filename = os.path.join(magic_path, magicname)

            areaval, width, height = self.run_magic_geometry(
                datasheet, layout_filename
            )

            if areaval == 0:
                resultdict = incompleteresult(param)
            else:
                if cond == 'height':
                    resultlist = [height]
                elif cond == 'width':
                    resultlist = [width]
                else:
                    resultlist = [areaval]

                if 'maximum' in spec:
                    spectype = 'maximum'
                    maxrec = spec['maximum']
                    maxresult = find_limits(
                        spectype, maxrec, resultlist, units, debug
                    )
                    if maxresult[1] == 'fail':
                        score = 'fail'
                    resultdict['maximum'] = maxresult

        return resultdict

    def cace_drc(self, datasheet, param, toolargs=None):
        """
        Run magic to get a DRC report
        """
        runtime_options = datasheet['runtime_options']
        debug = runtime_options['debug']

        if 'netlist_source' in runtime_options:
            if runtime_options['netlist_source'] == 'schematic':
                warn('Netlist source is schematic capture. Not running DRC.')
                return {}

        projname = datasheet['name']
        paths = datasheet['paths']

        info('Running magic to get layout DRC report.')

        layout_filename = None
        is_mag = False
        if 'layout' in paths:
            layout_path = paths['layout']
            layoutname = projname + '.gds'
            layout_filename = os.path.join(layout_path, layoutname)
            if not os.path.exists(layout_filename):
                layoutname = projname + '.gds.gz'
                layout_filename = os.path.join(layout_path, layoutname)
                if not os.path.exists(layout_filename):
                    layout_filename = None

        if not layout_filename:
            if 'magic' in paths:
                magic_path = paths['magic']
                magicname = projname + '.mag'
                layout_filename = os.path.join(magic_path, magicname)
                is_mag = True

        layout_path = os.path.split(layout_filename)[0]
        layout_locname = os.path.split(layout_filename)[1]
        layout_cellname = os.path.splitext(layout_locname)[0]

        rcfile = get_magic_rcfile(datasheet)

        # Find the layout directory and check if there is a layout
        # for the cell there.

        pdk_root = get_pdk_root()
        pdk = datasheet['PDK']

        newenv = os.environ.copy()
        if pdk_root and 'PDK_ROOT' not in newenv:
            newenv['PDK_ROOT'] = pdk_root
        if pdk and 'PDK' not in newenv:
            newenv['PDK'] = pdk

        drcproc = subprocess.Popen(
            ['magic', '-dnull', '-noconsole', '-rcfile', rcfile],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=newenv,
            cwd=self.param_dir,
            text=True,
        )

        drcproc.stdin.write('addpath ' + os.path.abspath(layout_path) + '\n')
        if is_mag:
            drcproc.stdin.write('load ' + layout_cellname + '\n')
        else:
            drcproc.stdin.write('gds read ' + layout_locname + '\n')
            drcproc.stdin.write('set toplist [cellname list top]\n')
            drcproc.stdin.write('set numtop [llength $toplist]\n')
            drcproc.stdin.write('if {$numtop > 1} {\n')
            drcproc.stdin.write('   foreach topcell $toplist {\n')
            drcproc.stdin.write('      if {$topcell != "(UNNAMED)"} {\n')
            drcproc.stdin.write('         load $topcell\n')
            drcproc.stdin.write('         break\n')
            drcproc.stdin.write('      }\n')
            drcproc.stdin.write('   }\n')
            drcproc.stdin.write('}\n')

        drcproc.stdin.write('drc on\n')
        drcproc.stdin.write('catch {drc style drc(full)}\n')
        drcproc.stdin.write('select top cell\n')
        drcproc.stdin.write('drc check\n')
        drcproc.stdin.write('drc catchup\n')
        drcproc.stdin.write('set dcount [drc list count total]\n')
        drcproc.stdin.write('puts stdout "drc = $dcount"\n')
        drcproc.stdin.write('set outfile [open "magic_drc.out" w+]\n')
        drcproc.stdin.write('set drc_why [drc listall why]\n')
        drcproc.stdin.write('puts stdout $drc_why\n')
        drcproc.stdin.write('foreach x $drc_why {\n')
        drcproc.stdin.write('   puts $outfile $x\n')
        drcproc.stdin.write('   puts stdout $x\n')
        drcproc.stdin.write('}\n')
        outlines = drcproc.communicate()[0]
        retcode = drcproc.returncode

        if retcode != 0:
            resultdict = incompleteresult(param)
        else:
            resultdict = {}

        magrex = re.compile('drc[ \t]+=[ \t]+([0-9.]+)[ \t]*$')
        for line in outlines.splitlines():
            # Diagnostic
            dbg(line)   # TODO file
            lmatch = magrex.match(line)
            if lmatch:
                drccount = int(lmatch.group(1))
                if 'spec' in param:
                    spec = param['spec']
                else:
                    spec = {}

                if 'maximum' in spec:
                    spectype = 'maximum'
                    maxrec = spec['maximum']
                    maxresult = find_limits(
                        spectype, maxrec, [drccount], '', debug
                    )
                    if maxresult[1] == 'fail':
                        score = 'fail'
                    resultdict['maximum'] = maxresult

        return resultdict

    def run_invalid_device_check(self, datasheet):
        """
        Run the invalid device check on a schematic.  This is used in place of
        LVS when only a schematic exists.
        """

        runtime_options = datasheet['runtime_options']
        debug = runtime_options['debug']
        if 'keep' in runtime_options:
            keep = runtime_options['keep']
        else:
            keep = False
        projname = datasheet['name']
        paths = datasheet['paths']
        namespace = self.get_magic_namespace(datasheet)
        pdk_root = get_pdk_root()
        pdk = datasheet['PDK']
        pdk_path = os.path.join(pdk_root, pdk)

        schem_netlist = None
        if 'netlist' in paths:
            schem_netlist_path = os.path.join(paths['netlist'], 'schematic')
            schem_netlist = os.path.join(
                schem_netlist_path, projname + '.spice'
            )

        dbg('Invalid device check diagnostic:')
        dbg('Schematic netlist path is ' + schem_netlist_path)
        dbg('Schematic netlist is ' + schem_netlist)

        if not schem_netlist:
            return -1
        else:
            faillines = netlist_precheck(
                schem_netlist, pdk_path, namespace, keep
            )
            return len(faillines)

    def run_and_analyze_lvs(self, datasheet, toolargs=None):
        """
        Run netgen to get an LVS result
        """
        runtime_options = datasheet['runtime_options']
        debug = runtime_options['debug']
        if 'keep' in runtime_options:
            keepmode = runtime_options['keep']
        else:
            keepmode = False

        projname = datasheet['name']
        pdk = datasheet['PDK']

        paths = datasheet['paths']
        root_path = paths['root']

        # Make sure that both netlists exist, or flag a warning.

        schem_netlist = None
        layout_netlist = None
        verilog_netlist = None

        if 'netlist' in paths:
            layout_netlist_path = os.path.join(paths['netlist'], 'layout')
            layout_netlist = os.path.join(
                layout_netlist_path, projname + '.spice'
            )

            schem_netlist_path = os.path.join(paths['netlist'], 'schematic')
            schem_netlist = os.path.join(
                schem_netlist_path, projname + '.spice'
            )

        if 'verilog' in paths:
            verilog_path = paths['verilog']
            verilog_netlist = os.path.join(verilog_path, projname + '.v')

        reports_path = paths.get('reports', self.param_dir)

        if not os.path.isdir(reports_path):
            os.makedirs(reports_path)

        testbenchpath = paths.get('testbench', None)
        scriptspath = paths.get('scripts', None)

        if not layout_netlist or not os.path.isfile(layout_netlist):
            err('Layout-extracted netlist does not exist. Cannot run LVS')
            return 'failure'
        if not schem_netlist or not os.path.isfile(schem_netlist):
            if not verilog_netlist or not os.path.isfile(verilog_netlist):
                err(
                    'Schematic-captured netlist does not exist. Cannot run LVS'
                )
                return 'failure'
            else:
                schem_arg = verilog_netlist + ' ' + projname
        else:
            schem_arg = schem_netlist + ' ' + projname

        # Check the netlist to see if the cell to match is a subcircuit.  If
        # not, then assume it is the top level.

        is_subckt = False
        subrex = re.compile(
            '^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
        )
        with open(layout_netlist) as ifile:
            spitext = ifile.read()

        dutlines = spitext.replace('\n+', ' ').splitlines()
        for line in dutlines:
            lmatch = subrex.match(line)
            if lmatch:
                subname = lmatch.group(1)
                if subname.lower() == projname.lower():
                    is_subckt = True
                    break

        if is_subckt:
            layout_arg = layout_netlist + ' ' + projname
        else:
            layout_arg = layout_netlist

        lvs_setup = get_netgen_setupfile(datasheet)

        # Run LVS as a subprocess and wait for it to finish.  Use the -json
        # switch to get a file that is easy to parse.

        dbg(toolargs)
        dbg(testbenchpath)
        if toolargs:
            if not isinstance(toolargs, list):
                toolargs = [toolargs]

        outfilename = projname + '_comp.out'
        outfilepath = os.path.join(self.param_dir, outfilename)
        jsonfilename = projname + '_comp.json'
        jsonfilepath = os.path.join(self.param_dir, jsonfilename)

        if toolargs:
            lvsargs = ['netgen', '-batch', 'source']
            if scriptspath:
                lvsargs.append(
                    os.path.abspath(os.path.join(scriptspath, toolargs[0]))
                )
            elif testbenchpath:
                lvsargs.append(
                    os.path.abspath(os.path.join(testbenchpath, toolargs[0]))
                )
            else:
                lvsargs.append(
                    os.path.abspath(
                        os.path.join(
                            paths['root'], 'cace/scripts', toolargs[0]
                        )
                    )
                )
            if len(toolargs) > 1:
                lvsargs.extend(toolargs[1:])
            dbg('cace_evaluate.py:  running ' + ' '.join(lvsargs))
        else:
            lvsargs = ['netgen', '-batch', 'lvs']
            lvsargs.extend(layout_arg)
            lvsargs.extend(schem_arg)
            lvsargs.append(lvs_setup)
            lvsargs.append(outfilepath)
            lvsargs.append('-json')

            dbg('cace_evaluate.py:  running ' + ' '.join(lvsargs))
        dbg(os.getcwd())
        newenv = os.environ.copy()
        pdk_root = get_pdk_root()
        if pdk_root and 'PDK_ROOT' not in newenv:
            newenv['PDK_ROOT'] = pdk_root
        if pdk and 'PDK' not in newenv:
            newenv['PDK'] = pdk

        with subprocess.Popen(
            lvsargs,
            cwd=self.param_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=newenv,
        ) as lvsproc:
            pgroup = os.getpgid(lvsproc.pid)
            lvsout, lvserr = lvsproc.communicate()
            retcode = lvsproc.returncode
            if retcode != 0:
                err('Netgen exited with error code ' + str(retcode))
                return 'failure'

            if lvserr:
                err('Error output generated by netgen:')
                for line in lvserr.splitlines():
                    err(line.rstrip('\n'))
                    sys.stdout.flush()
            if lvsout:
                dbg('Output from netgen:')
                for line in lvsout.splitlines():
                    dbg(line.rstrip())
                    try:
                        pline = line.decode('ascii')
                        if 'Logging to file' in pline:
                            outfilepath = pline.split()[3].strip('"')
                            # TODO really necessary to change again?
                            jsonfilepath = os.path.join(
                                self.param_dir,
                                os.path.splitext(outfilepath)[0] + '.json',
                            )
                    except:
                        # Might happen if non-ASCII characters are output from netgen
                        err('Unexpected output from netgen: ' + pline)

        if not os.path.isfile(jsonfilepath):
            err('No output JSON file generated by netgen!')
            err('Expected file: ' + jsonfilepath)
            return 'failure'

        # To do:  Check that file is not stale

        with open(jsonfilepath, 'r') as cfile:
            lvsdata = json.load(cfile)

        # Count errors in the JSON file
        failures = 0
        ncells = len(lvsdata)
        for c in range(0, ncells):
            cellrec = lvsdata[c]
            if c == ncells - 1:
                topcell = True
            else:
                topcell = False

            # Most errors must only be counted for the top cell, because individual
            # failing cells are flattened and the matching attempted again on the
            # flattened netlist.

            if topcell:
                if 'devices' in cellrec:
                    devices = cellrec['devices']
                    devlist = [
                        val
                        for pair in zip(devices[0], devices[1])
                        for val in pair
                    ]
                    devpair = list(
                        devlist[p : p + 2] for p in range(0, len(devlist), 2)
                    )
                    for dev in devpair:
                        c1dev = dev[0]
                        c2dev = dev[1]
                        diffdevs = abs(c1dev[1] - c2dev[1])
                        failures += diffdevs

                if 'nets' in cellrec:
                    nets = cellrec['nets']
                    diffnets = abs(nets[0] - nets[1])
                    failures += diffnets

                if 'badnets' in cellrec:
                    badnets = cellrec['badnets']
                    failures += len(badnets)

                if 'badelements' in cellrec:
                    badelements = cellrec['badelements']
                    failures += len(badelements)

                if 'pins' in cellrec:
                    pins = cellrec['pins']
                    pinlist = [
                        val for pair in zip(pins[0], pins[1]) for val in pair
                    ]
                    pinpair = list(
                        pinlist[p : p + 2] for p in range(0, len(pinlist), 2)
                    )
                    for pin in pinpair:
                        if pin[0].lower() != pin[1].lower():
                            failures += 1

            # Property errors must be counted for every cell
            if 'properties' in cellrec:
                properties = cellrec['properties']
                failures += len(properties)

        # Remove temporary files if '-keep' was not specified
        if not keepmode:
            if os.path.exists('lvs_batch_script.tcl'):
                os.remove('lvs_batch_script.tcl')

        return failures

    def cace_lvs(self, datasheet, param, toolargs=None):
        """
        Run netgen to get an LVS result
        """

        runtime_options = datasheet['runtime_options']
        debug = runtime_options['debug']

        source = runtime_options['netlist_source']
        if source == 'schematic':
            info('Running invalid device check.')
            # LVS cannot be run on a schematic, so run the invalid device check
            failures = self.run_invalid_device_check(datasheet)
        else:
            info('Running netgen to get LVS report.')
            failures = self.run_and_analyze_lvs(datasheet, toolargs)

        if isinstance(failures, list):
            err(
                'Unknown result from LVS or device check analysis:'
                + str(failures)
            )
            failures = 'failure'
        elif isinstance(failures, str) and failures != 'failure':
            try:
                failures = int(failures)
            except:
                err(
                    'Unknown result from LVS or device check analysis:'
                    + failures
                )
                failures = 'failure'

        if failures == 'failure':
            resultdict = incompleteresult(param)
        elif failures < 0:
            resultdict = incompleteresult(param)
        else:
            resultdict = {}

        if 'spec' in param:
            spec = param['spec']
        else:
            spec = {}

        if 'maximum' in spec:
            spectype = 'maximum'
            maxrec = spec['maximum']
            maxresult = find_limits(spectype, maxrec, [failures], '', debug)
            if maxresult[1] == 'fail':
                score = 'fail'
            resultdict['maximum'] = maxresult

        return resultdict

    def cace_evaluate(self, datasheet, param):
        """
        Main entrypoint of cace_evaluate

        "datasheet" is the CACE characterization dataset.
        "param" is the dictionary for a single physical parameter.
        """

        runtime_options = datasheet['runtime_options']
        netlist_source = runtime_options['netlist_source']
        debug = runtime_options['debug']

        if 'status' in param:
            status = param['status']
        else:
            status = 'active'
            param['status'] = status

        paramname = param['name']

        if status == 'skip' or status == 'blocked':
            info('Parameter ' + paramname + ' is marked for skipping.')
            return param

        info('Checking physical parameter ' + paramname)

        if 'evaluate' not in param:
            err('Parameter ' + paramname + ' has no evaluator!')
            return param

        evaluator = param['evaluate']

        # Simplification:  evaluator is just a string or list, not a dictionary.
        # This is for when it has only one entry.  Likewise, if the evaluator
        # is a dictionary but entry "tool" is only a single procedure, then it
        # will be a string and should be cast into a list.

        if isinstance(evaluator, dict):
            tool = evaluator['tool']
        else:
            tool = evaluator

        if isinstance(tool, list):
            toolargs = tool[1:]
            tool = tool[0]
        else:
            toolargs = None

        if tool == 'cace_area':
            resultdict = self.cace_area(datasheet, param, 'area', toolargs)
        elif tool == 'cace_width':
            resultdict = self.cace_area(datasheet, param, 'width', toolargs)
        elif tool == 'cace_height':
            resultdict = self.cace_area(datasheet, param, 'height', toolargs)
        elif tool == 'cace_drc':
            resultdict = self.cace_drc(datasheet, param, toolargs)
        elif tool == 'cace_lvs':
            resultdict = self.cace_lvs(datasheet, param, toolargs)
        else:
            err('Unknown evaluation procedure ' + tool + ';  not evaluating.')
            return param

        resultdict['name'] = runtime_options['netlist_source']
        addnewresult(param, resultdict)

        return param
