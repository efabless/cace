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
import sys
import json
import time
import signal
import logging
import argparse
from fnmatch import fnmatch
from datetime import timedelta
from rich.markdown import Markdown
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeElapsedColumn,
    TaskID,
)

from .__version__ import __version__
from .parameter import ParameterManager
from .logging import (
    LevelFilter,
    console,
    set_log_level,
    register_additional_handler,
    deregister_additional_handler,
)
from .logging import (
    dbg,
    verbose,
    info,
    subproc,
    rule,
    success,
    warn,
    err,
)

from .parameter.parameter import ResultType


def start_parameter(param, progress, task_ids, steps):
    pname = param['name']
    # Add a new task for the parameter
    task_ids[pname] = progress.add_task(
        param['display'] if 'display' in param else pname,
    )
    # Set total amount of steps
    progress.update(task_ids[pname], total=steps)


def step_parameter(param, progress, task_ids):
    pname = param['name']

    if pname in task_ids:
        # Update task for parameter
        progress.update(task_ids[pname], advance=1)
    else:
        warn('Step update for non existing parameter.')


def end_parameter(param, progress, task_ids, task_id):
    pname = param['name']
    if pname in task_ids:
        # Remove task for parameter
        progress.remove_task(task_ids[pname])

        # Update the main progress bar
        progress.update(task_id, advance=1)
    else:
        warn('Cannot remove non existing parameter.')


def cli():
    """
    Read a text file in CACE (ASCII) format 4.0, run
    simulations and analysis on electrical and physical
    parameters, as appropriate, and write out a modified
    file with simulation and analysis results.
    """

    parser = argparse.ArgumentParser(
        prog='cace',
        description="""This program parses the CACE characterization 
        file, runs simulations, and can output a modified file annotated with 
        characterization results.""",
        epilog='Online documentation at: https://cace.readthedocs.io/',
    )

    # version number
    parser.add_argument(
        '--version', action='version', version=f'%(prog)s {__version__}'
    )

    # positional argument, optional
    parser.add_argument(
        'datasheet', nargs='?', help='input specification datasheet (YAML)'
    )

    # positional argument, optional
    parser.add_argument(
        'output',
        nargs='?',
        help='output specification datasheet (YAML), used to convert a datasheet to a newer format',
    )

    # total number of jobs, optional
    parser.add_argument(
        '-j',
        '--jobs',
        type=int,
        help="""total number of jobs running in parallel""",
    )
    parser.add_argument(
        '-s',
        '--source',
        type=str,
        choices=['schematic', 'layout', 'pex', 'rcx', 'best'],
        default='best',
        help="""choose the netlist source for characterization. By default, or when using \'best\', characterization is run on the full R-C
    parasitic extracted netlist if the layout is available, else on the schematic captured netlist.""",
    )
    parser.add_argument(
        '-p',
        '--parameter',
        nargs='+',
        default=None,
        help='run simulations on only the named parameters, by default run all parameters. Has support for wildcards (*) to match parts of parameters.',
    )
    parser.add_argument(
        '-sp',
        '--skip-parameter',
        nargs='+',
        default=None,
        help='list parameters that should be skipped. Has support for wildcards (*) to match parts of parameters.',
    )
    parser.add_argument(
        '--parallel-parameters',
        type=int,
        default=4,
        help='the maximum number of parameters running in parallel',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='force new regeneration of all netlists',
    )
    parser.add_argument(
        '--max-runs',
        type=lambda value: int(value) if int(value) > 0 else 1,
        help="""the maximum number of runs to keep in the "runs/" folder, the oldest runs will be deleted""",
    )
    parser.add_argument(
        '--run-path',
        type=str,
        help='override the default "runs/" directory',
    )
    parser.add_argument(
        '--no-plot', action='store_true', help='do not generate any graphs'
    )
    parser.add_argument(
        '-l',
        '--log-level',
        type=str,
        choices=['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help="""set the log level for a more fine-grained output""",
    )
    parser.add_argument(
        '--sequential',
        action='store_true',
        help='runs simulations sequentially',
    )
    parser.add_argument(
        '--no-progress-bar',
        action='store_true',
        help='do not display the progress bar',
    )
    parser.add_argument(
        '--nofail',
        action='store_true',
        help='do not fail on any errors or failing parameters',
    )

    # Parse arguments
    args = parser.parse_args()

    # Set the log level
    if args.log_level:
        set_log_level(args.log_level)

    # Create the ParameterManager
    parameter_manager = ParameterManager(
        max_runs=args.max_runs, run_path=args.run_path, jobs=args.jobs
    )

    # Load the datasheet
    if args.datasheet:
        if parameter_manager.load_datasheet(args.datasheet):
            sys.exit(0)
    # Else search for it starting from the cwd
    else:
        if parameter_manager.find_datasheet(os.getcwd()):
            sys.exit(0)

    # Save the datasheet
    if args.output:
        parameter_manager.save_datasheet(args.output)

    # Log warnings and errors to files
    handlers: List[logging.Handler] = []
    for level in ['WARNING', 'ERROR']:
        path = os.path.join(parameter_manager.run_dir, f'{level.lower()}.log')
        handler = logging.FileHandler(path, mode='a+')
        handler.setLevel(level)
        handler.addFilter(LevelFilter([level]))
        handlers.append(handler)
        register_additional_handler(handler)

    # Log everything to a file
    path = os.path.join(parameter_manager.run_dir, 'flow.log')
    handler = logging.FileHandler(path, mode='a+')
    handler.setLevel('VERBOSE')
    handlers.append(handler)
    register_additional_handler(handler)

    # Set runtime options
    parameter_manager.set_runtime_options('force', args.force)
    parameter_manager.set_runtime_options('noplot', args.no_plot)
    parameter_manager.set_runtime_options('nosim', False)
    parameter_manager.set_runtime_options('sequential', args.sequential)
    parameter_manager.set_runtime_options('netlist_source', args.source)
    parameter_manager.set_runtime_options(
        'parallel_parameters', args.parallel_parameters
    )

    # Create the progress bar
    progress = Progress(
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=args.no_progress_bar,
    )

    # Add a single task for all parameters
    progress.start()
    task_id = progress.add_task(
        'Running Parameters',
    )
    task_ids = {}

    # Get the start timestamp
    timestamp_start = time.time()

    # Get all available parameters
    pnames = parameter_manager.get_all_pnames()

    # Queued parameter names
    queued_pnames = []

    # Queue specified parameters
    if args.parameter:
        dbg(f'Queuing parameters: {args.parameter}')

        for pname in args.parameter:
            # Directly queue a parameter name
            if pname in pnames:
                queued_pnames.append(pname)
            # Try to match pattern
            else:
                match_pnames = [
                    _pname for _pname in pnames if fnmatch(_pname, pname)
                ]

                if not match_pnames:
                    err(f'{pname} does not match any parameters.')
                    err(f'Known parameters are: {", ".join(pnames)}')
                    sys.exit(1)

                for match_pname in match_pnames:
                    queued_pnames.append(match_pname)
    # Queue all parameters
    else:
        queued_pnames = pnames

    # Skip specified parameters
    if args.skip_parameter:
        dbg(f'Skipping parameters: {args.skip_parameter}')

        for pname in args.skip_parameter:
            # Directly remove a parameter name
            if pname in queued_pnames:
                queued_pnames.remove(pname)
            # Try to match pattern
            else:
                match_pnames = [
                    _pname
                    for _pname in queued_pnames
                    if fnmatch(_pname, pname)
                ]

                if not match_pnames:
                    err(f'{pname} does not match any queued parameters.')
                    err(f'Queued parameters are: {", ".join(queued_pnames)}')
                    sys.exit(1)

                for match_pname in match_pnames:
                    queued_pnames.remove(match_pname)

    if not queued_pnames:
        err('No parameters specified to run.')
        sys.exit(1)

    info(f'Running parameters: {", ".join(queued_pnames)}')

    for queued_pname in queued_pnames:
        if not queued_pname in pnames:
            err(f'Unknown parameter {queued_pname}.')
            err(f'Known parameters are: {", ".join(pnames)}')
            sys.exit(1)

    for pname in queued_pnames:
        parameter_manager.queue_parameter(
            pname,
            start_cb=lambda param, steps: start_parameter(
                param, progress, task_ids, steps
            ),
            step_cb=lambda param: step_parameter(param, progress, task_ids),
            cancel_cb=lambda param: end_parameter(
                param, progress, task_ids, task_id
            ),
            end_cb=lambda param: end_parameter(
                param, progress, task_ids, task_id
            ),
        )

    # Set the total number of parameters in the progress bar
    progress.update(task_id, total=parameter_manager.num_queued_parameters())

    # Ctrl+C to cancel parameters
    signal.signal(
        signal.SIGINT, lambda sig, frame: parameter_manager.cancel_parameters()
    )

    # Run the simulations
    parameter_manager.run_parameters_async()

    # Wait for completion
    parameter_manager.join_parameters()
    result_types = parameter_manager.get_result_types()

    # Remove main progress bar
    progress.remove_task(task_id)

    # Stop the progress bar
    progress.stop()

    # Get the runtime and print it
    delta = str(timedelta(seconds=time.time() - timestamp_start)).split('.')[0]
    info(f'Done with CACE simulations and evaluations in {delta}.')

    # Print the summary to the console
    summary = parameter_manager.summarize_datasheet()
    console.print(Markdown(summary))

    # Save the summary
    with open(
        os.path.join(parameter_manager.run_dir, 'summary.md'), 'w'
    ) as ofile:
        ofile.write(summary)

    for registered_handlers in handlers:
        deregister_additional_handler(registered_handlers)

    # Get the return code based on all results
    returncode = 0
    for result_type in result_types.values():
        # An error happened
        if result_type == ResultType.ERROR:
            returncode = 1
        # Did not meet spec
        elif result_type == ResultType.FAILURE:
            returncode = 2
        # Something unexpected happened
        elif result_type == ResultType.UNKNOWN:
            returncode = 3
        # Parameter was cancelled
        elif result_type == ResultType.CANCELED:
            returncode = 4

    # Create the documentation
    if returncode == 0 or args.nofail:
        parameter_manager.generate_documentation()
    else:
        info(f'CACE failed, skipping documentation generation.')

    # Exit with final status
    if args.nofail:
        sys.exit(0)
    else:
        sys.exit(returncode)


if __name__ == '__main__':
    cli()
