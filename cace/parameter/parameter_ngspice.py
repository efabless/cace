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
import csv
import sys
import yaml
import time
import shutil
import threading
import subprocess
from multiprocessing.pool import ThreadPool

from ..common.misc import mkdirp
from ..common.spiceunits import spice_unit_convert
from ..common.common import (
    run_subprocess,
    set_xschem_paths,
    get_pdk,
    get_pdk_root,
)
from .parameter import Parameter, ResultType, Argument, Condition, Result
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


@register_parameter('ngspice')
class ParameterNgspice(Parameter):
    """
    The ElectricalParameter simulates an electrical parameter
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

        self.add_argument(Argument('template', None, True))
        self.add_argument(Argument('collate', None, False))
        self.add_argument(Argument('format', None, False))
        self.add_argument(Argument('suffix', None, False))
        self.add_argument(Argument('variables', [], False))

        # Total number of simulations
        # used for the progress bar
        self.num_sims = 1

        self.queued_jobs = []

    def cancel(self, no_cb):
        super().cancel(no_cb)

        for job in self.queued_jobs:
            job.cancel(no_cb)

    def add_simulation_job(self, job):
        self.queued_jobs.append(job)

    def pre_start(self):
        """
        Generate the conditions to get the total number of simulations
        """

        template = self.get_argument('template')
        template_path = os.path.join(self.paths['templates'], template)

        if not os.path.isfile(template_path):
            err(f'Could not find template file {template_path}.')
            self.result_type = ResultType.ERROR
            return

        # Get global default conditions
        conditions_default = self.get_default_conditions()

        dbg(conditions_default)

        # Get parameter conditions
        conditions_param = self.get_param_conditions()

        dbg(conditions_param)

        # Get the condition names used in the template
        # (and the default values if given)
        conditions_template = self.get_condition_names_used(
            template_path, escape=True
        )

        dbg(conditions_template)

        if not conditions_template:
            warn(f'No conditions found in template {template}')

        # Merge, to get the final conditions
        conditions = conditions_template
        for cond in conditions:

            # First, overwrite with global defaults
            if cond in conditions_default:
                conditions[cond] = conditions_default[cond]

            # Secondly, overwrite with parameter
            if cond in conditions_param:
                if conditions_param[cond].description:
                    conditions[cond].description = conditions_param[
                        cond
                    ].description
                if conditions_param[cond].display:
                    conditions[cond].display = conditions_param[cond].display
                if conditions_param[cond].unit:
                    conditions[cond].unit = conditions_param[cond].unit
                if conditions_param[cond].spec:
                    conditions[cond].spec = conditions_param[cond].spec

        dbg(f'conditions: {conditions}')

        # Generate the values for each condition
        for cond in conditions:
            conditions[cond].generate_values()

        # Get the total number of simulations
        self.num_sims = 1
        for cond in conditions:
            self.num_sims *= max(len(conditions[cond].values), 1)

    def implementation(self):

        info(f'Parameter {self.param["name"]}: Generating simulation files.')

        variables = self.get_argument('variables')

        # Add all named results
        for variable in variables:
            if variable != None:
                self.add_result(Result(variable))

        template = self.get_argument('template')
        template_path = os.path.join(self.paths['templates'], template)
        run_template_path = os.path.join(self.param_dir, template)
        template_ext = os.path.splitext(template)[1]

        # A schematic is given as template, this means we need
        # to perform the substitutions on the schematic
        if template_ext == '.sch':

            if not os.path.isfile(template_path):
                err(f'Could not find template file {template_path}.')
                self.result_type = ResultType.ERROR
                return

            # Copy template testbench to run dir
            shutil.copyfile(template_path, run_template_path)

            # Get global default conditions
            conditions_default = self.get_default_conditions()

            # Get parameter conditions
            conditions_param = self.get_param_conditions()

            # Get the condition names used in the template
            # (and the default values if given)
            conditions_template = self.get_condition_names_used(
                run_template_path, escape=True
            )

            if not conditions_template:
                warn(f'No conditions found in template {template}')

            # Merge, to get the final conditions
            conditions = conditions_template
            for cond in conditions:

                # First, overwrite with global defaults
                if cond in conditions_default:
                    conditions[cond] = conditions_default[cond]

                # Secondly, overwrite with parameter
                if cond in conditions_param:
                    if conditions_param[cond].description:
                        conditions[cond].description = conditions_param[
                            cond
                        ].description
                    if conditions_param[cond].display:
                        conditions[cond].display = conditions_param[
                            cond
                        ].display
                    if conditions_param[cond].unit:
                        conditions[cond].unit = conditions_param[cond].unit
                    if conditions_param[cond].spec:
                        conditions[cond].spec = conditions_param[cond].spec

            # Generate the values for each condition
            for cond in conditions:
                conditions[cond].generate_values()

            # Get the total number of simulations
            self.num_sims = 1
            for cond in conditions:
                self.num_sims *= max(len(conditions[cond].values), 1)

            dbg(f'Total number of simulations: {self.num_sims}')

            # If "collate" is set this means we need to merge
            # the results of this variable
            # This is done by removing it from the conditions
            # and

            if self.get_argument('collate'):
                collate_variable = self.get_argument('collate')
                info(f'Collating results using condition "{collate_variable}"')

                if collate_variable in conditions:
                    collate_condition = conditions.pop(collate_variable)
                    dbg(collate_condition)
                else:
                    err(
                        f'Couldn\'t find collate variable "{collate_variable}" in conditions.'
                    )

            # Generate the condition sets for each simulation
            condition_sets = self.generate_condition_sets(conditions)

            # For each condition set, substitute the
            # testbench template with it
            max_digits = len(str(len(condition_sets)))
            for index, condition_set in enumerate(condition_sets):

                # Inner loop for collate variable (if set)
                collate_values = [1]
                if self.get_argument('collate'):
                    collate_values = collate_condition.values
                    max_digits_collate = len(str(len(collate_values)))

                for collate_index, collate_value in enumerate(collate_values):

                    self.cancel_point()

                    # Create directory for this run
                    outpath = os.path.join(
                        self.param_dir, f'run_{index:0{max_digits}d}'
                    )

                    if self.get_argument('collate'):
                        outpath = os.path.join(
                            outpath, f'run_{collate_index:0{max_digits}d}'
                        )

                    dbg(f"Creating directory: '{os.path.relpath(outpath)}'.")
                    mkdirp(outpath)

                    # Get DUT netlist path
                    source = self.runtime_options['netlist_source']

                    if source == 'schematic':
                        netlistpath = os.path.join(
                            self.paths['netlist'], 'schematic'
                        )
                    elif source == 'layout':
                        netlistpath = os.path.join(
                            self.paths['netlist'], 'layout'
                        )
                    elif source == 'pex':
                        netlistpath = os.path.join(
                            self.paths['netlist'], 'pex'
                        )
                    elif source == 'rcx':
                        netlistpath = os.path.join(
                            self.paths['netlist'], 'rcx'
                        )

                    dutpath = os.path.join(
                        self.paths['root'],
                        netlistpath,
                        self.datasheet['name'] + '.spice',
                    )

                    if not os.path.isfile(dutpath):
                        err(f'Could not find dut netlist {dutpath}.')

                    reserved = {
                        'filename': os.path.splitext(template)[0],
                        'templates': os.path.abspath(self.paths['templates']),
                        'simpath': os.path.abspath(outpath),
                        'DUT_name': self.datasheet['name'],
                        'N': index,
                        'DUT_path': os.path.abspath(dutpath),
                        'PDK_ROOT': get_pdk_root(),
                        'PDK': get_pdk(),
                        'include_DUT': os.path.abspath(dutpath),
                        'random': str(
                            int(time.time() * 1000) & 0x7FFFFFFF
                        ),  # TODO
                    }

                    # Set the reserved conditions
                    for cond in condition_set:
                        if cond in reserved:
                            condition_set[cond] = reserved[cond]

                    # Add the collate condition
                    if self.get_argument('collate'):
                        condition_set[collate_variable] = collate_value

                    # Check if all conditions for this run
                    # have a value
                    for cond in condition_set:
                        if condition_set[cond] == None:
                            warn(f'Condition {cond} not defined')

                    # Write conditions set
                    with open(
                        os.path.join(outpath, 'conditions.yaml'), 'w'
                    ) as outfile:
                        yaml.dump(
                            condition_set,
                            outfile,
                            default_flow_style=False,
                            allow_unicode=True,
                        )

                    outfile = os.path.join(outpath, template)
                    dbg(f'Substituting with {condition_set} in {outfile}')

                    # Run the substitution
                    self.substitute(
                        run_template_path,
                        outfile,
                        condition_set,
                        conditions,
                        reserved={},
                        escape=True,
                    )

                    # Copy the xschem symbol
                    # and convert to primitive!

                    dname = self.datasheet['name']
                    xschemname = dname + '.sym'

                    schempath = self.paths['schematic']
                    symbolfilename = os.path.join(schempath, xschemname)
                    primfilename = os.path.join(outpath, xschemname)

                    if not os.path.isfile(symbolfilename):
                        err(f'Could not find xschem symbol {symbolfilename}.')
                        self.result_type = ResultType.ERROR
                        return

                    with open(symbolfilename, 'r') as ifile:
                        symboldata = ifile.read()
                        primdata = symboldata.replace(
                            'type=subcircuit', 'type=primitive'
                        )

                    with open(primfilename, 'w') as ofile:
                        ofile.write(primdata)

                    # Run xschem to convert the testbench schematic
                    # to a spice netlist

                    # Add the path with the modififed DUT symbol to the search path.
                    # Note that testbenches use a version of the DUT symbol that is
                    # marked as "primitive" so that it does not get added to the netlist directly.
                    # The netlist must be included by a ".include" statement in the testbenches.
                    tcllist = ['append XSCHEM_LIBRARY_PATH :' + primfilename]

                    # Add the templates path to the search path
                    # It could be that there are symbols for stimuli generation etc.
                    tcllist.append(
                        'append XSCHEM_LIBRARY_PATH :'
                        + os.path.abspath(self.paths['templates'])
                    )

                    tclstr = ' ; '.join(tcllist)

                    # Xschem arguments:
                    # -n:  Generate a netlist
                    # -s:  Netlist type is SPICE
                    # -r:  Bypass readline (because stdin/stdout are piped)
                    # -x:  No X11 / No GUI window
                    # -q:  Quit after processing command line
                    # --tcl: Tcl commands
                    xschemargs = [
                        '-n',
                        '-s',
                        '-r',
                        '-x',
                        '-q',
                        '--tcl',
                        tclstr,
                    ]

                    pdk_root = get_pdk_root()
                    pdk = get_pdk()

                    # Use the PDK xschemrc file for xschem startup
                    xschemrcfile = os.path.join(
                        pdk_root, pdk, 'libs.tech', 'xschem', 'xschemrc'
                    )
                    if os.path.isfile(xschemrcfile):
                        xschemargs.extend(['--rcfile', xschemrcfile])
                    else:
                        err(f'No xschemrc file found in the {pdk} PDK.')

                    xschemargs.extend(
                        [
                            '-o',
                            outpath,
                            '-N',
                            os.path.splitext(template)[0] + '.spice',
                        ]
                    )
                    xschemargs.append(outfile)

                    returncode = self.run_subprocess(
                        'xschem', xschemargs, cwd=outpath
                    )

                    """if returncode:
                        self.result_type = ResultType.ERROR
                        return"""

        # We directly got a spice netlist,
        # perform the substitutions on it
        elif template_ext == '.spice':
            err('TODO: Implement substitution for spice templates!')
            self.result_type = ResultType.ERROR
            return
        else:
            err(f'Unsupported file extension for template: {template}')

        # Run all simulations
        jobs = []

        info(f'Parameter {self.param["name"]}: Running simulations.')

        self.cancel_point()

        # Run simulation jobs sequentially
        if self.runtime_options['sequential']:
            max_digits = len(str(len(condition_sets)))
            for index, condition_set in enumerate(condition_sets):

                # Inner loop for collate variable (if set)
                collate_values = [1]
                if self.get_argument('collate'):
                    collate_values = collate_condition.values
                    max_digits_collate = len(str(len(collate_values)))

                for collate_index, collate_value in enumerate(collate_values):

                    self.cancel_point()

                    # Get directory for this run
                    outpath = os.path.join(
                        self.param_dir, f'run_{index:0{max_digits}d}'
                    )

                    if self.get_argument('collate'):
                        outpath = os.path.join(
                            outpath, f'run_{collate_index:0{max_digits}d}'
                        )

                    new_sim_job = SimulationJob(
                        self.param,
                        outpath,
                        os.path.splitext(template)[0] + '.spice',
                        self.jobs_sem,
                        self.step_cb,
                    )
                    self.add_simulation_job(new_sim_job)

                    new_sim_job.start()
                    new_sim_job.join()

        # Run simulation jobs in parallel
        else:
            # Use a thread pool to get the return value
            with ThreadPool(processes=None) as pool:

                # Schedule all simulations
                max_digits = len(str(len(condition_sets)))
                for index, condition_set in enumerate(condition_sets):

                    # Inner loop for collate variable (if set)
                    collate_values = [1]
                    if self.get_argument('collate'):
                        collate_values = collate_condition.values
                        max_digits_collate = len(str(len(collate_values)))

                    for collate_index, collate_value in enumerate(
                        collate_values
                    ):

                        # Get directory for this run
                        outpath = os.path.join(
                            self.param_dir, f'run_{index:0{max_digits}d}'
                        )

                        if self.get_argument('collate'):
                            outpath = os.path.join(
                                outpath, f'run_{collate_index:0{max_digits}d}'
                            )

                        new_sim_job = SimulationJob(
                            self.param,
                            outpath,
                            os.path.splitext(template)[0] + '.spice',
                            self.jobs_sem,
                            self.step_cb,
                        )
                        self.add_simulation_job(new_sim_job)

                        jobs.append(pool.apply_async(new_sim_job.run, ()))

                # Wait for completion
                while 1:
                    self.cancel_point()

                    # Check if all tasks have completed
                    if all([job.ready() for job in jobs]):
                        break

                    time.sleep(0.1)

                # Get the results
                for job in jobs:
                    if job.get() != 0:
                        self.result_type = ResultType.ERROR
                        return

                self.cancel_point()

        info(f'Parameter {self.param["name"]}: Collecting results.')

        # Get the result
        max_digits = len(str(len(condition_sets)))
        results_for_plot = []

        format = self.get_argument('format')
        suffix = self.get_argument('suffix')
        variables = self.get_argument('variables')

        simulation_values = []

        for index, condition_set in enumerate(condition_sets):

            # Inner loop for collate variable (if set)
            collate_values = [1]
            if self.get_argument('collate'):
                collate_values = collate_condition.values
                max_digits_collate = len(str(len(collate_values)))

            collated_values = {}

            for variable in variables:
                if variable != None:
                    collated_values[variable] = []

            for collate_index, collate_value in enumerate(collate_values):

                # Get directory for this run
                outpath = os.path.join(
                    self.param_dir, f'run_{index:0{max_digits}d}'
                )

                if self.get_argument('collate'):
                    outpath = os.path.join(
                        outpath, f'run_{collate_index:0{max_digits}d}'
                    )

                # Read the result file

                collated_results = {}

                if format == 'ascii':

                    result_file = os.path.join(
                        outpath,
                        os.path.splitext(template)[0] + f'_{index}' + suffix,
                    )

                    if not os.path.isfile(result_file):
                        err(f'No such result file {result_file}.')
                        self.result_type = ResultType.ERROR
                        return

                    with open(result_file, newline='') as csvfile:
                        reader = csv.reader(
                            csvfile, delimiter=' ', skipinitialspace=True
                        )
                        for row in reader:
                            for _index, entry in enumerate(row):
                                # Ignore empty entries (often the last element)
                                if entry != '':
                                    # Check if there is a named variable at this index
                                    if variables[_index] != None:
                                        # If so, append the entry
                                        collated_values[
                                            variables[_index]
                                        ].append(float(entry))

                    dbg(f'collated_values: {collated_values}')

                else:
                    err(f'Unsupported format for the simulation result.')

            for variable in variables:
                if variable != None:
                    # Extend the final result
                    self.get_result(variable).values.extend(
                        collated_values[variable]
                    )

            simulation_values.append(collated_values)
            self.result_type = ResultType.SUCCESS

        dbg(f'simulation_values: {simulation_values}')
        dbg(f'results_dict: {self.results_dict}')

        # TODO other tools?

        # Create a plot if specified
        if 'plot' in self.param:
            # Create the plots and save them
            for named_plot in self.param['plot']:
                self.makeplot(
                    named_plot, condition_sets, conditions, simulation_values
                )

    def get_num_steps(self):
        return self.num_sims


class SimulationJob(threading.Thread):

    """
    The SimulationJob runs exactly one simulation via ngspice
    """

    def __init__(
        self,
        param,
        outpath,
        simfile,
        jobs_sem,
        step_cb,
        *args,
        **kwargs,
    ):
        self.param = param
        self.outpath = outpath
        self.simfile = simfile
        self.jobs_sem = jobs_sem
        self.step_cb = step_cb

        self.canceled = False
        self.subproc_handle = None
        self._return = None

        super().__init__(*args, **kwargs)

    def cancel(self, no_cb):
        self.canceled = True

        if self.subproc_handle:
            self.subproc_handle.kill()

    def cancel_point(self):
        """If canceled, exit the thread"""

        if self.canceled:
            sys.exit()

    def run_subprocess(self, proc, args=[], env=None, input=None, cwd=None):

        dbg(
            f'Subprocess {proc} {" ".join(args)} at \'[repr.filename][link=file://{os.path.abspath(cwd)}]{os.path.relpath(cwd)}[/link][/repr.filename]\'…'
        )

        with subprocess.Popen(
            [proc] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if input else subprocess.DEVNULL,
            env=env,
            text=True,
        ) as process:

            self.subproc_handle = process

            dbg(input)
            stdout, stderr = process.communicate(input)
            returncode = process.returncode

            if returncode != 0:
                err(f'Subprocess exited with error code {returncode}')

            # Print stderr
            if stderr and returncode != 0:
                err('Error output generated by subprocess:')
                for line in stderr.splitlines():
                    err(line.rstrip('\n'))
            else:
                dbg('Error output generated by subprocess:')
                for line in stderr.splitlines():
                    dbg(line.rstrip('\n'))

            # Write stderr to file
            if stderr:
                with open(
                    f'{os.path.join(cwd, proc)}_stderr.out', 'w'
                ) as stderr_file:
                    stderr_file.write(stderr)

            # Print stdout
            if stdout:
                dbg(f'Output from subprocess {proc}:')
                for line in stdout.splitlines():
                    dbg(line.rstrip())

            # Write stdout to file
            if stdout:
                with open(
                    f'{os.path.join(cwd, proc)}_stdout.out', 'w'
                ) as stdout_file:
                    stdout_file.write(stdout)

        self.subproc_handle = None

        return returncode

    def run(self):
        self.cancel_point()

        # Acquire a job from the global jobs semaphore
        with self.jobs_sem:
            self.cancel_point()

            # Run ngspice
            returncode = self.run_subprocess(
                'ngspice', ['--batch', self.simfile], cwd=self.outpath
            )

            self.cancel_point()

            self._return = returncode

            # Call the step cb -> advance progress bar
            if self.step_cb:
                self.step_cb(self.param)

        # For when the join function is called
        return self._return
