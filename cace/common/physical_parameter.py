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

from .cace_evaluate import *


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

        # TODO Create netlists

        self.cancel_point()
        
        print(f'Evaluating physical parameter: {self.param["name"]}')
        cace_evaluate(self.datasheet, self.param)

        if self.cb:
            self.cb(self.param['name'])

    def cancel(self, cancel_cb):
        print(f'Cancel physical parameter: {self.param["name"]}')
        self.canceled = True

        if cancel_cb:
            self.cb = None

    def cancel_point(self):
        """If canceled, call the cb and exit the thread"""

        if self.canceled:
            self.cb(self.param['name'], True)
            sys.exit()
