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
import threading

from .cace_evaluate import cace_evaluate
from .cace_regenerate import regenerate_netlists


class PhysicalParameter(threading.Thread):
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
        cb=None,
        cb_sims=None,
        *args,
        **kwargs,
    ):
        self.param = param
        self.datasheet = datasheet
        self.cb = cb
        self.cb_sims = cb_sims
        self.pdk = pdk
        self.paths = paths
        self.runtime_options = runtime_options

        self.canceled = False

        super().__init__(*args, **kwargs)

    def run(self):

        self.cancel_point()

        # Start by regenerating the netlists for the circuit-under-test
        # (This may not be quick but all tests depend on the existence
        # of the netlist, so it has to be done here and cannot be
        # parallelized).

        fullnetlistpath = regenerate_netlists(self.datasheet)
        if not fullnetlistpath:
            print(
                f'{self.param["name"]}: Failed to regenerate project netlist; stopping.'
            )
            return 1

        self.cancel_point()

        print(f'{self.param["name"]}: Evaluating physical parameter')
        cace_evaluate(self.datasheet, self.param)

        if self.cb:
            self.cb(self.param['name'])

    def cancel(self, cancel_cb):
        print(f'{self.param["name"]}: Cancel physical parameter')
        self.canceled = True

        if cancel_cb:
            self.cb = None

    def cancel_point(self):
        """If canceled, call the cb and exit the thread"""

        if self.canceled:
            if self.cb:
                self.cb(self.param['name'], True)
            sys.exit()
