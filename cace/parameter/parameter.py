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
from abc import abstractmethod, ABC
from threading import Thread
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool

from ..common.misc import mkdirp
from ..logging import (
    info,
    warn,
    verbose,
)


class Parameter(ABC, Thread):
    """
    Base class for all electrical and physical parameters.
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
        self.param = param
        self.datasheet = datasheet
        self.pdk = pdk
        self.paths = paths
        self.runtime_options = runtime_options
        self.run_dir = run_dir
        self.start_cb = start_cb
        self.end_cb = end_cb
        self.cancel_cb = cancel_cb
        self.step_cb = step_cb

        self.result = {}

        self.canceled = False
        self.done = False

        super().__init__(*args, **kwargs)

        # Create new parameter dir
        self.param_dir = os.path.abspath(
            os.path.join(self.run_dir, 'parameters', self.param['name'])
        )

        info(f'Creating directory: {self.param_dir}.')
        mkdirp(self.param_dir)

    def cancel(self, no_cb):
        info(f'Parameter {self.param["name"]}: Canceled')
        self.canceled = True

        if no_cb:
            self.cancel_cb = None

    def cancel_point(self):
        """If canceled, call the cancel cb and exit the thread"""

        if self.canceled:
            if self.cancel_cb:
                self.cancel_cb(self.param['name'])
            sys.exit()

    def run(self):

        info(f'Parameter {self.param["name"]}: Started')

        self.cancel_point()

        self.cancel_point()

        if self.start_cb:
            self.start_cb(self.param['name'])

        self.preprocess()

        self.cancel_point()

        self.implementation()

        self.cancel_point()

        self.postprocess()

        # Set done before calling end cb
        self.done = True

        if self.end_cb:
            self.end_cb(self.param['name'])

        info(f'Parameter {self.param["name"]}: Completed')

        return self.result

    @abstractmethod
    def implementation(self):
        pass

    @abstractmethod
    def preprocess(self):
        pass

    @abstractmethod
    def postprocess(self):
        pass
