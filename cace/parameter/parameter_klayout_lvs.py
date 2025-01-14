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

from ..common.common import run_subprocess, get_pdk_root, get_layout_path

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


@register_parameter('klayout_lvs')
class ParameterKLayoutLVS(Parameter):
    """
    Run LVS using KLayout
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

            info('Running KLayout to get LVS report.')

            projname = self.datasheet['name']
            paths = self.datasheet['paths']
            root_path = self.paths['root']

            # Make sure that schematic netlist exist,
            schem_netlist = None

            if 'netlist' in paths:
                schem_netlist_path = os.path.join(
                    paths['netlist'], 'schematic'
                )
                schem_netlist = os.path.join(
                    schem_netlist_path, projname + '.spice'
                )
                schem_netlist = os.path.abspath(schem_netlist)

            if not schem_netlist or not os.path.isfile(schem_netlist):
                err(
                    'Schematic-captured netlist does not exist. Cannot run LVS'
                )
                self.result_type = ResultType.ERROR
                return

            # Get the path to the layout, only GDS
            (layout_filepath, is_magic) = get_layout_path(
                projname, self.paths, check_magic=False
            )

            # Check if layout exists
            if not os.path.isfile(layout_filepath):
                err('No layout found!')
                self.result_type = ResultType.ERROR
                return

            if self.get_argument('script'):
                    lvs_script_path = os.path.abspath(
                        os.path.join(scriptspath, self.get_argument('script'))
                    )
            else:
                lvs_script_path = os.path.join(
                    get_pdk_root(),
                    self.datasheet['PDK'],
                    'libs.tech',
                    'klayout',
                    'lvs',
                    'sky130.lvs',
                )

            if not os.path.exists(lvs_script_path):
                err(f'LVS script {lvs_script_path} does not exist!')
                self.result_type = ResultType.ERROR
                return

            report_file_path = os.path.join(self.param_dir, f'{projname}.lvsdb')

            # PDK specific arguments
            if self.datasheet['PDK'].startswith('sky130'):
                arguments = [
                    '-b',
                    '-r',
                    lvs_script_path,
                    '-rd',
                    f'input={os.path.abspath(layout_filepath)}',
                    '-rd',
                    f'top_cell={projname}',
                    '-rd',
                    f'schematic={schem_netlist}',
                    '-rd',
                    f'report={report_file_path}',
                    '-rd',
                    f'report={report_file_path}',
                    '-rd',
                    f'target_netlist={os.path.abspath(os.path.join(self.param_dir, projname + ".cir"))}',
                    '-rd',
                    f'thr={os.cpu_count()}',  # TODO how to distribute cores?
                ]

            returncode = self.run_subprocess(
                'klayout',
                arguments + self.get_argument('args'),
                cwd=self.param_dir,
            )

            if not os.path.isfile(report_file_path):
                err('No output file generated by KLayout!')
                err(f'Expected file: {report_file_path}')
                self.result_type = ResultType.ERROR
                return

            info(
                f"KLayout LVS report at '[repr.filename][link=file://{os.path.abspath(report_file_path)}]{os.path.relpath(report_file_path)}[/link][/repr.filename]'…"
            )

        # Advance progress bar
        if self.step_cb:
            self.step_cb(self.param)

        # Match for errors in the .lvsdb file
        lvsrex = re.compile(r"M\(E B\('.*'\)\)")

        # Get the result
        try:
            with open(report_file_path) as klayout_xml_report:
                size = os.fstat(klayout_xml_report.fileno()).st_size
                if size == 0:
                    err(f'File {report_file_path} is of size 0.')
                    self.result_type = ResultType.ERROR
                    return
                lvs_content = klayout_xml_report.read()
                lvs_count = len(lvsrex.findall(lvs_content))

                self.result_type = ResultType.SUCCESS
                self.get_result('lvs_errors').values = [lvs_count]
                return

        # Catch reports not found
        except FileNotFoundError as e:
            err(f'Failed to generate {report_file_path}: {e}')
            self.result_type = ResultType.ERROR
            return
        except (IOError, OSError) as e:
            err(f'Failed to generate {report_file_path}: {e}')
            self.result_type = ResultType.ERROR
            return
