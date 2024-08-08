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

from ..common.common import run_subprocess, get_magic_rcfile
from ..common.ring_buffer import RingBuffer
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


@register_parameter('magic_area')
class ParameterMagicArea(Parameter):
    """
    Determine bounds of the design geometry

    "cond" should be one of "area", "width", or "height", and determines
    what value is returned by the routine.

    The routine reads the .mag or .gds file of the layout and returns
    the width and height values in microns.  This is captured from
    standard output and the requested result returned to the calling
    routine.

    """

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        self.cond = 'area'

        super().__init__(
            *args,
            **kwargs,
        )

        self.add_argument(Argument('args', [], False))

    def is_runnable(self):
        netlist_source = self.runtime_options['netlist_source']

        if netlist_source == 'schematic':
            info(
                'Netlist source is schematic capture. Not running area measurements.'
            )
            self.result['type'] = ResultType.SKIPPED
            return False

        return True

    def implementation(self):

        self.cancel_point()

        # Acquire a job from the global jobs semaphore
        with self.jobs_sem:

            info(f'Running magic to get {self.cond} measurements.')

            projname = self.datasheet['name']
            paths = self.datasheet['paths']

            rcfile = get_magic_rcfile()

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

            # Run magic to get the bounds of the design geometry
            # Get triplet of area, width, and height

            is_mag = (
                True
                if os.path.splitext(layout_filename)[1] == '.mag'
                else False
            )
            layout_path = os.path.split(layout_filename)[0]
            layout_locname = os.path.split(layout_filename)[1]
            layout_cellname = os.path.splitext(layout_locname)[0]

            if not os.path.exists(layout_filename):
                err(f'Layout {layout_filename} does not exist!')

            magic_input = ''

            magic_input += f'addpath {os.path.abspath(layout_path)}\n'
            if is_mag:
                magic_input += f'load {layout_cellname}\n'
            else:
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

            magic_input += 'select top cell\n'
            magic_input += 'box\n'
            magic_input += 'quit -noprompt\n'

            returncode = self.run_subprocess(
                'magic',
                ['-dnull', '-noconsole', '-rcfile', rcfile]
                + self.get_argument('args'),
                input=magic_input,
                cwd=self.param_dir,
            )

            if returncode != 0:
                err('Magic exited with non-zero return code!')

            magrex = re.compile(
                'microns:[ \t]+([0-9.]+)[ \t]*x[ \t]*([0-9.]+)[ \t]+.*[ \t]+([0-9.]+)[ \t]*$'
            )

            with open(
                f'{os.path.join(self.param_dir, "magic")}_stdout.out', 'r'
            ) as stdout_file:

                for line in stdout_file.readlines():
                    lmatch = magrex.match(line)
                    if lmatch:
                        widthval = float(lmatch.group(1)) / 1000_000
                        heightval = float(lmatch.group(2)) / 1000_000
                        areaval = float(lmatch.group(3)) / 1000_000 / 1000_000

            if areaval == 0:
                resultdict = incompleteresult(self.param)
            else:
                if self.cond == 'height':
                    resultlist = [heightval]
                elif self.cond == 'width':
                    resultlist = [widthval]
                else:
                    resultlist = [areaval]

        self.result['type'] = ResultType.SUCCESS
        self.result['values'] = resultlist

        if self.step_cb:
            self.step_cb(self.param)


@register_parameter('magic_width')
class ParameterMagicWidth(ParameterMagicArea):
    """ """

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.cond = 'width'


@register_parameter('magic_height')
class ParameterMagicHeight(ParameterMagicArea):
    """ """

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.cond = 'height'
