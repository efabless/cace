#!/usr/bin/env python3
#
# --------------------------------------------------------
# Circuit Automatic Characterization Engine (CACE) system
# cace.py ---
# Read a text file in CACE (ASCII) format 4.0, run
# all simulations and analysis on electrical and physical
# parameters, as appropriate, and write out a modified
# file with simulation and analysis results.
#
# --------------------------------------------------------
# Written by Tim Edwards
# Efabless Corporation
# November 22, 2023
# For CACE version 4.0
# --------------------------------------------------------

import os
import sys
import json
import signal
import argparse

from .common.cace_read import *
from .common.cace_compat import *
from .common.cace_write import *
from .common.cace_gensim import *
from .common.cace_launch import *
from .common.cace_collate import *
from .common.cace_evaluate import *
from .common.cace_regenerate import *
from .common.cace_makeplot import *

import multiprocessing.pool

# -----------------------------------------------------------------------------
# Create a multiprocessing class that can be nested
# Solution pulled from discussion at:
# https://stackoverflow.com/questions/6974695/python-process-pool-non-daemonic
# -----------------------------------------------------------------------------


class NoDaemonProcess(multiprocessing.Process):
    @property
    def daemon(self):
        return False

    @daemon.setter
    def daemon(self, value):
        pass


class NoDaemonContext(type(multiprocessing.get_context())):
    Process = NoDaemonProcess


# We sub-class multiprocessing.pool.Pool instead of multiprocessing.Pool
# because the latter is only a wrapper function, not a proper class.
class NestablePool(multiprocessing.pool.Pool):
    def __init__(self, *args, **kwargs):
        kwargs['context'] = NoDaemonContext()
        super(NestablePool, self).__init__(*args, **kwargs)


# -----------------------------------------------------------------
# Exit the child process when SIGUSR1 is given to the process
# -----------------------------------------------------------------


def child_process_exit(signum, frame):
    print('CACE:  Received forced stop.')
    try:
        multiprocessing.current_process().terminate()
    except AttributeError:
        print('Terminate failed; Child PID is ' + str(os.getpid()))
        print('Waiting on process to finish.')


# -----------------------------------------------------------------
# cace_run_eparam
#
# Run complete characterization of a single electrical parameter
#
# Electrical parameter evaluation is a three-step process.  First,
# generate all of the simulation netlists to simulate.  Then,
# run all the simulations.  Finally, collect the simulation results
# and create plots and/or determine parameter performance limits.
#
# "datasheet" is the CACE characterization dataset
# "eparam" is the dictionary of a single electrical parameter
# -----------------------------------------------------------------


def cace_run_eparam(datasheet, eparam):

    # Quick check for skipped or blocked parameter.
    if 'status' in eparam:
        status = eparam['status']
        if status == 'skip' or status == 'blocked':
            return eparam

    noplot = False
    if 'runtime_options' in datasheet:
        runtime_options = datasheet['runtime_options']
        if 'noplot' in runtime_options:
            noplot = True
        if 'pid' in runtime_options:
            os.setpgid(os.getpid(), runtime_options['pid'])
            signal.signal(signal.SIGUSR1, child_process_exit)

    needplot = True if 'plot' in eparam else False
    needcollate = True if 'spec' in eparam else False

    eparamname = eparam['name']
    print('Evaluating electrical parameter ' + eparamname)
    cace_gensim(datasheet, eparam)

    print('Launching Simulations')
    cace_launch(datasheet, eparam)

    if needplot:
        print('Plotting results')
        cace_makeplot(datasheet, eparam)

    if needcollate:
        print('Collating results')
        eparam = cace_collate(datasheet, eparam)

    return eparam


# -----------------------------------------------------------------------
# cace_run_pparam
#
# Physical parameter evaluation is done by running scripts which do
# the task of running a tool to perform some calculation on the physical
# design, such as area measurement, DRC, or LVS.
#
# "datasheet" is the CACE characterization dataset
# "pparam" is the dictionary of a single physical parameter
# -----------------------------------------------------------------------


def cace_run_pparam(datasheet, pparam):

    # Quick check for skipped or blocked parameter.
    if 'status' in pparam:
        status = pparam['status']
        if status == 'skip' or status == 'blocked':
            return pparam

    if 'runtime_options' in datasheet:
        runtime_options = datasheet['runtime_options']
        if 'pid' in runtime_options:
            os.setpgid(os.getpid(), runtime_options['pid'])
            signal.signal(signal.SIGUSR1, child_process_exit)

    pparamname = pparam['name']
    print('Evaluating physical parameter ' + pparamname)
    return cace_evaluate(datasheet, pparam)


# -----------------------------------------------------------------------
# cace_run_all_eparams
#
# Run all electrical parameters simulations and measurements.
# This routine contains a nested multiprocessing pool.
#
# "datasheet" is the CACE characterization dataset
# -----------------------------------------------------------------------


def cace_run_all_eparams(datasheet):

    runtime_options = datasheet['runtime_options']
    if 'pid' in runtime_options:
        os.setpgid(os.getpid(), runtime_options['pid'])
        signal.signal(signal.SIGUSR1, child_process_exit)

    try:
        keepmode = runtime_options['keep']
    except:
        keepmode = False

    try:
        sequential = runtime_options['sequential']
    except:
        sequential = False

    if sequential:
        for eparam in datasheet['electrical_parameters']:
            cace_run_eparam(datasheet, eparam)
    else:
        alleparams = []
        with NestablePool() as pool:
            results = []
            idx = 0
            for eparam in datasheet['electrical_parameters']:
                eparam['sequence'] = idx
                results.append(
                    pool.apply_async(
                        cace_run_eparam,
                        (datasheet, eparam),
                    )
                )
                idx += 1

            # Replace the electrical parameter list in the datasheet with the
            # number of electrical parameters
            datasheet['electrical_parameters'] = len(
                datasheet['electrical_parameters']
            )

            for result in results:
                try:
                    presult = result.get(timeout=300)
                except Exception as e:
                    print('cace_run_eparam failed with exception:')
                    print(e)
                    presult = None
                if presult:
                    alleparams.append(presult)

        # After joining forks, 'results' contains an unordered list of
        # parameters.  Because the forks do not share memory, these
        # parameters are no longer the same as the ones in the datasheet,
        # so put everything back together here.

        maxidx = datasheet['electrical_parameters']
        datasheet['electrical_parameters'] = []
        for idx in range(0, maxidx):
            for param in alleparams:
                if param['sequence'] == idx:
                    datasheet['electrical_parameters'].append(param)
                    break

        for param in alleparams:
            param.pop('sequence')

    # Files to clean up that may have been generated
    if os.path.exists('b3v32check.log'):
        os.remove('b3v32check.log')

    # Final cleanup step:  Remove any '.tv' files from the work area.
    if keepmode == False:
        paths = datasheet['paths']
        root_path = paths['root']
        simulation_path = paths['simulation']

        files = os.listdir(os.path.join(root_path, simulation_path))
        for filename in files:
            try:
                fileext = os.path.splitext(filename)[1]
            except:
                pass
            else:
                if fileext == '.tv':
                    os.remove(
                        os.path.join(root_path, simulation_path, filename)
                    )

    # Because this comes back from multiprocessing as an unordered result,
    # add an entry to the front of the list to distinguish it.

    alleparams = []
    alleparams.append(0)
    alleparams.extend(datasheet['electrical_parameters'])
    return alleparams


# -----------------------------------------------------------------------
# cace_run_all_pparams
#
# Run all physical parameter measurements.
# This routine contains a nested multiprocessing pool.
#
# "datasheet" is the CACE characterization dataset
# -----------------------------------------------------------------------


def cace_run_all_pparams(datasheet):

    runtime_options = datasheet['runtime_options']
    if 'pid' in runtime_options:
        os.setpgid(os.getpid(), runtime_options['pid'])
        signal.signal(signal.SIGUSR1, child_process_exit)

    try:
        sequential = runtime_options['sequential']
    except:
        sequential = False

    if sequential:
        for pparam in datasheet['physical_parameters']:
            cace_run_pparam(datasheet, pparam)
    else:
        allpparams = []
        with NestablePool() as pool:
            results = []
            idx = 0
            for pparam in datasheet['physical_parameters']:
                pparam['sequence'] = idx
                results.append(
                    pool.apply_async(
                        cace_run_pparam,
                        (datasheet, pparam),
                    )
                )
                idx += 1

            # Replace the physical parameter list in the datasheet with the
            # number of physical parameters
            datasheet['physical_parameters'] = len(
                datasheet['physical_parameters']
            )

            for result in results:
                try:
                    presult = result.get(timeout=300)
                except Exception as e:
                    print('cace_run_pparam failed with exception:')
                    print(e)
                    presult = None
                if presult:
                    allpparams.append(presult)

        # After joining forks, 'results' contains an unordered list of
        # parameters.  Because the forks do not share memory, these
        # parameters are no longer the same as the ones in the datasheet,
        # so put everything back together here.

        maxidx = datasheet['physical_parameters']
        datasheet['physical_parameters'] = []
        for idx in range(0, maxidx):
            for param in allpparams:
                if param['sequence'] == idx:
                    datasheet['physical_parameters'].append(param)
                    break

        for param in allpparams:
            param.pop('sequence')

        allpparams = []
        allpparams.append(1)
        allpparams.extend(datasheet['physical_parameters'])
        return allpparams


# -----------------------------------------------------------------
# cace_run
#
# Run CACE on a characterization datasheet.
#
# "datasheet" is the CACE characterization dataset
# "paramnames" is an optional list of parameter names, which if present may
# 	be the names of electrical parameters or a physical
# 	parameters.  If omitted, then characterization is run on
# 	the full set of electrical and physical parameters in the
# 	datasheet.
# -----------------------------------------------------------------


def cace_run(datasheet, paramnames=[]):

    if 'runtime_options' in datasheet:
        runtime_options = datasheet['runtime_options']
        source = runtime_options['netlist_source']
    else:
        source = 'best'
        runtime_options = {}
        runtime_options['netlist_source'] = source
        runtime_options['debug'] = False
        runtime_options['keep'] = False
        runtime_options['sequential'] = False
        datasheet['runtime_options'] = runtime_options

    valid_sources = ['best', 'all', 'schematic', 'layout', 'pex', 'rcx']
    if source not in valid_sources:
        print('Invalid value for the netlist source.  Valid values are:')
        print('    ' + ' '.join(valid_sources))
        print('No characterization will be done.')
        runtime_options['status'] = 'failed'
        return datasheet

    try:
        debug = runtime_options['debug']
    except:
        debug = False

    try:
        sequential = runtime_options['sequential']
    except:
        sequential = False

    # Get the set of paths from the characterization file
    paths = datasheet['paths']

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

    fullnetlistpath = regenerate_netlists(datasheet)
    if not fullnetlistpath:
        print('Failed to regenerate project netlist;  stopping.')
        runtime_options['status'] = 'failed'
        return datasheet

    if not paramnames:

        # From this point:  Running characterization on the entire datasheet
        # (all electrical and physical parameters)

        # Generate testbench netlists if needed
        result = regenerate_testbenches(datasheet, paramnames)
        if result == 1:
            print('Failed to regenerate testbench netlists;  stopping.')
            runtime_options['status'] = 'failed'
            return datasheet

        if sequential:
            cace_run_all_eparams(datasheet)
            cace_run_all_pparams(datasheet)
        else:
            poolresult = []
            with NestablePool() as top_pool:
                results = []
                # Note:  datasheet must be cast as a list if it is a single argument.
                results.append(
                    top_pool.apply_async(
                        cace_run_all_eparams,
                        [datasheet],
                    )
                )
                results.append(
                    top_pool.apply_async(
                        cace_run_all_pparams,
                        [datasheet],
                    )
                )

                for result in results:
                    try:
                        presult = result.get(timeout=300)
                    except Exception as e:
                        print('cace_run_all_[e|p]param failed with exception:')
                        print(e)
                        presult = None
                    poolresult.append(presult)

            # The pool results may arrive in either order, so arrange them properly.
            if poolresult[0]:
                idx0 = poolresult[0][0]
                datasheet['electrical_parameters'] = poolresult[idx0][1:]
            if poolresult[1]:
                idx1 = poolresult[1][0]
                datasheet['physical_parameters'] = poolresult[idx1][1:]

    else:

        for paramname in paramnames:

            # Generate testbench netlists if needed
            result = regenerate_testbenches(datasheet, paramname)
            if result == 1:
                print('Failed to regenerate testbench netlists;  stopping.')
                runtime_options['status'] = 'failed'
                return datasheet

            # Handle a single parameter

            # Special option paramname = "check" is used to run the
            # proceeding code to regenerate DUT and testbench netlists,
            # and then return.
            if paramname == 'check':
                runtime_options['status'] = 'passed'
                return datasheet

            # Scan the names of electrical and physical parameters to
            # see whether the indicated parameter to check is an
            # electrical or physical parameter, and call the appropriate
            # routine to handle it.

            found = False
            if 'electrical_parameters' in datasheet:
                for eparam in datasheet['electrical_parameters']:
                    if eparam['name'] == paramname:
                        cace_run_eparam(datasheet, eparam)
                        found = True
                        break
            if 'physical_parameters' in datasheet:
                for pparam in datasheet['physical_parameters']:
                    if pparam['name'] == paramname:
                        cace_run_pparam(datasheet, pparam)
                        found = True
                        break

            if not found:
                print('\nError:  No parameter named ' + paramname + ' found!')
                print('Valid electrical parameter names are:')
                for eparam in datasheet['electrical_parameters']:
                    print('   ' + eparam['name'])
                print('Valid physical parameter names are:')
                for pparam in datasheet['physical_parameters']:
                    print('   ' + pparam['name'])

    return datasheet


# -----------------------------------------------------------------
# Print usage statement
# -----------------------------------------------------------------


def usage():
    print('Usage:')
    print('')
    print('cace.py <filename_in> <filename_out> [options]')
    print('  Where <filename_in> is a format 4.0 ASCII CACE file.')
    print('  And <filename_out> is the name of the file to write.')
    print('')
    print('options may be one of:')
    print('  -source=schematic|layout|rcx|all|best')
    print('  -param=<parameter_name>')
    print('  -force')
    print('  -json')
    print('  -keep')
    print('  -debug')
    print('  -sequential')
    print('  -summary')
    print('')
    print('When run from the top level, this program parses the CACE')
    print('characterization file, runs simulations, and outputs a')
    print('modified file annotated with characterization results.')
    print('')
    print('With option "-source", restrict characterization to the')
    print('specific netlist source, which is either schematic capture,')
    print('layout extracted, or full R-C parasitic extracted.  If not')
    print('specified, then characterization is run on the full R-C')
    print('parasitic extracted layout netlist if available, and the')
    print('schematic captured netlist if not (option "best").')
    print('')
    print('Option "-param=<parameter_name>" runs simulations on only')
    print('the named electrical or physical parameter.')
    print('')
    print('Option "-force" forces new regeneration of all netlists.')
    print('')
    print('Option "-json" generates an output file in JSON format.')
    print('')
    print('Option "-keep" retains files generated for characterization.')
    print('')
    print('Option "-noplot" will not generate any graphs.')
    print('')
    print('Option "-debug" generates additional diagnostic output.')
    print('')
    print('Option "-sequential" runs simulations sequentially.')
    print('')
    print(
        'Option "-nosim" does not re-run simulations if the output file exists.'
    )
    print('   (Warning---does not check if simulations are out of date).')
    print('')
    print('Option "-summary" prints a summary of results at the end.')


# -----------------------------------------------------------------
# Top level call to cace.py
# If called from the command line
# -----------------------------------------------------------------


def cli():
    parser = argparse.ArgumentParser(
        prog='cace',
        description="""This program parses the CACE characterization 
        file, runs simulations, and can output a modified file annotated with 
        characterization results.""",
        epilog='Online documentation at: https://cace.readthedocs.io/',
    )

    # positional argument
    parser.add_argument('datasheet', help='format 4.0 ASCII CACE file')

    # positional argument, optional
    parser.add_argument('outfile', nargs='?', help='name of the file to write')

    parser.add_argument(
        '-s',
        '--source',
        type=str,
        choices=['schematic', 'layout', 'rcx', 'all', 'best'],
        default='best',
        help="""restricts characterization to the
        specific netlist source, which is either schematic capture
        layout extracted, or full R-C parasitic extracted.  If not
        specified, then characterization is run on the full R-C
        parasitic extracted layout netlist if available, and the
        schematic captured netlist if not (option "best")""",
    )
    parser.add_argument(
        '-p',
        '--parameter',
        nargs='+',
        default=None,
        help='runs simulations on only the named electrical or physical parameters, by default it runs all parameters',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='forces new regeneration of all netlists',
    )
    parser.add_argument(
        '-j',
        '--json',
        action='store_true',
        help='generates an output file in JSON format',
    )
    parser.add_argument(
        '-k',
        '--keep',
        action='store_true',
        help='retains files generated for characterization',
    )
    parser.add_argument(
        '--no-plot', action='store_true', help='do not generate any graphs'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='generates additional diagnostic output',
    )
    parser.add_argument(
        '--sequential',
        action='store_true',
        help='runs simulations sequentially',
    )
    parser.add_argument(
        '--no-simulation',
        action='store_true',
        help="""does not re-run simulations if the output file exists.
    (Warning: Does not check if simulations are out of date)""",
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='prints a summary of results at the end',
    )

    # Parse arguments
    args = parser.parse_args()

    # If the file is a JSON file, read it with json.load
    if os.path.splitext(args.datasheet)[1] == '.json':
        with open(args.datasheet, 'r') as ifile:
            dataset = json.load(ifile)
            if 'data-sheet' in dataset:
                dataset = dataset['data-sheet']
                # Attempt to upgrade this to format 4.0
                dataset = cace_compat(dataset, args.debug)
    else:
        dataset = cace_read(args.datasheet, args.debug)

    if dataset == {}:
        print('No dataset was returned.')
        sys.exit(1)

    # If there is a "paths" dictionary in dataset and it does
    # not have an entry for "root", then find the name of the
    # directory where "filename" exists and set that to root.
    filepath = os.path.split(os.path.realpath(args.datasheet))[0]
    if 'paths' in dataset:
        paths = dataset['paths']
        if 'root' not in paths:
            paths['root'] = filepath

    # Set the current working directory to the root by first
    # setting the current working directory to the path of
    # the testbench file and then setting it to root (assuming
    # root is a relative path, although it could be an absolute
    # path).
    os.chdir(filepath)
    os.chdir(paths['root'])
    paths['root'] = os.getcwd()
    if args.debug:
        print('Working directory set to project root at ' + paths['root'])

    # All run-time options are dropped into a dictionary,
    # passed to all routines, and removed at the end.
    runtime_options = {}
    runtime_options['debug'] = args.debug
    runtime_options['force'] = args.force
    runtime_options['json'] = args.json
    runtime_options['keep'] = args.keep
    runtime_options['noplot'] = args.no_plot
    runtime_options['nosim'] = args.no_simulation
    runtime_options['sequential'] = args.sequential
    runtime_options['netlist_source'] = args.source

    # Add the name of the file to the top-level dictionary
    runtime_options['filename'] = os.path.split(args.datasheet)[1]

    dataset['runtime_options'] = runtime_options

    # Run CACE. Use only as directed.
    charresult = cace_run(dataset, args.parameter)
    if args.debug:
        print('Done with CACE simulations and evaluations.')

    if charresult == {}:
        print('No results were returned.')
        sys.exit(1)

    if args.outfile:
        if args.debug:
            print('Writing final output file ' + args.outfile)
        if dojson:
            # Dump the result as a JSON file
            jsonfile = os.path.splitext(args.outfile)[0] + '_debug.json'
            with open(jsonfile, 'w') as ofile:
                json.dump(charresult, ofile, indent=4)
        else:
            # Write the result in CACE ASCII format version 4.0
            cace_write(charresult, args.outfile, doruntime=False)

    if args.summary:
        print('')
        print('CACE Summary of results:')
        print('------------------------')
        cace_summary(charresult, args.parameter)


if __name__ == '__main__':
    cli()
