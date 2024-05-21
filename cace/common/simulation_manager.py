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

from .cace_read import cace_read
from .cace_compat import cace_compat
from .cace_write import cace_write, cace_summary, cace_generate_html
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

        self.worker_thread = None

        self.queued_threads = []
        self.queued_lock = threading.Lock()

        self.running_threads = []
        self.running_lock = threading.Lock()

        self.default_options = {
            'netlist_source': 'schematic',
            'force': False,
            'keep': False,
            'nosim': False,
            'json': False,
            'sequential': False,  # TODO implement
            'noplot': False,  # TODO test
            'parallel_parameters': 4,
            'debug': False,
            'filename': 'Unknown',
        }

        self.default_runtime_options()

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
        """
        Check the search_dir directory and determine if there
        is a .txt or .json file with the name of the directory, which
        is assumed to have the same name as the project circuit.  Also
        check subdirectories one level down.
        Returns 0 on success and 1 on failure.
        """

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
                        return 0

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
                                return 0

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
                        return 0

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
                                return 0

        print('No datasheet found in local project (JSON or text file).')
        return 1

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

    def markdown_summary(self, file=None):
        """
        Print a brief summary to either stdout or any file that is passed.
        The summary is formatted in Markdown and can be viewed
        """
        print('\n# CACE Summary\n', file=file)

        print(
            f'**general**\n\n'
            f'- name: {self.datasheet["name"]}\n'
            f'- description: {self.datasheet["description"]}\n'
            f'- commit: {self.datasheet["commit"]}\n'
            f'- PDK: {self.datasheet["PDK"]}\n'
            f'- cace_format: {self.datasheet["cace_format"]}\n',
            file=file,
        )

        print(
            f'**authorship**\n\n'
            f'- designer: {self.datasheet["authorship"]["designer"]}\n'
            f'- company: {self.datasheet["authorship"]["company"]}\n'
            f'- creation_date: {self.datasheet["authorship"]["creation_date"]}\n'
            f'- license: {self.datasheet["authorship"]["license"]}\n',
            file=file,
        )

        print('## Electrical Parameters\n', file=file)

        # Spacings
        sp = [20, 20, 9, 9, 9, 9, 9, 9, 8]

        print(
            f'| {"Parameter": ^{sp[0]}} | {"Testbench": ^{sp[1]}} | {"Min Limit": ^{sp[2]}} | {"Min Value": ^{sp[3]}} | {"Typ Limit": ^{sp[4]}} | {"Typ Value": ^{sp[5]}} | {"Max Limit": ^{sp[6]}} | {"Max Value": ^{sp[7]}} | {"Status": ^{sp[8]}} |',
            file=file,
        )
        print(
            f'| :{"-"*(sp[0]-1)} | :{"-"*(sp[1]-1)} | :{"-"*(sp[3]-2)}: | :{"-"*(sp[3]-2)}: | :{"-"*(sp[4]-2)}: | :{"-"*(sp[5]-2)}: | :{"-"*(sp[6]-2)}: | :{"-"*(sp[7]-2)}: | :{"-"*(sp[8]-2)}: |',
            file=file,
        )

        if 'electrical_parameters' in self.datasheet:
            for eparam in self.datasheet['electrical_parameters']:

                min_limit = ''
                typ_limit = ''
                max_limit = ''

                if 'spec' in eparam:
                    if 'minimum' in eparam['spec']:
                        min_limit = eparam['spec']['minimum']

                        if isinstance(min_limit, list):
                            min_limit = min_limit[0]

                    if 'typical' in eparam['spec']:
                        typ_limit = eparam['spec']['typical']

                        if isinstance(typ_limit, list):
                            typ_limit = typ_limit[0]

                    if 'maximum' in eparam['spec']:
                        max_limit = eparam['spec']['maximum']

                        if isinstance(max_limit, list):
                            max_limit = max_limit[0]

                min_value = ''
                typ_value = ''
                max_value = ''

                if 'results' in eparam:
                    passing = True

                    if 'minimum' in eparam['results']:
                        min_value = eparam['results']['minimum'][0]

                        if eparam['results']['minimum'][1] != 'pass':
                            passing = False

                    if 'typical' in eparam['results']:
                        typ_value = eparam['results']['typical'][0]

                        if eparam['results']['typical'][1] != 'pass':
                            passing = False

                    if 'maximum' in eparam['results']:
                        max_value = eparam['results']['maximum'][0]

                        if eparam['results']['maximum'][1] != 'pass':
                            passing = False

                testbench = ''

                status = 'Pass ✅' if passing else 'Fail ❌'

                if eparam['status'] == 'skip':
                    status = 'Skip 🟧'

                if 'simulate' in eparam:
                    testbench = eparam['simulate']['template']

                print(
                    f'| {eparam["name"]: <{sp[0]}} | {testbench: <{sp[1]}} | {min_limit: ^{sp[2]}} | {min_value: ^{sp[3]}} | {typ_limit: ^{sp[4]}} | {typ_value: ^{sp[5]}} | {max_limit: ^{sp[6]}} | {max_value: ^{sp[7]}} | {status: ^{sp[8]-1}} |',
                    file=file,
                )

        print('\n## Physical Parameters\n', file=file)

        print(
            f'| {"Parameter": ^{sp[0]}} | {"Testbench": ^{sp[1]}} | {"Min Limit": ^{sp[2]}} | {"Min Value": ^{sp[3]}} | {"Typ Limit": ^{sp[4]}} | {"Typ Value": ^{sp[5]}} | {"Max Limit": ^{sp[6]}} | {"Max Value": ^{sp[7]}} | {"Status": ^{sp[8]}} |',
            file=file,
        )
        print(
            f'| :{"-"*(sp[0]-1)} | :{"-"*(sp[1]-1)} | :{"-"*(sp[3]-2)}: | :{"-"*(sp[3]-2)}: | :{"-"*(sp[4]-2)}: | :{"-"*(sp[5]-2)}: | :{"-"*(sp[6]-2)}: | :{"-"*(sp[7]-2)}: | :{"-"*(sp[8]-2)}: |',
            file=file,
        )

        if 'physical_parameters' in self.datasheet:
            for pparam in self.datasheet['physical_parameters']:

                min_limit = ''
                typ_limit = ''
                max_limit = ''

                if 'spec' in pparam:
                    if 'minimum' in pparam['spec']:
                        min_limit = pparam['spec']['minimum']

                        if isinstance(min_limit, list):
                            min_limit = min_limit[0]

                    if 'typical' in pparam['spec']:
                        typ_limit = pparam['spec']['typical']

                        if isinstance(typ_limit, list):
                            typ_limit = typ_limit[0]

                    if 'maximum' in pparam['spec']:
                        max_limit = pparam['spec']['maximum']

                        if isinstance(max_limit, list):
                            max_limit = max_limit[0]

                min_value = ''
                typ_value = ''
                max_value = ''

                if 'results' in pparam:
                    passing = True

                    if 'minimum' in pparam['results']:
                        min_value = pparam['results']['minimum'][0]

                        if pparam['results']['minimum'][1] != 'pass':
                            passing = False

                    if 'typical' in pparam['results']:
                        typ_value = pparam['results']['typical'][0]

                        if pparam['results']['typical'][1] != 'pass':
                            passing = False

                    if 'maximum' in pparam['results']:
                        max_value = pparam['results']['maximum'][0]

                        if pparam['results']['maximum'][1] != 'pass':
                            passing = False

                testbench = ''

                status = 'Pass ✅' if passing else 'Fail ❌'

                if pparam['status'] == 'skip':
                    status = 'Skip 🟧'

                if 'simulate' in pparam:
                    testbench = pparam['simulate']['template']

                print(
                    f'| {pparam["name"]: <{sp[0]}} | {testbench: <{sp[1]}} | {min_limit: ^{sp[2]}} | {min_value: ^{sp[3]}} | {typ_limit: ^{sp[4]}} | {typ_value: ^{sp[5]}} | {max_limit: ^{sp[6]}} | {max_value: ^{sp[7]}} | {status: ^{sp[8]-1}} |',
                    file=file,
                )

        print('\n', file=file)

    def generate_html(self):
        debug = self.get_runtime_options('debug')
        cace_generate_html(self.datasheet, None, debug)

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

        # Make sure runtime options exist
        if not 'runtime_options' in self.datasheet:
            self.datasheet['runtime_options'] = {}

        # Init with default value if key does not exist
        for key, value in self.default_options.items():
            if not key in self.datasheet['runtime_options']:
                self.datasheet['runtime_options'][key] = value

    def set_runtime_options(self, key, value):
        self.datasheet['runtime_options'][key] = value

        # Make sure the runtime options are valid
        self.validate_runtime_options()

    def get_runtime_options(self, key):
        if not key in self.datasheet['runtime_options']:
            print(f'Warning: Runtime option "{key}" not in runtime_options')
            if key in self.default_options:
                print(f'Setting runtime option "{key}" to default value')
                self.datasheet['runtime_options'][key] = self.default_options[
                    key
                ]

        return self.datasheet['runtime_options'][key]

    def get_path(self, key):
        if not key in self.datasheet['paths']:
            print(f'Warning: Path "{key}" not in paths')
            print(f'Setting path "{key}" to "{key}"')
            self.datasheet['paths'][key] = key

        return self.datasheet['paths'][key]

    def validate_runtime_options(self):
        """Make sure the runtime options contain valid values"""

        valid_sources = ['schematic', 'layout', 'pex', 'rcx', 'best']

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

                    new_sim_param = ElectricalParameter(
                        param, self.datasheet, pdk, paths, runtime_options, cb
                    )

                    print(
                        f'Inserting electrical parameter {param["name"]} into queue'
                    )

                    with self.queued_lock:
                        self.queued_threads.insert(0, new_sim_param)

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

                    new_sim_param = PhysicalParameter(
                        param, self.datasheet, pdk, paths, runtime_options, cb
                    )

                    print(
                        f'Inserting physical parameter {param["name"]} into queue'
                    )

                    with self.queued_lock:
                        self.queued_threads.insert(0, new_sim_param)

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

    def prune_running_threads(self):
        """Remove threads that are either marked as done or have been canceled"""

        needs_unlock = False
        if not self.running_lock.locked():
            self.running_lock.lock()
            needs_unlock = True

        # Remove completed threads
        self.running_threads = [
            t
            for t in self.running_threads
            if t.is_alive() or (not t.done and not t.canceled)
        ]

        if needs_unlock:
            self.running_lock.unlock()

    def num_parameters(self):
        """Get the number of queued or running parameters"""

        return self.num_queued_parameters() + self.num_running_parameters()

    def num_queued_parameters(self):
        """Get the number of queued parameters"""

        return len(self.queued_threads)

    def num_running_parameters(self):
        """Get the number of running parameters"""

        with self.running_lock:
            self.prune_running_threads()

            # Count the parameter threads that are not yet done
            num_running = sum(
                1
                for t in self.running_threads
                if not t.done and not t.canceled
            )

        return num_running

    def run_parameters_async(self):
        """Start a worker thread to start parameter threads"""

        # Only start a new worker thread, if
        # the previous one hasn't completed yet
        if not self.worker_thread or not self.worker_thread.is_alive():
            # Start new worker thread to start parameter threads
            self.worker_thread = threading.Thread(
                target=self.run_parameters_thread
            )
            self.worker_thread.start()

    def run_parameters_thread(self):
        """Called as a thread, starts the threads of queued parameters"""

        while self.queued_threads:

            # Check whether we can start another parameter in parallel
            if (
                self.num_running_parameters()
                < self.datasheet['runtime_options']['parallel_parameters']
            ):
                param_thread = None

                # Holding both locks, move a parameter
                # from queued to running
                with self.running_lock:
                    with self.queued_lock:
                        # Could have been cancelled meanhwile
                        if self.queued_threads:
                            param_thread = self.queued_threads.pop()
                            self.running_threads.append(param_thread)

                if param_thread and not param_thread.canceled:
                    print(f'Running parameter {param_thread.param["name"]}')
                    param_thread.start()

            # Else wait until another parameter has completed
            else:
                time.sleep(0.1)

    def join_parameters(self):
        """Join all running parameter threads"""

        # Wait until all parameters are running
        if self.worker_thread:
            self.worker_thread.join()
        self.worker_thread = None

        # Wait until all parameters are complete
        with self.running_lock:
            for param_thread in self.running_threads:
                param_thread.join()

            # Remove completed threads
            self.prune_running_threads()

    def run_parameters(self):
        """Run parameters sequentially, note that simulations can still be parallelized"""

        with self.queued_lock:
            while self.queued_threads:
                param_thread = self.queued_threads.pop()
                param_thread.run()

    def cancel_parameters(self, cancel_cb=False):
        """Cancel all parameters"""

        self.cancel_queued_parameters(cancel_cb)
        self.cancel_running_parameters(cancel_cb)

    def cancel_queued_parameters(self, cancel_cb=False):
        """Cancel all queued parameters"""

        with self.queued_lock:
            while self.queued_threads:
                param_thread = self.queued_threads.pop()

                # Cancel the thread and start it
                # so that it directly calls its callback
                param_thread.cancel(cancel_cb)
                param_thread.start()

    def cancel_running_parameters(self, cancel_cb=False):
        """Cancel all running parameters"""

        with self.running_lock:

            # Remove completed threads
            self.prune_running_threads()

            for param_thread in self.running_threads:
                param_thread.cancel(cancel_cb)

    def cancel_parameter(self, pname, cancel_cb=False):
        """Cancel a single parameter"""

        self.cancel_queued_parameter(pname, cancel_cb)
        self.cancel_running_parameter(pname, cancel_cb)

    def cancel_queued_parameter(self, pname, cancel_cb=False):
        """Cancel a single running parameter"""

        with self.queued_lock:

            # Get all threads that should be canceled
            # Maybe there are multiple threads with the same name
            cancel_threads = [
                t for t in self.queued_threads if t.param['name'] == pname
            ]

            for param_thread in cancel_threads:

                # Remove the thread from the queued list
                self.queued_threads.remove(param_thread)

                # Cancel the thread and start it
                # so that it directly calls its callback
                param_thread.cancel(cancel_cb)
                param_thread.start()

    def cancel_running_parameter(self, pname, cancel_cb=False):
        """Cancel a single running parameter"""

        with self.running_lock:

            # Remove completed threads
            self.prune_running_threads()

            for param_thread in self.running_threads:
                # TODO also check source
                if param_thread.param['name'] == pname:
                    param_thread.cancel(cancel_cb)
