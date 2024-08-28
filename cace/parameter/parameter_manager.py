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
import glob
import time
import yaml
import shutil
import signal
import datetime
import threading

from ..common.misc import mkdirp
from ..common.cace_read import cace_read, cace_read_yaml
from ..common.cace_write import (
    markdown_summary,
    generate_documentation,
)
from ..common.cace_regenerate import regenerate_netlists, regenerate_gds

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

registered_parameters = {}


def register_parameter(name):
    def inner(cls):
        registered_parameters[name] = cls
        return cls

    return inner


class ParameterManager:
    """
    The ParameterManager manages the parameter queue
    of physical and electrical parameters.
    It also holds the datasheet and provides functions to
    manipulate it.
    """

    def __init__(self, datasheet={}, max_runs=None, run_path=None, jobs=None):
        """Initialize the object with a datasheet"""
        self.datasheet = datasheet
        self.max_runs = max_runs
        self.run_path = run_path

        self.worker_thread = None

        self.queued_threads = []
        self.queued_lock = threading.Lock()

        self.running_threads = []
        self.running_lock = threading.Lock()

        self.results = {}
        self.result_types = {}

        self.runtime_options = {}

        self.default_runtime_options = {
            'debug': False,
            'netlist_source': 'schematic',
            'sequential': False,
            'noplot': False,  # TODO test
            'parallel_parameters': 4,
            'filename': None,
        }

        self.set_default_runtime_options()

        self.default_paths = {
            'templates': 'cace/templates',
            'scripts': 'cace/scripts',
            'runs': 'runs',
        }

        self.set_default_paths()

        # Set the number of jobs to the number of cores
        # if jobs=None
        if not jobs:
            jobs = os.cpu_count()

        # Fallback jobs
        if not jobs:
            jobs = 4

        self.jobs_sem = threading.Semaphore(value=jobs)

        dbg(f'Parameter manager: total number of jobs is {jobs}')

    ### datasheet functions ###

    def load_datasheet(self, datasheet_path):
        """
        Tries to load a datasheet from the given path.
        YAML is preferred over text format.
        Returns 0 on success and 1 on failure.
        """

        if not os.path.isfile(datasheet_path):
            err(f'File {datasheet_path} not found.')
            return 1

        [dspath, dsname] = os.path.split(datasheet_path)

        suffix = os.path.splitext(datasheet_path)[1]

        if suffix == '.yaml':
            # Read the datasheet, new CACE YAML format version 5.0
            self.datasheet = cace_read_yaml(datasheet_path)
        elif suffix == '.txt':
            self.datasheet = cace_read(datasheet_path)
        else:
            err(f'Unsupported file extension: {suffix}')
            return 1

        # Datasheet is invalid
        if self.datasheet == None:
            return 1

        self.runtime_options['filename'] = dsname

        # CACE should be run from the location of the datasheet's root
        # directory.  Typically, the datasheet is in the "cace" subdirectory
        # and "root" is "..".

        rootpath = None
        paths = self.datasheet['paths']
        if 'root' in paths:
            rootpath = paths['root']

        if rootpath:
            dspath = os.path.join(dspath, rootpath)
            paths['root'] = '.'

        os.chdir(dspath)
        info(
            f"Working directory set to '{dspath}' ('{os.path.abspath(dspath)}')."
        )
        os.environ['CACE_ROOT'] = os.path.abspath(dspath)

        # Set the PDK variable
        if self.datasheet['PDK']:
            os.environ['PDK'] = self.datasheet['PDK']

        # Make sure all runtime options exist
        self.set_default_runtime_options()

        # Make sure all paths exist
        self.set_default_paths()

        # Create a new run dir for logs
        self.prepare_run_dir()

        return 0

    def find_datasheet(self, search_dir):
        """
        Check the search_dir directory and determine if there
        is a .yaml or .txt file with the name of the directory, which
        is assumed to have the same name as the project circuit.  Also
        check subdirectories one level down.
        Returns 0 on success and 1 on failure.
        """

        dirname = os.path.split(search_dir)[1]
        dirlist = os.listdir(search_dir)

        # Look through all directories for a '.yaml' file
        for item in dirlist:
            if os.path.isfile(item):
                fileext = os.path.splitext(item)[1]
                basename = os.path.splitext(item)[0]
                if fileext == '.yaml':
                    if basename == dirname:
                        info(f"Loading datasheet from '{item}'.")
                        return self.load_datasheet(item)

            elif os.path.isdir(item):
                subdirlist = os.listdir(item)
                for subitem in subdirlist:
                    subitemref = os.path.join(item, subitem)
                    if os.path.isfile(subitemref):
                        fileext = os.path.splitext(subitem)[1]
                        basename = os.path.splitext(subitem)[0]
                        if fileext == '.yaml':
                            if basename == dirname:
                                info(f"Loading datasheet from '{subitemref}'.")
                                return self.load_datasheet(subitemref)

        info('No datasheet found in local project (YAML file).')
        return 1

    def save_datasheet(self, path):
        info(f'Writing output file {path}')

        suffix = os.path.splitext(path)[1]

        if suffix == '.yaml':
            # Write the result in CACE YAML format version 5.0
            new_datasheet = self.datasheet.copy()

            # Set version to 5.0
            new_datasheet['cace_format'] = 5.0

            with open(os.path.join(path), 'w') as outfile:
                yaml.dump(
                    new_datasheet,
                    outfile,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
        else:
            err(f'Unsupported file extension: {suffix}')

    def set_datasheet(self, datasheet):
        """Set a new datasheet"""
        self.datasheet = datasheet

    def get_datasheet(self):
        """Return the datasheet"""
        return self.datasheet

    def summarize_datasheet(self):
        return markdown_summary(
            self.datasheet,
            self.runtime_options,
            self.results,
            self.result_types,
        )

    def generate_documentation(self):
        if 'documentation' in self.datasheet['paths']:
            doc_path = os.path.join(
                self.datasheet['paths']['root'],
                self.datasheet['paths']['documentation'],
            )

            info(f"Generating documentation in '{os.path.relpath(doc_path)}'")

            # Create path to documentation
            mkdirp(doc_path)

            # Generate the documentation
            generate_documentation(self.datasheet)

            # Save summary for netlist type
            summary = markdown_summary(
                self.datasheet,
                self.runtime_options,
                self.results,
                self.result_types,
            )
            summarypath = os.path.join(
                self.datasheet['paths']['root'],
                self.datasheet['paths']['documentation'],
                f'{self.datasheet["name"]}_{self.runtime_options["netlist_source"]}.md',
            )
            with open(summarypath, 'w') as ofile:
                ofile.write(summary)

                # Save the plots
                ofile.write(f'\n## Plots\n')

                for parameter in self.datasheet['parameters']:
                    if 'plot' in self.datasheet['parameters'][parameter]:
                        plotpath = os.path.join(
                            self.datasheet['paths']['root'],
                            self.datasheet['paths']['documentation'],
                            f'{self.datasheet["name"]}',
                            f'{self.runtime_options["netlist_source"]}',
                        )
                        mkdirp(plotpath)

                        for named_plot in self.datasheet['parameters'][
                            parameter
                        ]['plot']:

                            # File format
                            suffix = '.png'
                            if (
                                'suffix'
                                in self.datasheet['parameters'][parameter][
                                    'plot'
                                ][named_plot]
                            ):
                                suffix = self.datasheet['parameters'][
                                    parameter
                                ]['plot'][named_plot]['suffix']

                            # Filename for the plot
                            filename = f'{named_plot}{suffix}'

                            param_dir = os.path.abspath(
                                os.path.join(
                                    self.run_dir,
                                    'parameters',
                                    self.datasheet['parameters'][parameter][
                                        'name'
                                    ],
                                )
                            )

                            source = os.path.join(param_dir, filename)
                            destination = os.path.join(plotpath, filename)

                            # Only copy if the file exists
                            if os.path.exists(source) and os.path.isfile(
                                source
                            ):
                                shutil.copy(source, destination)
                                ofile.write(f'\n## {named_plot}\n')

                                ofile.write(
                                    f'\n![{named_plot}]({os.path.join(".", self.datasheet["name"], self.runtime_options["netlist_source"], filename)})\n'
                                )

        else:
            info(
                f'Path "documentation" not set in datasheet. Skipping documentation generation.'
            )

    def duplicate_parameter(self, pname):
        param = self.find_parameter(pname)

        if not param:
            warn(f'Could not duplicate parameter {pname}')
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
            warn(f'Could not delete parameter {pname}')
            return

        eparams = self.datasheet['electrical_parameters']
        eidx = eparams.index(param)
        eparams.pop(eidx)

    def set_default_runtime_options(self):
        """Sane default values"""

        # Make sure runtime options exist
        if not self.runtime_options:
            self.runtime_options = {}

        # Init with default value if key does not exist
        for key, value in self.default_runtime_options.items():
            if not key in self.runtime_options:
                self.runtime_options[key] = value

    def set_default_paths(self):
        """Sane default values"""

        # Make sure runtime options exist
        if not 'paths' in self.datasheet:
            self.datasheet['paths'] = {}

        # Init with default value if key does not exist
        for key, value in self.default_paths.items():
            if not key in self.datasheet['paths']:
                self.datasheet['paths'][key] = value

    def set_runtime_options(self, key, value):
        self.runtime_options[key] = value

        # Make sure the runtime options are valid
        self.validate_runtime_options()

    def get_runtime_options(self, key):
        if not key in self.runtime_options:
            dbg(f'Runtime option "{key}" not in runtime_options')
            if key in self.default_options:
                info(f'Setting runtime option "{key}" to default value')
                self.runtime_options[key] = self.default_options[key]

        return self.runtime_options[key]

    def get_path(self, key):
        if not key in self.datasheet['paths']:
            dbg(f'Path "{key}" not in paths')
            dbg(f'Setting path "{key}" to "{key}"')
            self.datasheet['paths'][key] = key

        return self.datasheet['paths'][key]

    def validate_runtime_options(self):
        """Make sure the runtime options contain valid values"""

        valid_sources = ['schematic', 'layout', 'pex', 'rcx', 'best']

        # Check for valid sources
        if not self.runtime_options['netlist_source'] in valid_sources:
            err(
                f'Invalid netlist source: {self.runtime_options["netlist_source"]}'
            )

        # If a magic layout is given, make sure layout is also defined
        if 'magic' in self.datasheet['paths']:
            if not 'layout' in self.datasheet['paths']:
                # Default layout path
                self.datasheet['paths']['layout'] = 'gds'

        # Replace "best" with the best possible source
        if self.runtime_options['netlist_source'] == 'best':
            # If a layout is given, the best source is rcx
            if 'layout' in self.datasheet['paths']:
                self.runtime_options['netlist_source'] = 'rcx'
            # Else only schematic is possible
            else:
                self.runtime_options['netlist_source'] = 'schematic'

        if not self.runtime_options['parallel_parameters'] > 0:
            err(f'parallel_parameters must be at least 1')

        # TODO check that other keys exist

    ### simulation functions ####

    def get_all_pnames(self):
        """Return all parameter names"""

        pnames = list(self.datasheet['parameters'].keys())

        return pnames

    def find_parameter(self, pname):
        """
        Searches for the parameter with the name pname
        """

        if pname in self.datasheet['parameters']:
            return self.datasheet['parameters'][pname]

        warn(f'Unknown parameter: {pname}')
        return None

    def param_set_status(self, pname, status):
        param = self.find_parameter(pname)
        if param:
            param['status'] = status

    def queue_parameter(
        self, pname, start_cb=None, end_cb=None, cancel_cb=None, step_cb=None
    ):
        """Queue a parameter for later execution"""

        paths = self.datasheet['paths']
        pdk = self.datasheet['PDK']

        if pname in self.datasheet['parameters']:

            param = self.datasheet['parameters'][pname]
            tool = param['tool']

            # Get the name of the tool
            if isinstance(tool, str):
                toolname = tool
            else:
                toolname = list(tool.keys())[0]

            if toolname in registered_parameters.keys():
                cls = registered_parameters[toolname]

                new_sim_param = cls(
                    pname,
                    param,
                    self.datasheet,
                    pdk,
                    paths,
                    self.runtime_options,
                    self.run_dir,
                    # Semaphore for starting
                    # new jobs
                    self.jobs_sem,
                    # Callbacks
                    start_cb,
                    end_cb,
                    cancel_cb,
                    step_cb,
                )

                dbg(f'Inserting parameter {pname} into queue.')

                with self.queued_lock:
                    self.queued_threads.insert(0, new_sim_param)

                return

            else:
                err(f'Unknown evaluation tool: {toolname}.')
                return

        warn(f'Unknown parameter {pname}')

        warn('Available parameters are:')
        for pname in self.datasheet['parameters']:
            warn(pname)

    def prune_running_threads(self):
        """Remove threads that are either marked as done or have been canceled"""

        needs_unlock = False
        if not self.running_lock.locked():
            self.running_lock.acquire()
            needs_unlock = True

        # Get the results
        for t in self.running_threads:
            if not t.is_alive() and t.started:
                if t.pname in self.results:
                    warn(f'{t.pname} already in results!')
                self.results[t.pname] = t.results_dict
                self.result_types[t.pname] = t.result_type
                t.harvested = True

        # Remove completed threads
        self.running_threads = [
            t for t in self.running_threads if not t.harvested
        ]

        if needs_unlock:
            self.running_lock.release()

    def get_results(self):
        return self.results

    def get_result_types(self):
        return self.result_types

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

    def prepare_run_dir(self):

        self.design_dir = '.'

        # Create a new tag
        tag = (
            datetime.datetime.now()
            .astimezone()
            .strftime('RUN_%Y-%m-%d_%H-%M-%S')
        )

        run_path = self.datasheet['paths']['runs']

        # Override runs dir with cli argument
        if self.run_path:
            run_path = self.run_path

        # Create new run dir
        self.run_dir = os.path.abspath(
            os.path.join(self.design_dir, run_path, tag)
        )

        # Check if run dir already exists
        runs = sorted(glob.glob(os.path.join(self.design_dir, run_path, '*')))

        if self.run_dir in runs:
            error('Run directory exists already. Please try again.')

        info(f"Starting a new run with tag '{tag}'.")
        mkdirp(self.run_dir)

        # Delete the oldest runs if max_runs set
        if self.max_runs and len(runs) >= self.max_runs:
            runs = runs[::-1]   # Reverse runs
            # Select runs to remove
            remove = runs[self.max_runs - 1 :]
            dbg(f'Removing run directories: {remove}')

            for run in remove:
                shutil.rmtree(run)

    def run_parameters_async(self):
        """Start a worker thread to start parameter threads"""

        # Start by regenerating the netlists for the circuit-under-test
        # (This may not be quick but all tests depend on the existence
        # of the netlist, so it has to be done here and cannot be
        # parallelized).

        fullnetlistpath = regenerate_netlists(
            self.datasheet, self.runtime_options
        )
        if not fullnetlistpath:
            err('Failed to regenerate project netlist, aborting.')
            self.cancel_parameters(True)
            return

        # If mag files are given as layout, regenerate the gds if needed
        if regenerate_gds(self.datasheet, self.runtime_options):
            err(
                'Failed to regenerate GDSII layout from magic layout, aborting.'
            )
            self.cancel_parameters(True)
            return

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
                < self.runtime_options['parallel_parameters']
            ):
                param_thread = None

                # Holding both locks, move a parameter
                # from queued to running
                with self.running_lock:
                    with self.queued_lock:
                        # Could have been cancelled meanwhile
                        if self.queued_threads:
                            param_thread = self.queued_threads.pop()
                            self.running_threads.append(param_thread)

                if param_thread and not param_thread.canceled:
                    dbg(f'Running parameter {param_thread.pname}')
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

        # Wait until all parameters are completed
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

    def cancel_parameters(self, no_cb=False):
        """Cancel all parameters"""

        self.cancel_queued_parameters(no_cb)
        self.cancel_running_parameters(no_cb)

    def cancel_queued_parameters(self, no_cb=False):
        """Cancel all queued parameters"""

        with self.queued_lock:
            while self.queued_threads:
                param_thread = self.queued_threads.pop()

                # Cancel the thread and start it
                # so that it directly calls its callback
                param_thread.cancel(no_cb)
                param_thread.start()

    def cancel_running_parameters(self, no_cb=False):
        """Cancel all running parameters"""

        with self.running_lock:
            # Remove completed threads
            self.prune_running_threads()

            for param_thread in self.running_threads:
                param_thread.cancel(no_cb)

    def cancel_parameter(self, pname, no_cb=False):
        """Cancel a single parameter"""

        self.cancel_queued_parameter(pname, no_cb)
        self.cancel_running_parameter(pname, no_cb)

    def cancel_queued_parameter(self, pname, no_cb=False):
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
                param_thread.cancel(no_cb)
                param_thread.start()

    def cancel_running_parameter(self, pname, no_cb=False):
        """Cancel a single running parameter"""

        with self.running_lock:

            # Remove completed threads
            self.prune_running_threads()

            for param_thread in self.running_threads:
                # TODO also check source
                if param_thread.param['name'] == pname:
                    param_thread.cancel(no_cb)
