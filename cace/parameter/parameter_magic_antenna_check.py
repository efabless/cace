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

from ..common.common import run_subprocess, get_magic_rcfile, get_layout_path
from ..common.ring_buffer import RingBuffer
from .parameter import Parameter, ResultType, Argument, Result
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


@register_parameter('magic_antenna_check')
class ParameterMagicAntennaCheck(Parameter):
    """
    Perform the magic antenna check to
    find antenna violations in the layout.
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

        self.add_result(Result('antenna_violations'))

        self.add_argument(Argument('args', [], False))

    def is_runnable(self):
        netlist_source = self.runtime_options['netlist_source']

        if netlist_source == 'schematic':
            info(
                'Netlist source is schematic capture. Not checking antenna violations measurements.'
            )
            self.result_type = ResultType.SKIPPED
            return False

        return True

    def implementation(self):

        self.cancel_point()

        # Acquire a job from the global jobs semaphore
        with self.jobs_sem:

            info(f'Running magic to check for antenna violations.')

            projname = self.datasheet['name']
            paths = self.datasheet['paths']

            rcfile = get_magic_rcfile()

            # Get the path to the layout, prefer magic
            (layout_filepath, is_magic) = get_layout_path(
                projname, self.paths, check_magic=True
            )

            # Check if layout exists
            if not os.path.isfile(layout_filepath):
                err('No layout found!')
                self.result_type = ResultType.ERROR
                return

            # Run magic to get the antenna violations

            magic_input = ''

            magic_input += 'crashbackups stop\n'   # no periodic saving
            magic_input += 'drc off\n'   # turn off background checker
            magic_input += 'snap internal\n'   # select internal grid

            if is_magic:
                magic_input += f'path search +{os.path.abspath(os.path.dirname(layout_filepath))}\n'
                magic_input += f'load {os.path.basename(layout_filepath)}\n'
            else:
                magic_input += f'gds read {os.path.abspath(layout_filepath)}\n'
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
            magic_input += 'expand\n'
            magic_input += 'extract do local\n'
            magic_input += 'extract no all\n'
            magic_input += 'extract all\n'
            magic_input += 'antennacheck debug\n'
            magic_input += 'antennacheck\n'
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

        magrex = re.compile('Antenna violation detected')
        stderr_filepath = os.path.join(self.param_dir, 'magic_stderr.out')
        violations = 0

        # Check if stderr exists, else no violations occurred
        if os.path.isfile(stderr_filepath):
            with open(stderr_filepath, 'r') as stdout_file:
                # Count the violations
                for line in stdout_file.readlines():
                    lmatch = magrex.match(line)
                    if lmatch:
                        violations += 1

        self.result_type = ResultType.SUCCESS
        self.get_result('antenna_violations').values = [violations]

        # Increment progress bar
        if self.step_cb:
            self.step_cb(self.param)
