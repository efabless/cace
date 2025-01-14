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

from ..common.common import (
    run_subprocess,
    get_netgen_setupfile,
)

from .parameter import Parameter, ResultType, Argument, Result

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

from .parameter_manager import register_parameter


@register_parameter('netgen_lvs')
class ParameterNetgenLVS(Parameter):
    """
    Run LVS using netgen
    """

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.add_result(Result('lvs_errors'))

        self.add_argument(Argument('args', [], False))
        self.add_argument(Argument('script', None, False))

    def is_runnable(self):
        netlist_source = self.runtime_options['netlist_source']

        if netlist_source == 'schematic':
            info('Netlist source is schematic capture. Not running LVS.')
            self.result_type = ResultType.SKIPPED
            return False

        return True

    def implementation(self):

        self.cancel_point()

        # Acquire a job from the global jobs semaphore
        with self.jobs_sem:

            info('Running netgen to get LVS report.')

            projname = self.datasheet['name']
            paths = self.datasheet['paths']
            root_path = self.paths['root']

            # Make sure that both netlists exist, or flag a warning.

            schem_netlist = None
            layout_netlist = None
            verilog_netlist = None

            if 'netlist' in paths:
                layout_netlist_path = os.path.join(paths['netlist'], 'layout')
                layout_netlist = os.path.join(
                    layout_netlist_path, projname + '.spice'
                )
                layout_netlist = os.path.abspath(layout_netlist)

                schem_netlist_path = os.path.join(
                    paths['netlist'], 'schematic'
                )
                schem_netlist = os.path.join(
                    schem_netlist_path, projname + '.spice'
                )
                schem_netlist = os.path.abspath(schem_netlist)

            if 'verilog' in paths:
                verilog_path = paths['verilog']
                verilog_netlist = os.path.join(verilog_path, projname + '.v')
                verilog_netlist = os.path.abspath(verilog_netlist)

            scriptspath = paths.get('scripts')

            if not layout_netlist or not os.path.isfile(layout_netlist):
                err('Layout-extracted netlist does not exist. Cannot run LVS')
                self.result_type = ResultType.ERROR
                return

            if not schem_netlist or not os.path.isfile(schem_netlist):
                if not verilog_netlist or not os.path.isfile(verilog_netlist):
                    err(
                        'Schematic-captured netlist does not exist. Cannot run LVS'
                    )
                    self.result_type = ResultType.ERROR
                    return
                else:
                    schem_arg = verilog_netlist + ' ' + projname
            else:
                schem_arg = schem_netlist + ' ' + projname

            # Check the netlist to see if the cell to match is a subcircuit.  If
            # not, then assume it is the top level.

            is_subckt = False
            subrex = re.compile(
                r'^[^\*]*[ \t]*.subckt[ \t]+([^ \t]+).*$', re.IGNORECASE
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

            lvs_setup = get_netgen_setupfile()

            # Run LVS as a subprocess and wait for it to finish.  Use the -json
            # switch to get a file that is easy to parse.

            outfilename = projname + '_comp.out'
            outfilepath = os.path.join(self.param_dir, outfilename)
            jsonfilename = projname + '_comp.json'
            jsonfilepath = os.path.join(self.param_dir, jsonfilename)

            if self.get_argument('script'):
                lvsargs = ['-batch', 'source']

                # Use the custom script
                lvsargs.append(
                    os.path.abspath(
                        os.path.join(scriptspath, self.get_argument('script'))
                    )
                )

            else:
                lvsargs = ['-batch', 'lvs']
                lvsargs.append(layout_arg)
                lvsargs.append(schem_arg)
                lvsargs.append(lvs_setup)
                lvsargs.append(outfilepath)
                lvsargs.append('-json')

            lvsargs.extend(self.get_argument('args'))

            returncode = self.run_subprocess(
                'netgen', lvsargs, cwd=self.param_dir
            )

            if not os.path.isfile(jsonfilepath):
                err('No output JSON file generated by netgen!')
                err(f'Expected file: {jsonfilepath}')
                self.result_type = ResultType.ERROR
                return

            if not os.path.isfile(outfilepath):
                err('No output text file generated by netgen!')
                err(f'Expected file: {outfilepath}')
                self.result_type = ResultType.ERROR
                return

            info(
                f"Netgen LVS report at '[repr.filename][link=file://{os.path.abspath(outfilepath)}]{os.path.relpath(outfilepath)}[/link][/repr.filename]'…"
            )

        if self.step_cb:
            self.step_cb(self.param)

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

            if isinstance(failures, list):
                err(
                    f'Unknown result from LVS or device check analysis: {failures}'
                )
                self.result_type = ResultType.ERROR
                return
            elif isinstance(failures, str) and failures != 'failure':
                try:
                    failures = int(failures)
                except:
                    err(
                        f'Unknown result from LVS or device check analysis: {failures}'
                    )
                    self.result_type = ResultType.ERROR
                    return

        self.result_type = ResultType.SUCCESS
        self.get_result('lvs_errors').values = [failures]
