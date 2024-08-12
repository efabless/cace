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
import traceback
import subprocess
from statistics import median, mean
from enum import Enum
from abc import abstractmethod, ABC
from threading import Thread
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
from matplotlib.figure import Figure

from ..common.safe_eval import safe_eval
from ..common.misc import mkdirp
from ..common.spiceunits import spice_unit_convert
from ..common.common import linseq, logseq
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


class ResultType(Enum):
    UNKNOWN = 0
    ERROR = 1
    SUCCESS = 2
    FAILURE = 3
    SKIPPED = 4
    CANCELED = 5

    def __str__(self):
        if self.value == ResultType.UNKNOWN.value:
            return 'Unknown ❓'
        elif self.value == ResultType.ERROR.value:
            return 'Error ❗'
        elif self.value == ResultType.SUCCESS.value:
            return 'Pass ✅'
        elif self.value == ResultType.FAILURE.value:
            return 'Fail ❌'
        elif self.value == ResultType.SKIPPED.value:
            return 'Skip 🟧'
        elif self.value == ResultType.CANCELED.value:
            return 'Cancel 🟧'
        else:
            return '???'


class Argument:
    def __init__(self, name, default=None, required=False):
        self.name = name
        self.default = default
        self.required = required


class Condition:
    def __init__(self):
        self.name = None
        self.description = None
        self.display = None
        self.unit = None
        self.spec = {}
        self.values = []

    def __repr__(self):
        return f'{self.name} with spec {self.spec} and values {self.values}'

    def __str__(self):
        return f'{self.name} {self.description} {self.display} {self.unit} {self.spec} {self.values}'

    def generate_values(self):
        self.values = [val for val in self.condition_gen()]

    def condition_gen(self):
        """
        Define a generator for conditions.
        """

        if 'enumerate' in self.spec:
            for i in self.spec['enumerate']:
                yield i

        if 'step' in self.spec:
            if not 'minimum' in self.spec or not 'maximum' in self.spec:
                err(
                    f'Step specified in condition, but no minimum/maximum: {self}'
                )

            if 'typical' in self.spec:
                yield self.spec['typical']

            # Linear step
            if self.spec['step'] == 'linear':
                stepsize = 1
                if 'stepsize' in self.spec:
                    stepsize = self.spec['stepsize']

                yield from linseq(
                    int(self.spec['minimum']),
                    int(self.spec['maximum']),
                    int(stepsize),
                )

            # Logarithmic step
            elif self.spec['step'] == 'logarithmic':
                stepsize = 2
                if 'stepsize' in self.spec:
                    stepsize = self.spec['stepsize']

                yield from logseq(
                    int(self.spec['minimum']),
                    int(self.spec['maximum']),
                    int(stepsize),
                )

            else:
                err(
                    f'Unknown step type {self.spec["step"]} in condition: {self}'
                )
        else:
            if 'minimum' in self.spec:
                yield self.spec['minimum']
            if 'maximum' in self.spec:
                yield self.spec['maximum']
            if 'typical' in self.spec:
                yield self.spec['typical']


class Parameter(ABC, Thread):
    """
    Base class for all parameters.
    """

    # Vectors in name[number|range] format
    vectrex = re.compile(r'([^\[]+)\[([0-9:]+)\]')

    def __init__(
        self,
        pname,
        param,
        datasheet,
        pdk,
        paths,
        runtime_options,
        run_dir,
        jobs_sem,
        start_cb=None,
        end_cb=None,
        cancel_cb=None,
        step_cb=None,
        *args,
        **kwargs,
    ):
        self.pname = pname
        self.param = param
        self.datasheet = datasheet
        self.pdk = pdk
        self.paths = paths
        self.runtime_options = runtime_options
        self.run_dir = run_dir
        self.jobs_sem = jobs_sem
        self.start_cb = start_cb
        self.end_cb = end_cb
        self.cancel_cb = cancel_cb
        self.step_cb = step_cb

        self.started = False

        self.harvested = False

        self.subproc_handle = None

        self.param_dir = os.path.abspath(
            os.path.join(self.run_dir, 'parameters', pname)
        )

        # Get the name of the tool and input
        tool = self.param['tool']
        if isinstance(tool, str):
            self.toolname = tool
            self.tooldict = None
        else:
            self.toolname = list(tool.keys())[0]
            self.tooldict = tool[self.toolname]

        self.arguments_dict = {}

        self.result = {'type': ResultType.UNKNOWN, 'values': []}

        self.canceled = False
        self.done = False

        super().__init__(*args, **kwargs)

    def add_argument(self, arg: Argument):
        if arg.required:
            if not self.tooldict or not arg.name in self.tooldict:
                warn(f'Expected {arg.name} in {self.toolname}')

        if self.tooldict and arg.name in self.tooldict:
            self.arguments_dict[arg.name] = self.tooldict[arg.name]
        else:
            self.arguments_dict[arg.name] = arg.default

    def get_argument(self, arg: str):
        return self.arguments_dict[arg]

    def cancel(self, no_cb):
        info(f'Parameter {self.pname}: Canceled')
        self.canceled = True

        if self.subproc_handle:
            self.subproc_handle.kill()

        if no_cb:
            self.cancel_cb = None

    def cancel_point(self):
        """If canceled, call the cancel cb and exit the thread"""

        if self.canceled:
            self.result['type'] = ResultType.CANCELED
            if self.cancel_cb:
                self.cancel_cb(self.param)
            sys.exit()

    def is_runnable(self):
        return True

    def run(self):

        self.started = True
        rule(f'Started {self.param["display"]}')

        # Create new parameter dir
        dbg(f"Creating directory: '{os.path.relpath(self.param_dir)}'.")
        mkdirp(self.param_dir)

        try:
            self.cancel_point()

            self.pre_start()

            if self.start_cb:
                self.start_cb(self.param, self.get_num_steps())

            self.cancel_point()

            # Run the implementation
            if self.is_runnable():
                self.implementation()

            self.cancel_point()

        except Exception:
            traceback.print_exc()
            self.result['type'] = ResultType.ERROR
            self.canceled = True

        self.evaluate_result()

        # Set done before calling end cb
        self.done = True

        if self.end_cb:
            self.end_cb(self.param)

        rule(f'Completed {self.param["display"]}: {self.result["type"]}')

        return self.result

    @abstractmethod
    def implementation(self):
        pass

    def pre_start(self):
        pass

    def get_num_steps(self):
        return 1

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

    def evaluate_result(self):

        defaults = {
            'minimum': {
                'fail': True,
                'calculation': 'minimum',
                'limit': 'above',
            },
            'typical': {
                'fail': False,
                'calculation': 'median',
                'limit': 'exact',
            },
            'maximum': {
                'fail': True,
                'calculation': 'maximum',
                'limit': 'below',
            },
        }

        # For each entry in the specs
        for entry in ['minimum', 'typical', 'maximum']:

            if entry in self.param['spec']:
                value = self.param['spec'][entry]['value']
                fail = (
                    self.param['spec'][entry]['fail']
                    if 'fail' in self.param['spec'][entry]
                    else defaults[entry]['fail']
                )
                calculation = (
                    self.param['spec'][entry]['calculation']
                    if 'calculation' in self.param['spec'][entry]
                    else defaults[entry]['calculation']
                )
                limit = (
                    self.param['spec'][entry]['limit']
                    if 'limit' in self.param['spec'][entry]
                    else defaults[entry]['limit']
                )

                if self.result['values']:
                    # Calculate a single value from a vector
                    if calculation == 'minimum':
                        result = min(self.result['values'])
                    elif calculation == 'maximum':
                        result = max(self.result['values'])
                    elif calculation == 'median':
                        result = median(self.result['values'])
                    elif calculation == 'average':
                        result = mean(self.result['values'])
                    else:
                        err(f'Unknown calculation type: {calculation}')
                else:
                    result = None

                self.result[entry] = {'value': result}
                dbg(f'Got {entry} result for {self.pname}: {result}')

                status = 'pass'

                # Check result against a limit
                if value != 'any' and fail == True:
                    # Scale value with unit
                    if 'unit' in self.param:
                        dbg(f'{self.param["unit"]} {value}')
                        value = spice_unit_convert(
                            (str(self.param['unit']), str(value))
                        )

                    if result != None:
                        dbg(
                            f'Checking result {result} against value {value} with limit {limit}.'
                        )
                        if limit == 'above':
                            if result < float(value):
                                status = 'fail'
                        elif limit == 'below':
                            if result > float(value):
                                status = 'fail'
                        elif limit == 'exact':
                            if result != float(value):
                                status = 'fail'
                        else:
                            err(f'Unknown limit type: {limit}')

                self.result[entry]['status'] = status

                dbg(f'Got {entry} status for {self.pname}: {status}')

            else:
                self.result[entry] = None

        for entry in ['minimum', 'typical', 'maximum']:
            if entry in self.result:
                if self.result[entry] and 'status' in self.result[entry]:
                    if self.result[entry]['status'] == 'fail':
                        # If any spec fails, fail the whole parameter
                        self.result['type'] = ResultType.FAILURE

    def get_default_conditions(self):
        # Get the global default conditions
        conditions_default = {}

        for cond, spec in self.datasheet['default_conditions'].items():
            # Create new conditions
            new_cond = Condition()

            # Remove any bit slices
            pmatch = self.vectrex.match(cond)
            if pmatch:
                cond = pmatch.group(1)

            new_cond.name = cond

            for key, value in spec.items():
                if key == 'description':
                    new_cond.description = value
                elif key == 'display':
                    new_cond.display = value
                elif key == 'unit':
                    new_cond.unit = value
                else:
                    new_cond.spec[key] = value

            # Add condition
            conditions_default[cond] = new_cond

        return conditions_default

    def get_param_conditions(self):
        # Get the conditions for this parameter
        conditions_param = {}

        for cond, spec in self.param['conditions'].items():
            # Create new conditions
            new_cond = Condition()

            # Remove any bit slices
            pmatch = self.vectrex.match(cond)
            if pmatch:
                cond = pmatch.group(1)

            new_cond.name = cond

            for key, value in spec.items():
                if key == 'description':
                    new_cond.description = value
                elif key == 'display':
                    new_cond.display = value
                elif key == 'unit':
                    new_cond.unit = value
                else:
                    new_cond.spec[key] = value

            # Add condition
            conditions_param[cond] = new_cond

        return conditions_param

    def generate_condition_sets(self, conditions):
        num_sets = 1

        # Get the total number of condition sets
        for cond in conditions:
            num_sets *= max(len(conditions[cond].values), 1)

        # Get the condition sets for each simulation
        # (the unique combinations of all conditions)
        condition_sets = []
        cond_index = [0] * len(conditions)

        for _ in range(num_sets):
            condition_set = {}
            overflow = False

            for index, cond in enumerate(conditions):
                if conditions[cond].values:
                    if conditions[cond].unit:
                        value = conditions[cond].values[cond_index[index]]
                        unit = conditions[cond].unit
                        condition_set[cond] = spice_unit_convert(
                            (str(unit), str(value))
                        )
                    else:
                        condition_set[cond] = str(
                            conditions[cond].values[cond_index[index]]
                        )
                else:
                    condition_set[cond] = None

                # The first condition always increments its index
                if index == 0:
                    cond_index[index] += 1
                # The conditions that come after only increment
                # if the previous condition just overflowed
                elif overflow:
                    cond_index[index] += 1
                    overflow = False

                # Check whether the condition reached its maximum
                if cond_index[index] == max(len(conditions[cond].values), 1):
                    cond_index[index] = 0
                    overflow = True

            condition_sets.append(condition_set)

        return condition_sets

    def get_condition_names_used(self, template, escape=False):
        """
        Read a template file and record all of the variable names that will
        be substituted, so it is clear which local and global conditions
        need to be enumerated.
        """

        if not os.path.isfile(template):
            err(f'No such template file {template}.')
            return

        with open(template, 'r') as ifile:
            simtext = ifile.read()

        simlines = simtext.splitlines()

        # Regular expressions
        # varex:		variable name {name}
        if escape:
            varex = re.compile(r'\\\{([^ \}\t]+)\\\}')
        else:
            varex = re.compile(r'\{([^ \}\t]+)\}')

        conditions = {}

        for line in simlines:
            for patmatch in varex.finditer(line):
                pattern = patmatch.group(1)
                default = None

                # For condition names in the form {cond=value}, use only the name
                if '=' in pattern:
                    (pattern, default) = pattern.split('=')

                # For condition names in the form {cond|value}, use only the name
                if '|' in pattern:
                    (pattern, cond_type) = pattern.split('|')

                # Remove any bit slices
                pmatch = self.vectrex.match(pattern)
                if pmatch:
                    pattern = pmatch.group(1)

                # Create new conditions
                new_cond = Condition()
                new_cond.name = pattern
                if default:
                    new_cond.spec['typical'] = default
                conditions[pattern] = new_cond

        return conditions

    def substitute(
        self,
        template_path,
        substituted_path,
        conditions_set,
        conditions,
        reserved,
        escape=False,
    ):
        # Regular expressions
        # varex:		variable name {name}
        # sweepex:		name in {cond|value} format
        # brackrex:		expressions in [expression] format

        if escape:
            varex = re.compile(r'\\\{([^\\\}]+)\\\}')
            sweepex = re.compile(r'\\\{([^\\\}]+)\|([^ \\\}]+)\\\}')
            brackrex = re.compile(r'\[([^\]]+)\]')
        else:
            varex = re.compile(r'\{([^\}]+)\}')
            sweepex = re.compile(r'\{([^\}]+)\|([^ \}]+)\}')
            brackrex = re.compile(r'\[([^\]]+)\]')

        if not os.path.isfile(template_path):
            err(f'Could not find template file {template_path}.')
            self.result['type'] = ResultType.ERROR
            return

        # Read template into a list
        with open(template_path, 'r') as infile:
            template_text = infile.read()

        # Concatenate any continuation lines
        template_lines = template_text.replace('\n+', ' ').splitlines()

        def varex_sub(matchobj):
            cond_name = matchobj.group(1)
            dbg(f'Found condition: {cond_name}.')

            # For condition names in the form {cond=value}, use only the name
            if '=' in cond_name:
                (cond_name, default) = cond_name.split('=')

            # Check for bit slices
            indices = None
            pmatch = self.vectrex.match(cond_name)
            if pmatch:
                cond_name = pmatch.group(1)
                indices = pmatch.group(2).split(':')

            # Check whether the condition is in the set
            if cond_name in conditions_set:

                # Condition not defined
                if conditions_set[cond_name] == None:
                    return matchobj.group(0)

                # Simply replace with the full value
                if not indices:
                    replace = str(conditions_set[cond_name])
                # Extract certain bits
                else:
                    try:

                        # Single bit
                        if len(indices) == 1:
                            # Convert number into binary first
                            length = int(indices[0]) + 1
                            binary = format(
                                int(conditions_set[cond_name]), f'0{length}b'
                            )
                            end = len(binary)
                            replace = binary[end - 1 - int(indices[0])]
                        # Bit slice
                        elif len(indices) == 1:
                            # Convert number into binary first
                            length = max(
                                int(indices[0]) + 1, int(indices[1]) + 1
                            )
                            binary = format(
                                int(conditions_set[cond_name]), f'0{length}b'
                            )
                            end = len(binary)
                            replace = binary[
                                end
                                - 1
                                - int(indices[0]) : end
                                - int(indices[1])
                            ]
                        else:
                            err(
                                f'This bit slice is not supported: {matchobj.group(1)}'
                            )
                            return ''
                    except:
                        err(
                            f"Can't extract bit from: {conditions_set[cond_name]}"
                        )
                        return ''

                dbg(f'Replacing with {replace}.')
                return replace
            else:
                err(f'Could not find {cond_name} in condition set.')

            # Error, do not change the condition value
            return matchobj.group(0)

        def sweepex_sub(matchobj):
            cond_name = matchobj.group(1)
            cond_type = matchobj.group(2)
            dbg(f'Found condition: {cond_name} with type {cond_type}.')

            if cond_name in conditions:
                if cond_type in conditions[cond_name].spec:
                    replace = str(conditions[cond_name].spec[cond_type])
                    dbg(f'Replacing with {replace}.')
                    return replace
                else:
                    err(
                        f'Could not find {cond_type} in {cond_name} in conditions.'
                    )
            else:
                err(f'Could not find {cond_name} in conditions.')
            return ''

        def brackrex_sub(matchobj):
            expression = matchobj.group(1)
            dbg(f'Found expression: {expression}.')

            try:
                # Avoid catching simple array indexes like "v[0]".
                # Other non-expressions will just throw exceptions
                # when passed to safe_eval().
                btest = int(expression)
                return matchobj.group(0)
            except:
                pass

            try:
                return str(safe_eval(expression))
            except (ValueError, SyntaxError):
                err(f'Invalid expression: {expression}.')
            return ''

        # Substitute values
        substituted_lines = []
        for template_line in template_lines:

            # Substitute variable name at {name|maximum}
            template_line = sweepex.sub(sweepex_sub, template_line)

            # Substitute variable name {name}
            template_line = varex.sub(varex_sub, template_line)

            # Evaluate expressions [2 + 2]
            template_line = brackrex.sub(brackrex_sub, template_line)

            substituted_lines.append(template_line)

        # Write the output file
        with open(substituted_path, 'w') as outfile:
            for line in substituted_lines:
                outfile.write(f'{line}\n')

    def makeplot(self, condition_sets, conditions, results_for_plot):

        info(
            f'Parameter {self.param["name"]}: Plotting to \'[repr.filename][link=file://{os.path.abspath(self.param_dir)}]{os.path.relpath(self.param_dir)}[/link][/repr.filename]\'…'
        )

        if (
            not 'yaxis' in self.param['plot']
            and not 'xaxis' in self.param['plot']
        ):
            err('Neither yaxis or xaxis specified.')

        xvariable = None
        if 'xaxis' in self.param['plot']:
            xvariable = self.param['plot']['xaxis']
        xdisplay = xvariable
        xunit = ''

        yvariable = None
        if 'yaxis' in self.param['plot']:
            yvariable = self.param['plot']['yaxis']
        ydisplay = yvariable
        yunit = ''

        # The result variable inherits display
        # and unit from the parameter
        if xvariable == 'result':
            xdisplay = self.param['display']
            xunit = self.param['unit']

        # The result variable inherits display
        # and unit from the parameter
        if xvariable == 'result':
            xdisplay = self.param['display']
            xunit = self.param['unit']

        # For other variables see if there is an entry
        if 'variables' in self.param:
            if xvariable in self.param['variables']:
                if 'display' in self.param['variables'][xvariable]:
                    xdisplay = self.param['variables'][xvariable]['display']
                if 'unit' in self.param['variables'][xvariable]:
                    xunit = self.param['variables'][xvariable]['unit']

            if yvariable in self.param['variables']:
                if 'display' in self.param['variables'][yvariable]:
                    ydisplay = self.param['variables'][yvariable]['display']
                if 'unit' in self.param['variables'][yvariable]:
                    yunit = self.param['variables'][yvariable]['unit']

        # Create a new figure
        param_fig = Figure()

        # Set the title, if given
        if 'title' in self.param['plot']:
            fig.suptitle(self.param['plot']['title'])

        # Filename for the whole parameter plot
        filename = f'{self.param["name"]}.png'
        if 'filename' in self.param['plot']:
            filename = self.param['plot']['filename']

        # Create a new axis for the whole parameter
        param_ax = param_fig.add_subplot(111)

        # Get the plot type
        plot_type = 'xyplot'
        if 'type' in self.param['plot']:
            plot_type = self.param['plot']['type']

        # Set the title, if given
        stacked = False
        if 'stacked' in self.param['plot']:
            if self.param['plot']['stacked']:
                stacked = True

        # Set x and y labels
        param_ax.set_xlabel(xdisplay)
        param_ax.set_ylabel(ydisplay)

        # Enable the grid
        if 'grid' in self.param['plot']:
            if self.param['plot']['grid']:
                param_ax.grid(True)

        # Set opacity for histogram
        opacity = 1.0
        if len(condition_sets) > 1:
            opacity = 0.5

        # Get the result
        max_digits = len(str(len(condition_sets)))
        for index, condition_set in enumerate(condition_sets):

            # Create a new figure, just for this run
            run_fig = Figure()

            # Set the title, if given
            if 'title' in self.param['plot']:
                run_fig.suptitle(self.param['plot']['title'])

            # Create a new axis just for this run
            run_ax = run_fig.add_subplot(111)

            # Set x and y labels
            run_ax.set_xlabel(xdisplay)
            run_ax.set_ylabel(ydisplay)

            # Enable the grid
            if 'grid' in self.param['plot']:
                if self.param['plot']['grid']:
                    run_ax.grid(True)

            # Get directory for this run
            outpath = os.path.join(
                self.param_dir, f'run_{index:0{max_digits}d}'
            )

            # Get the results for this plot
            collated_variable_values = results_for_plot[index]

            xvalues = None
            if xvariable:
                # Is the variable a simulation result?
                if xvariable in collated_variable_values:
                    xvalues = collated_variable_values[xvariable]
                # Else it may be a condition?
                elif xvariable in condition_set:
                    xvalues = condition_set[xvariable]
                else:
                    err(f'Unknown variable: {xvariable}')

            yvalues = None
            if yvariable:
                # Is the variable a simulation result?
                if yvariable in collated_variable_values:
                    yvalues = collated_variable_values[yvariable]
                # Else it may be a condition?
                elif yvariable in condition_set:
                    yvalues = condition_set[yvariable]
                else:
                    err(f'Unknown variable: {yvariable}')

            marker = None
            if not isinstance(xvalues, list) or len(xvalues) == 1:
                marker = 'o'

            # Get the label for the legend
            label = []
            for condition in condition_set:
                if condition in conditions:
                    # Only add conditions with more than one value
                    if len(conditions[condition].values) > 1:
                        label.append(
                            f'{condition} = {condition_set[condition]}'
                        )
            label = ', '.join(label)

            self.plot(
                xvalues,
                yvalues,
                [param_ax, run_ax],
                plot_type,
                label,
                marker,
                stacked,
                opacity,
            )

            # Plot other variables than xvariable or yvariable
            if 'variables' in self.param:
                for variable in self.param['variables']:
                    if variable != xvariable and variable != yvariable:
                        # Is the variable a simulation result?
                        if variable in collated_variable_values:
                            yvalues = collated_variable_values[variable]
                        else:
                            err(f'Unknown variable: {xvariable}')

                        label = variable

                        self.plot(
                            xvalues,
                            yvalues,
                            [run_ax],
                            plot_type,
                            label,
                            marker,
                            stacked,
                        )

            # Enable the legend
            legend = None
            if 'legend' in self.param['plot'] and self.param['plot']['legend']:
                legend = run_ax.legend(
                    loc=2, bbox_to_anchor=(1.04, 1), borderaxespad=0.0
                )

            # Save the figure for this run
            if legend:
                run_fig.savefig(
                    os.path.join(outpath, filename),
                    bbox_inches='tight',
                    bbox_extra_artists=[legend],
                )
            else:
                run_fig.savefig(
                    os.path.join(outpath, filename), bbox_inches='tight'
                )

        # Plot other variables than xvariable or yvariable
        if 'variables' in self.param:
            for variable in self.param['variables']:
                if variable != xvariable and variable != yvariable:
                    # Is the variable a simulation result?
                    if variable in collated_variable_values:
                        yvalues = collated_variable_values[variable]
                    else:
                        err(f'Unknown variable: {xvariable}')

                    label = variable
                    self.plot(
                        xvalues,
                        yvalues,
                        [param_ax],
                        plot_type,
                        label,
                        marker,
                        stacked,
                    )

        # Enable the legend
        legend = None
        if len(condition_sets) > 1 or (
            'legend' in self.param['plot'] and self.param['plot']['legend']
        ):
            legend = param_ax.legend(
                loc=2, bbox_to_anchor=(1.04, 1), borderaxespad=0.0
            )

        # Save the figure for the whole parameter
        if legend:
            param_fig.savefig(
                os.path.join(self.param_dir, filename),
                bbox_inches='tight',
                bbox_extra_artists=[legend],
            )
        else:
            param_fig.savefig(
                os.path.join(self.param_dir, filename), bbox_inches='tight'
            )

    def plot(
        self,
        xvalues,
        yvalues,
        axes,
        plot_type='xyplot',
        label=None,
        marker=None,
        stacked=False,
        alpha=1.0,
    ):
        if plot_type == 'histogram':
            for ax in axes:
                ax.hist(
                    xvalues,
                    bins='auto',
                    histtype='bar',
                    label=label,
                    stacked=stacked,
                    alpha=alpha,
                )
        elif plot_type == 'semilogx':
            for ax in axes:
                ax.semilogx(xvalues, yvalues, label=label, marker=marker)
        elif plot_type == 'semilogy':
            for ax in axes:
                ax.semilogy(xvalues, yvalues, label=label, marker=marker)
        elif plot_type == 'loglog':
            for ax in axes:
                ax.loglog(xvalues, yvalues, label=label, marker=marker)
        elif plot_type == 'xyplot':
            for ax in axes:
                ax.plot(xvalues, yvalues, label=label, marker=marker)
        else:
            err(f'Unknown plot type: {plot_type}')
