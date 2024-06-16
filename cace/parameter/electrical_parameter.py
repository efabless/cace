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
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool

from ..common.cace_gensim import *
from ..common.cace_collate import *
from ..common.cace_makeplot import *

from .simulation_job import SimulationJob

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


class ElectricalParameter(Parameter):
    """
    The ElectricalParameter simulates an electrical parameter
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
        self.queued_jobs = []
        self.new_testbenches = []

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

    def cancel(self, no_cb):
        super().cancel(no_cb)

        for job in self.queued_jobs:
            job.cancel(no_cb)

    def implementation(self):

        # Something went wrong in preprocess
        # better abort early
        if not self.get_num_steps():
            err(f'Parameter {self.param["name"]}: Error in preprocess')
            self.cancel(False)

        self.cancel_point()

        # Run simulation jobs sequentially
        if self.runtime_options['sequential']:

            for job in self.queued_jobs:
                info(
                    f'Parameter {self.param["name"]}: Starting task with id {job.idx}'
                )

                # Start simulation job as single thread
                job.start()
                presult = job.join()

                self.cancel_point()

                if presult:
                    self.new_testbenches[presult['sequence']] = presult

                """if self.step_cb:
                    self.step_cb(self.param)"""

            dbg(f'Parameter {self.param["name"]}: All tasks done')

        # Run simulation jobs in parallel
        else:
            with ThreadPool(processes=max(cpu_count() - 1, 1)) as mypool:

                # Start the jobs
                jobs = []
                for job in self.queued_jobs:
                    info(
                        f'Parameter {self.param["name"]}: Starting task with id {job.idx}'
                    )
                    jobs.append(mypool.apply_async(job.run))

                # Wait for completion
                while 1:
                    self.cancel_point()

                    # Check if all tasks have completed
                    if all([job.ready() for job in jobs]):
                        dbg(f'Parameter {self.param["name"]}: All tasks done')
                        break

                    time.sleep(0.1)

                # Get the restuls
                for job in jobs:
                    presult = job.get()

                    if presult:

                        # TODO make testbench name the key for easier access
                        self.new_testbenches[presult['sequence']] = presult

                jobs = []

        self.cancel_point()

        # Check whether testbenches are valid
        for testbench in self.new_testbenches:
            if not testbench:
                err(f'{self.param["name"]}: At least one testbench is invalid')
                self.param['results'] = None

                # Just cancel on error
                self.cancel(False)
                self.cancel_point()

        # Assign the new testbenches to the parameter
        # (cancel is not possible anymore)
        self.param['testbenches'] = self.new_testbenches

    def add_simulation_job(self, job):
        self.queued_jobs.append(job)

    # Preprocess: create netlists and testbenches
    # TODO: removes results from testbenches
    # this is a problem when a testbench is canceled
    def preprocess(self):

        dbg(f'Parameter {self.param["name"]}: Generating simulation files')

        # Generate the spice netlists for simulation from the template
        cace_gensim(self.datasheet, self.param, self.param_dir)

        # Diagnostic:  find and print the number of files to be simulated
        # Names are methodname, pinname, and simulation number.
        totalsims = 0
        if 'testbenches' in self.param:
            totalsims += len(self.param['testbenches'])
            dbg(
                f'Parameter {self.param["name"]}: Total files to simulate: {str(totalsims)}'
            )
        else:
            warn(
                f'Parameter {self.param["name"]}: Skipping (no testbenches to simulate)'
            )
            return

        # Determine if testbenches are collated, and so need to be
        # simulated in groups
        idx = 0
        simdict = self.param['simulate']
        if 'group_size' in simdict:
            group_size = simdict['group_size']
        else:
            group_size = 1

        # Track how many simulations were successful
        simulations = 0

        testbenches = self.param['testbenches']
        paramname = self.param['name']

        alltestbenches = []
        results = []

        # Create an empty testbench list to hold
        # the testbenches that are returned
        self.new_testbenches = []

        for i in range(0, len(testbenches), group_size):
            testbenchlist = testbenches[i : i + group_size]
            for testbench in testbenchlist:
                testbench['sequence'] = idx

            new_sim_job = SimulationJob(
                self.param,
                testbenchlist,
                self.pdk,
                self.paths,
                self.runtime_options,
                self.param_dir,
                self.step_cb,
                idx,
            )
            self.add_simulation_job(new_sim_job)

            # Append an empty testbench
            self.new_testbenches.append([None])

            idx += 1

    def postprocess(self):

        if 'plot' in self.param:
            dbg(f'Parameter {self.param["name"]}: Plotting results')

            info(
                f'Parameter {self.param["name"]}: Plotting to \'[repr.filename][link=file://{os.path.abspath(self.plot_dir)}]{os.path.relpath(self.plot_dir)}[/link][/repr.filename]\'…'
            )

            cace_makeplot(self.datasheet, self.param, self.plot_dir)

        if 'spec' in self.param:
            dbg(f'Parameter {self.param["name"]}: Collating results')
            self.param = cace_collate(self.datasheet, self.param)

    def get_num_steps(self):
        if 'testbenches' in self.param:
            return len(self.param['testbenches'])
        else:
            return None
