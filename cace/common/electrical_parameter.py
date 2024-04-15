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

from .cace_regenerate import *
from .cace_gensim import *
from .cace_collate import *
from .cace_makeplot import *
from .cace_evaluate import *

from .simulation_job import SimulationJob


class ElectricalParameter(threading.Thread):
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

        self.queued_jobs = []
        self.new_testbenches = []
        self.canceled = False

        super().__init__(*args, **kwargs)

    def cancel(self, cancel_cb):
        print(f'Cancel electrical parameter: {self.param["name"]}')
        self.canceled = True

        if cancel_cb:
            self.cb = None

        for sim in self.queued_jobs:
            sim.cancel(cancel_cb)

    def cancel_point(self):
        """If canceled, call the cb and exit the thread"""

        if self.canceled:
            if self.cb:
                self.cb(self.param['name'], True)
            sys.exit()

    def run(self):

        self.cancel_point()

        # Preprocess: create netlists and testbenches
        # TODO: removes results from testbenches
        # this is a problem when a testbench is canceled
        self.preprocess()

        self.cancel_point()

        with ThreadPool(processes=max(cpu_count() - 1, 1)) as mypool:

            # Start the jobs
            jobs = []
            for sim in self.queued_jobs:
                print(f'{self.param["name"]}: Starting task')
                jobs.append(mypool.apply_async(sim.run, callback=self.cb_sims))

            # Wait for completion
            while 1:
                self.cancel_point()

                # Check if all tasks have completed
                if all([job.ready() for job in jobs]):
                    print(f'{self.param["name"]}: All tasks done')
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
                print(
                    f'{self.param["name"]}: Error: At least one testbench is invalid'
                )
                self.cb(self.param['name'])
                return

        # Assign the new testbenches to the parameter
        # (cancel is not possible anymore)
        self.param['testbenches'] = self.new_testbenches

        self.postprocess()

        if self.cb:
            self.cb(self.param['name'])

        print(f'{self.param["name"]}: Completed')

    def add_simulation_job(self, job):
        self.queued_jobs.append(job)

    def preprocess(self):

        # Get the set of paths from the characterization file
        paths = self.datasheet['paths']

        # Simulation path is where the output is dumped.  If it doesn't
        # exist, then create it.
        root_path = paths['root']
        simulation_path = paths['simulation']

        if not os.path.isdir(os.path.join(root_path, simulation_path)):
            print('Creating simulation path ' + simulation_path)
            os.makedirs(os.path.join(root_path, simulation_path))

        # Start by regenerating the netlists for the circuit-under-test
        # (This may not be quick but all tests depend on the existence
        # of the netlist, so it has to be done here and cannot be
        # parallelized).

        fullnetlistpath = regenerate_netlists(self.datasheet)
        if not fullnetlistpath:
            print('Failed to regenerate project netlist;  stopping.')
            return 1

        # Generate testbench netlists if needed
        result = regenerate_testbenches(self.datasheet, self.param['name'])
        if result == 1:
            print('Failed to regenerate testbench netlists;  stopping.')
            return 1

        print('Evaluating electrical parameter ' + self.param['name'])
        cace_gensim(self.datasheet, self.param)

        # Diagnostic:  find and print the number of files to be simulated
        # Names are methodname, pinname, and simulation number.
        totalsims = 0
        if 'testbenches' in self.param:
            totalsims += len(self.param['testbenches'])
            print('Total files to simulate: ' + str(totalsims))
        else:
            print(
                'Skipping parameter '
                + self.param['name']
                + ' (no testbenches).'
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
            )
            self.add_simulation_job(new_sim_job)

            idx += 1

        # Create an empty testbench list to hold the testbenches
        # that are returned
        self.new_testbenches = [None] * (
            len(self.param['testbenches']) // group_size
        )

    def postprocess(self):

        if 'plot' in self.param:
            print('Plotting results')
            cace_makeplot(self.datasheet, self.param)

        if 'spec' in self.param:
            print('Collating results')
            self.param = cace_collate(self.datasheet, self.param)
