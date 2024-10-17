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
import traceback
import subprocess
from multiprocessing.pool import ThreadPool
from importlib.machinery import SourceFileLoader

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
    console,
)
from rich.markdown import Markdown


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

        self.add_argument(Argument('template', None, True))   # TODO typing
        self.add_argument(Argument('collate', None, False))
        self.add_argument(Argument('format', None, False))
        self.add_argument(Argument('suffix', None, False))
        self.add_argument(Argument('variables', [], False))
        self.add_argument(Argument('script', None, False))
        self.add_argument(Argument('script_variables', [], False))

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

        info(f'Parameter {self.param["name"]}: Generating simulation files…')

        variables = self.get_argument('variables')

        # Add all named results
        for variable in variables:
            if variable != None:
                self.add_result(Result(variable))

        script_variables = self.get_argument('script_variables')

        # Add all named results from the user-defined script
        for variable in script_variables:
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
            # the results were all conditions but the collate conditions is the same
            # This is useful for MC simulations, where the results of different iterations,
            # but under the same conditions (e.g. temperature) should be collated.

            # First remove the collate condition from the conditions
            collate_variable = None
            if self.get_argument('collate'):
                collate_variable = self.get_argument('collate')

                # Remove any bit slices
                pmatch = self.vectrex.match(collate_variable)
                if pmatch:
                    collate_variable = pmatch.group(1)

                info(f'Collating results using condition "{collate_variable}"')

                if collate_variable in conditions:
                    collate_condition = conditions.pop(collate_variable)
                    dbg(collate_condition)
                else:
                    err(
                        f'Couldn\'t find condition "{collate_variable}" used for collating the results.'
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
                        'netlist_source': source,
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

        info(f'Parameter {self.param["name"]}: Running simulations…')

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

        info(f'Parameter {self.param["name"]}: Collecting results…')

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
                else:
                    err(f'Unsupported format for the simulation result.')

            dbg(f'collated values: {collated_values}')

            # Put back the collate condition for script and plotting
            if self.get_argument('collate'):
                condition_sets[index][collate_variable] = collate_values

                dbg(
                    f'collated condition: {condition_sets[index][collate_variable]}'
                )

            dbg(f'Extending final result…')

            for variable in variables:
                if variable != None:
                    # Extend the final result
                    self.get_result(variable).values.extend(
                        collated_values[variable]
                    )

            # Postprocess using user-defined script
            script = self.get_argument('script')
            if script:
                script_path = os.path.join(
                    self.datasheet['paths']['scripts'], script
                )

                info(
                    f"Running user-defined script '[repr.filename][link=file://{os.path.abspath(script_path)}]{os.path.relpath(script_path)}[/link][/repr.filename]'…"
                )

                if not os.path.isfile(script_path):
                    err(f'No such user script {script_path}.')
                    self.result_type = ResultType.ERROR
                    return

                try:
                    user_script = SourceFileLoader(
                        'user_script', script_path
                    ).load_module()

                    class CustomPrint:
                        def __enter__(self):
                            self._stdout = sys.stdout
                            sys.stdout = self
                            return self

                        def __exit__(self, *args):
                            sys.stdout = self._stdout

                        def write(self, text):
                            text = text.rstrip()
                            if len(text) == 0:
                                return
                            info(text)

                        def flush(self):
                            self._stdout.flush()

                        def __getattr__(self, attr):
                            return getattr(self._stdout, attr)

                    with CustomPrint() as output:
                        script_values = user_script.postprocess(
                            collated_values, condition_set
                        )

                        # Merge collated and script variables
                        collated_values.update(script_values)

                except Exception:
                    err(f'Error in user script:')
                    traceback.print_exc()
                    self.result_type = ResultType.ERROR
                    return

            for variable in script_variables:
                if variable != None:
                    # Check for variable in results
                    if variable not in script_values:
                        err(f'Variable "{variable}" not in script results.')
                        self.result_type = ResultType.ERROR
                        return

                    # Extend the final result
                    self.get_result(variable).values.extend(
                        script_values[variable]
                    )

            simulation_values.append(collated_values)
            self.result_type = ResultType.SUCCESS

        dbg(f'simulation_values: {simulation_values}')
        dbg(f'results_dict: {self.results_dict}')

        # Put back the collate_condition
        # TODO find a better way
        if self.get_argument('collate'):
            conditions[collate_variable] = collate_condition

        # Extend simulation variables with script variables
        variables.extend(script_variables)

        # Write the CSV summary
        self.write_simulation_summary_csv(
            os.path.join(self.param_dir, f'simulation_summary.csv'),
            conditions,
            condition_sets,
            variables,
            simulation_values,
        )

        # Create the Markdown summary
        simulation_summary = self.create_simulation_summary_markdown(
            conditions,
            condition_sets,
            variables,
            simulation_values,
        )

        # Get path for the simulation summary
        outpath_sim_summary = os.path.join(
            self.param_dir, f'simulation_summary.md'
        )

        # Save the simulation summary
        with open(outpath_sim_summary, 'w') as f:
            f.write(simulation_summary)

        info(
            f'Parameter {self.param["name"]}: Saving simulation summary as \'[repr.filename][link=file://{os.path.abspath(outpath_sim_summary)}]{os.path.relpath(outpath_sim_summary)}[/link][/repr.filename]\'…'
        )

        # Print the simulation summary in the console
        console.print(Markdown(simulation_summary))

        # Create a plot if specified
        if 'plot' in self.param:
            # Create the plots and save them
            for named_plot in self.param['plot']:
                self.makeplot(
                    named_plot,
                    condition_sets,
                    conditions,
                    simulation_values,
                    collate_variable,
                )

    def create_simulation_summary_markdown(
        self,
        conditions,
        condition_sets,
        variables,
        simulation_values,
    ):
        """
        Create a summary for all simulation runs in Markdown
        """

        summary_table = f'# Simulation Summary for {self.param["display"]}\n\n'

        # Find all conditions with more than one value,
        # these change between simulations
        conditions_in_summary = []
        for condition in conditions.values():
            if len(condition.values) > 1:
                conditions_in_summary.append(condition.name)

        # Print the header
        header_entries = []
        header_separators = []

        # First entry is the simulation run
        header_entries.append('run')
        header_separators.append(':--')

        for cond in conditions_in_summary:
            header_entries.append(str(cond))
            header_separators.append('-' * max(len(str(cond)) - 1, 1) + ':')

        # Get resulting variables (check for None)
        for variable in variables:
            if variable != None:
                header_entries.append(str(variable))
                header_separators.append(
                    '-' * max(len(str(variable)) - 1, 1) + ':'
                )

        # Add header and separators
        summary_table += f'| {" | ".join(header_entries)} |\n'
        summary_table += f'| {" | ".join(header_separators)} |\n'

        # Generate the entries
        max_digits = len(str(len(condition_sets)))
        max_entries_list = 3
        for index, (condition_set, sim_values) in enumerate(
            zip(condition_sets, simulation_values)
        ):
            body_entries = []
            body_entries.append(f'run_{index:0{max_digits}d}')

            for cond in conditions_in_summary:
                if isinstance(condition_set[cond], list):
                    if len(condition_set[cond]) == 1:
                        body_entries.append(
                            self.decimal2readable(condition_set[cond][0])
                        )
                        continue

                    values = condition_set[cond][
                        0 : min(max_entries_list, len(condition_set[cond]))
                    ]
                    values = [self.decimal2readable(value) for value in values]
                    if len(condition_set[cond]) > max_entries_list:
                        values.append('…')
                    body_entries.append(f'[{", ".join(values)}]')
                else:
                    body_entries.append(
                        self.decimal2readable(condition_set[cond])
                    )

            for variable in variables:
                if variable != None:
                    if isinstance(simulation_values[index][variable], list):
                        if len(simulation_values[index][variable]) == 1:
                            body_entries.append(
                                self.decimal2readable(
                                    simulation_values[index][variable][0]
                                )
                            )
                            continue

                        values = simulation_values[index][variable][
                            0 : min(
                                max_entries_list,
                                len(simulation_values[index][variable]),
                            )
                        ]
                        values = [
                            self.decimal2readable(value) for value in values
                        ]
                        if (
                            len(simulation_values[index][variable])
                            > max_entries_list
                        ):
                            values.append('…')
                        body_entries.append(f'[{", ".join(values)}]')
                    else:
                        body_entries.append(
                            self.decimal2readable(
                                simulation_values[index][variable]
                            )
                        )

            summary_table += f'| {" | ".join(body_entries)} |\n'

        return summary_table

    def write_simulation_summary_csv(
        self,
        csv_file,
        conditions,
        condition_sets,
        variables,
        simulation_values,
    ):
        """
        Write a summary for all simulation runs in CSV
        """

        with open(csv_file, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)

            # Find all conditions with more than one value,
            # these change between simulations
            conditions_in_summary = []
            for condition in conditions.values():
                if len(condition.values) > 1:
                    conditions_in_summary.append(condition.name)

            # Print the header
            header_entries = []

            # First entry is the simulation run
            header_entries.append('run')

            for cond in conditions_in_summary:
                header_entries.append(str(cond))

            # Get resulting variables (check for None)
            for variable in variables:
                if variable != None:
                    header_entries.append(str(variable))

            # Write header
            csvwriter.writerow(header_entries)

            # Generate the entries
            max_digits = len(str(len(condition_sets)))
            max_entries_list = 3
            for index, (condition_set, sim_values) in enumerate(
                zip(condition_sets, simulation_values)
            ):
                body_entries = []
                body_entries.append(f'run_{index:0{max_digits}d}')

                for cond in conditions_in_summary:
                    if isinstance(condition_set[cond], list):
                        if len(condition_set[cond]) == 1:
                            body_entries.append(
                                self.decimal2readable(condition_set[cond][0])
                            )
                            continue

                        values = condition_set[cond][
                            0 : min(max_entries_list, len(condition_set[cond]))
                        ]
                        values = [
                            self.decimal2readable(value) for value in values
                        ]
                        if len(condition_set[cond]) > max_entries_list:
                            values.append('…')
                        body_entries.append(f'[{", ".join(values)}]')
                    else:
                        body_entries.append(
                            self.decimal2readable(condition_set[cond])
                        )

                for variable in variables:
                    if variable != None:
                        if isinstance(
                            simulation_values[index][variable], list
                        ):
                            if len(simulation_values[index][variable]) == 1:
                                body_entries.append(
                                    self.decimal2readable(
                                        simulation_values[index][variable][0]
                                    )
                                )
                                continue

                            values = simulation_values[index][variable][
                                0 : min(
                                    max_entries_list,
                                    len(simulation_values[index][variable]),
                                )
                            ]
                            values = [
                                self.decimal2readable(value)
                                for value in values
                            ]
                            if (
                                len(simulation_values[index][variable])
                                > max_entries_list
                            ):
                                values.append('…')
                            body_entries.append(f'[{", ".join(values)}]')
                        else:
                            body_entries.append(
                                self.decimal2readable(
                                    simulation_values[index][variable]
                                )
                            )

                # Write row
                csvwriter.writerow(body_entries)

    def decimal2readable(self, decimal):
        if isinstance(decimal, str):
            return decimal

        # Print zero as float
        if decimal == 0:
            return f'{decimal:.3f}'

        if decimal < 0.1 or decimal > 100000:
            return f'{decimal:.3e}'
        else:
            return f'{decimal:.3f}'

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
