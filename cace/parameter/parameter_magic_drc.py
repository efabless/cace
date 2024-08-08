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

from ..common.common import run_subprocess, get_magic_rcfile
from .parameter import Parameter, ResultType, Argument
from .parameter_manager import register_parameter
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


@register_parameter('magic_drc')
class ParameterMagicDRC(Parameter):
    """
    Run magic drc
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

        self.add_argument(Argument('args', [], False))
        self.add_argument(Argument('gds_flatten', False, False))

    def is_runnable(self):
        netlist_source = self.runtime_options['netlist_source']

        if netlist_source == 'schematic':
            info('Netlist source is schematic capture. Not running DRC.')
            self.result['type'] = ResultType.SKIPPED
            return False

        return True

    def implementation(self):

        self.cancel_point()

        # Acquire a job from the global jobs semaphore
        with self.jobs_sem:

            """
            Run magic to get a DRC report
            """

            projname = self.datasheet['name']
            paths = self.datasheet['paths']

            info('Running magic to get layout DRC report.')

            # Find the layout directory and check if there is a layout
            # for the cell there.

            layout_filename = None
            is_mag = False

            # Prefer magic layout
            if 'magic' in paths:
                magic_path = paths['magic']
                magicname = projname + '.mag'
                layout_filename = os.path.join(magic_path, magicname)
                is_mag = True
            # Else use GDSII
            elif 'layout' in paths:
                layout_path = paths['layout']
                layoutname = projname + '.gds'
                layout_filename = os.path.join(layout_path, layoutname)
                # Search for compressed layout
                if not os.path.exists(layout_filename):
                    layoutname = projname + '.gds.gz'
                    layout_filename = os.path.join(layout_path, layoutname)
            else:
                err(
                    'Neither "magic" nor "layout" specified in datasheet paths.'
                )
                self.result['type'] = ResultType.ERROR
                return

            # Check if layout exists
            if not os.path.isfile(layout_filename):
                err('No layout found!')
                err(f'Expected file: {layout_filename}')
                self.result['type'] = ResultType.ERROR
                return

            layout_path = os.path.split(layout_filename)[0]
            layout_locname = os.path.split(layout_filename)[1]
            layout_cellname = os.path.splitext(layout_locname)[0]

            rcfile = get_magic_rcfile()

            magic_input = ''

            magic_input += f'addpath {os.path.abspath(layout_path)}\n'
            if is_mag:
                magic_input += f'load {layout_cellname}\n'
            else:
                if self.get_argument('gds_flatten'):
                    magic_input += 'gds flatglob *\n'
                magic_input += f'gds read {layout_locname}\n'
                magic_input += 'set toplist [cellname list top]\n'
                magic_input += 'set numtop [llength $toplist]\n'
                magic_input += 'if {$numtop > 1} {\n'
                magic_input += '   foreach topcell $toplist {\n'
                magic_input += '      if {$topcell != "(UNNAMED)"} {\n'
                magic_input += '         load $topcell\n'
                magic_input += '         break\n'
                magic_input += '      }\n'
                magic_input += '   }\n'
                magic_input += '}\n'

            magic_input += 'drc on\n'
            magic_input += 'catch {drc style drc(full)}\n'
            magic_input += 'select top cell\n'
            magic_input += 'drc check\n'
            magic_input += 'drc catchup\n'
            magic_input += 'set dcount [drc list count total]\n'
            magic_input += 'puts stdout "drc = $dcount"\n'
            magic_input += 'set outfile [open "magic_drc.out" w+]\n'
            magic_input += 'set drc_why [drc listall why]\n'
            magic_input += 'puts stdout $drc_why\n'
            magic_input += 'foreach x $drc_why {\n'
            magic_input += '   puts $outfile $x\n'
            magic_input += '   puts stdout $x\n'
            magic_input += '}\n'

            returncode = self.run_subprocess(
                'magic',
                ['-dnull', '-noconsole', '-rcfile', rcfile]
                + self.get_argument('args'),
                input=magic_input,
                cwd=self.param_dir,
            )

        if self.step_cb:
            self.step_cb(self.param)

        magrex = re.compile('drc[ \t]+=[ \t]+([0-9.]+)[ \t]*$')

        stdoutfilepath = os.path.join(self.param_dir, 'magic_stdout.out')
        drcfilepath = os.path.join(self.param_dir, 'magic_drc.out')

        if not os.path.isfile(drcfilepath):
            err('No output file generated by magic!')
            err(f'Expected file: {drcfilepath}')
            self.result['type'] = ResultType.ERROR
            return

        info(
            f"Magic DRC report at '[repr.filename][link=file://{os.path.abspath(drcfilepath)}]{os.path.relpath(drcfilepath)}[/link][/repr.filename]'…"
        )

        drccount = None
        with open(stdoutfilepath, 'r') as stdout_file:

            for line in stdout_file.readlines():
                lmatch = magrex.match(line)
                if lmatch:
                    drccount = int(lmatch.group(1))

        self.result['type'] = ResultType.SUCCESS
        self.result['values'] = [drccount]
