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
import time
import shutil
import signal
import threading

from queue import Queue

from .cace_read import cace_read
from .cace_compat import cace_compat
from .cace_write import cace_write, cace_summary
from .physical_parameter import PhysicalParameter
from .electrical_parameter import ElectricalParameter


class SimulationManager:
    """
    The SimulationManager manages the simulation queue
    of physical and electrical parameters.
    It also holds the datasheet and provides functions to
    manipulate it.
    """

    def __init__(self, datasheet={}):
        """Initialize the object with a datasheet"""
        self.datasheet = datasheet
        self.threads = []
        self.queue = Queue()
        self.thread = None
        self.threads = []

    ### datasheet functions ###

    def load_datasheet(self, datasheet_path, debug):

        if not os.path.isfile(datasheet_path):
            print(f'Error: File {datasheet_path} not found.')
            return

        [dspath, dsname] = os.path.split(datasheet_path)

        # Read the datasheet, legacy format
        if os.path.splitext(datasheet_path)[1] == '.json':
            with open(datasheet_path) as ifile:
                try:
                    # "data-sheet" as a sub-entry of the input file is deprecated.
                    datatop = json.load(ifile)
                    if 'data-sheet' in datatop:
                        datatop = datatop['data-sheet']
                except json.decoder.JSONDecodeError as e:
                    print(
                        'Error:  Parse error reading JSON file '
                        + datasheet_path
                        + ':'
                    )
                    print(str(e))
                    return
        # New format
        else:
            datatop = cace_read(datasheet_path, debug)

        # Ensure that datasheet complies with CACE version 4.0 format
        self.datasheet = cace_compat(datatop, debug)

        # CACE should be run from the location of the datasheet's root
        # directory.  Typically, the datasheet is in the "cace" subdirectory
        # and "root" is "..".

        rootpath = None
        paths = self.datasheet['paths']
        if 'root' in paths:
            rootpath = self.datasheet['paths']['root']

        if rootpath:
            dspath = os.path.join(dspath, rootpath)
            paths['root'] = '.'

        os.chdir(dspath)
        print(os.getcwd())
        if debug:
            print(
                f'Working directory set to {dspath} ({os.path.abspath(dspath)})'
            )

        # set the filename
        self.datasheet['runtime_options']['filename'] = os.path.abspath(
            datasheet_path
        )

        # Make sure all runtime options exist
        self.default_runtime_options()

    def find_datasheet(self, search_dir, debug):
        # Check the search_dir directory and determine if there
        # is a .txt or .json file with the name of the directory, which
        # is assumed to have the same name as the project circuit.  Also
        # check subdirectories one level down.
        dirname = os.path.split(search_dir)[1]
        dirlist = os.listdir(search_dir)

        # Look through all directories for a '.txt' file
        for item in dirlist:
            if os.path.isfile(item):
                fileext = os.path.splitext(item)[1]
                basename = os.path.splitext(item)[0]
                if fileext == '.txt':
                    if basename == dirname:
                        print(f'Loading datasheet from {item}')
                        self.load_datasheet(item, debug)
                        return

            elif os.path.isdir(item):
                subdirlist = os.listdir(item)
                for subitem in subdirlist:
                    subitemref = os.path.join(item, subitem)
                    if os.path.isfile(subitemref):
                        fileext = os.path.splitext(subitem)[1]
                        basename = os.path.splitext(subitem)[0]
                        if fileext == '.txt':
                            if basename == dirname:
                                print(f'Loading datasheet from {subitemref}')
                                self.load_datasheet(subitemref, debug)
                                return

        # Look through all directories for a '.json' file
        # ('.txt') is preferred to ('.json')
        for item in dirlist:
            if os.path.isfile(item):
                fileext = os.path.splitext(item)[1]
                basename = os.path.splitext(item)[0]
                if fileext == '.json':
                    if basename == dirname:
                        print(f'Loading datasheet from {item}')
                        self.load_datasheet(item, debug)
                        return

            elif os.path.isdir(item):
                subdirlist = os.listdir(item)
                for subitem in subdirlist:
                    subitemref = os.path.join(item, subitem)
                    if os.path.isfile(subitemref):
                        fileext = os.path.splitext(subitem)[1]
                        basename = os.path.splitext(subitem)[0]
                        if fileext == '.json':
                            if basename == dirname:
                                print(f'Loading datasheet from {subitemref}')
                                self.load_datasheet(subitemref, debug)
                                return

        print('No datasheet found in local project (JSON or text file).')

    def save_datasheet(self, path):
        if self.datasheet['runtime_options']['debug']:
            print(f'Writing final output file {path}')

        if self.datasheet['runtime_options']['json']:
            # Dump the result as a JSON file
            jsonfile = os.path.splitext(path)[0] + '_debug.json'
            with open(jsonfile, 'w') as ofile:
                json.dump(self.datasheet, ofile, indent=4)
        else:
            # Write the result in CACE ASCII format version 4.0
            cace_write(self.datasheet, path, doruntime=False)

    def set_datasheet(self, datasheet):
        """Set a new datasheet"""
        self.datasheet = datasheet

    def get_datasheet(self):
        """Return the datasheet"""
        return self.datasheet

    def summarize_datasheet(self, pnames=[]):
        cace_summary(self.datasheet, pnames)

    def duplicate_parameter(self, pname):
        param = self.find_parameter(pname)

        if not param:
            print(f'Could not duplicate parameter {pname}')
            return

        newparam = param.copy()

        # Make the copied parameter editable
        newparam['editable'] = True

        # Adjsut the name
        newparam['name'] += '_copy'

        # Append this to the electrical parameter list after the item being copied
        if 'display' in param:
            newparam['display'] = param['display'] + ' (copy)'

        eparams = self.datasheet['electrical_parameters']
        eidx = eparams.index(param)
        eparams.insert(eidx + 1, newparam)

    def delete_parameter(self, pname):
        param = self.find_parameter(pname)

        if not param:
            print(f'Could not delete parameter {pname}')
            return

        eparams = self.datasheet['electrical_parameters']
        eidx = eparams.index(param)
        eparams.pop(eidx)

    def default_runtime_options(self):
        """Sane default values"""

        default_options = {
            'netlist_source': 'schematic',
            'force': False,
            'keep': False,
            'nosim': False,
            'json': False,
            'sequential': False,  # TODO implement
            'noplot': False,  # TODO test
            'parallel_parameters': 4,  # TODO test
            'debug': False,
            'filename': 'Unknown',
        }

        # Init with default value if key does not exist
        for key, value in default_options.items():
            if not key in self.datasheet['runtime_options']:
                self.datasheet['runtime_options'][key] = value

    def set_runtime_options(self, key, value):
        self.datasheet['runtime_options'][key] = value

        # Make sure the runtime options are valid
        self.validate_runtime_options()

    def get_runtime_options(self, key):
        return self.datasheet['runtime_options'][key]

    def validate_runtime_options(self):
        """Make sure the runtime options contain valid values"""

        valid_sources = ['schematic', 'layout', 'pex', 'rcx']

        if (
            not self.datasheet['runtime_options']['netlist_source']
            in valid_sources
        ):
            print(
                f'Error: Invalid netlist source: {self.datasheet["runtime_options"]["netlist_source"]}'
            )

        if not self.datasheet['runtime_options']['parallel_parameters'] > 0:
            print(f'Error: parallel_parameters must be at least 1')

        # TODO check that other keys exist

    ### simulation functions ####

    def get_all_pnames(self):
        """Return all parameter names"""

        eparams = []
        pparams = []

        if 'electrical_parameters' in self.datasheet:
            eparams = [
                item['name']
                for item in self.datasheet['electrical_parameters']
            ]

        if 'physical_parameters' in self.datasheet:
            pparams = [
                item['name'] for item in self.datasheet['physical_parameters']
            ]

        return eparams + pparams

    def find_parameter(self, pname):
        """
        Searches for the parameter with the name pname
        """

        # TODO make 'electrical_parameters' and 'physical_parameters'
        # a dictionary for much easier access

        param = None

        if 'electrical_parameters' in self.datasheet:
            for item in self.datasheet['electrical_parameters']:
                if item['name'] == pname:
                    if param:
                        print(f'Error: {pname} at least twice in datasheet')
                    param = item

        if 'physical_parameters' in self.datasheet:
            for item in self.datasheet['physical_parameters']:
                if item['name'] == pname:
                    if param:
                        print(f'Error: {pname} at least twice in datasheet')
                    param = item

        if not param:
            print('Unknown parameter "' + pname + '"')
            if 'electrical_parameters' in self.datasheet:
                print('Known electrical parameters are:')
                for eparam in self.datasheet['electrical_parameters']:
                    print(eparam['name'])
            if 'physical_parameters' in self.datasheet:
                print('Known physical parameters are:')
                for pparam in self.datasheet['physical_parameters']:
                    print(pparam['name'])

        return param

    def param_set_status(self, pname, status):
        param = self.find_parameter(pname)
        if param:
            param['status'] = status

    def queue_parameter(self, pname, cb=None, sim_cb=None):
        """Queue a parameter for later execution"""

        paths = self.datasheet['paths']
        runtime_options = self.datasheet['runtime_options']
        pdk = self.datasheet['PDK']

        if 'electrical_parameters' in self.datasheet:
            for param in self.datasheet['electrical_parameters']:
                if param['name'] == pname:
                    # Quick check for skipped or blocked parameter.
                    if 'status' in param:
                        status = param['status']
                        if status == 'skip':
                            print(
                                f'Skipping parameter {param["name"]} (status=skip).'
                            )
                            return
                        if status == 'blocked':
                            print(
                                f'Skipping parameter {param["name"]} (status=blocked).'
                            )
                            return

                    print('Creating ElectricalParameter')

                    new_sim_param = ElectricalParameter(
                        param, self.datasheet, pdk, paths, runtime_options, cb
                    )

                    print('Inserting into queue')
                    self.queue.put(new_sim_param)

                    # TODO return number of simulations for this parameter
                    #      needed for progress bars etc.
                    return 1

        if 'physical_parameters' in self.datasheet:
            for param in self.datasheet['physical_parameters']:
                if param['name'] == pname:
                    # Quick check for skipped or blocked parameter.
                    if 'status' in param:
                        status = param['status']
                        if status == 'skip':
                            print(
                                f'Skipping parameter {param["name"]} (status=skip).'
                            )
                            return
                        if status == 'blocked':
                            print(
                                f'Skipping parameter {param["name"]} (status=blocked).'
                            )
                            return

                    print('Creating PhysicalParameter')

                    new_sim_param = PhysicalParameter(
                        param, self.datasheet, pdk, paths, runtime_options, cb
                    )

                    print('Inserting into queue')
                    self.queue.put(new_sim_param)

                    # TODO return number of simulations for this parameter
                    #      needed for progress bars etc.
                    return 1

        print(f'Unknown parameter {pname}')
        if 'electrical_parameters' in self.datasheet:
            print('Known electrical parameters are:')
            for eparam in self.datasheet['electrical_parameters']:
                print(eparam['name'])
        if 'physical_parameters' in self.datasheet:
            print('Known physical parameters are:')
            for pparam in self.datasheet['physical_parameters']:
                print(pparam['name'])

        return None

    def num_queued_simulations(self):
        """Get the number of queued simulations"""

        return self.queue.qsize()

    def num_running_simulations(self):
        """Get the number of running simulations"""

        # TODO Remove completed threads
        self.threads = [t for t in self.threads if t.is_alive()]

        return len(self.threads)

    def run_parameters_async(self):
        """Start a thread to start parameter threads"""

        print('Starting threads async')

        # Wait until previous run completed
        if self.thread:
            self.thread.join()
        self.thread = None

        # Start new thread to start parameter threads
        self.thread = threading.Thread(target=self.run_parameters_thread)
        self.thread.start()

    def run_parameters_thread(self):
        """A thread starts the thread of queued parameters"""

        while not self.queue.empty():
            # Check whether we can start another parameter in parallel
            if (
                self.num_running_simulations()
                < self.datasheet['runtime_options']['parallel_parameters']
            ):

                sim_param = self.queue.get()

                print('Starting simulation thread')
                # sim_param.setDaemon(True) # TODO correct?
                sim_param.start()

                self.threads.append(sim_param)
            # Else wait until another parameter has completed
            else:
                time.sleep(0.1)

    def join_parameters(self):
        """Join all running parameter threads"""

        # Wait until previous run completed
        if self.thread:
            self.thread.join()
        self.thread = None

        # Wait until thread is complete
        for thread in self.threads:
            thread.join()

        # Remove completed threads
        self.threads = [t for t in self.threads if t.is_alive()]

    def run_parameters(self):
        """Run parameters sequentially, note that simulations can still be parallelized"""

        while not self.queue.empty():
            sim_param = self.queue.get()

            print('Starting simulation')
            sim_param.run()

    def clear_queued_parameters(self, cancel_cb=False):
        """Clear all queued parameters"""

        while not self.queue.empty():
            sim_param = self.queue.get()

            print('Cancel queued simulation')
            sim_param.cancel(cancel_cb)
            sim_param.run()

    def cancel_running_parameters(self, cancel_cb=False):
        """Cancel all running parameters"""

        # Remove completed threads
        self.threads = [t for t in self.threads if t.is_alive()]

        for thread in self.threads:
            thread.cancel(cancel_cb)

    def cancel_running_parameter(self, pname, cancel_cb=False):
        """Cancel a single running parameter"""

        # Remove completed threads
        self.threads = [t for t in self.threads if t.is_alive()]

        found = False
        for thread in self.threads:
            if thread.param['name'] == pname:
                found = True
                thread.cancel(cancel_cb)

        if not found:
            print(f'Error: Could not cancel simulation: {pname} not found')
