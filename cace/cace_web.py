from flask import Flask, render_template, request, Response
from .parameter import ParameterManager

import queue
import json
import os

# TODO: These should be options on the web interface
parameter_manager = ParameterManager(max_runs=None, run_path=None, jobs=None)
parameter_manager.find_datasheet(os.getcwd())

any_queue = queue.Queue()

app = Flask(__name__, template_folder='web', static_folder='web/static')


@app.route('/')
def homepage():
    pnames = parameter_manager.get_all_pnames()
    data = [{'name': pname} for pname in pnames]

    return render_template(template_name_or_list='index.html', data=data)


@app.route('/runsim', methods=['POST'])
def runsim():
    parameter_manager.results = {}
    parameter_manager.result_types = {}

    params = request.form.getlist('selected_params')

    for param in params:
        parameter_manager.queue_parameter(
            param,
            start_cb=lambda param, steps: (
                any_queue.put(
                    {'task': 'start', 'param': param, 'steps': steps}
                )
            ),
            step_cb=lambda param: (
                any_queue.put({'task': 'step', 'param': param})
            ),
            cancel_cb=lambda param: (
                any_queue.put({'task': 'cancel', 'param': param})
            ),
            end_cb=lambda param: any_queue.put(
                {'task': 'end', 'param': param}
            ),
        )

    # TODO: These should be options on the web interface
    parameter_manager.set_runtime_options('force', False)
    parameter_manager.set_runtime_options('noplot', False)
    parameter_manager.set_runtime_options('nosim', False)
    parameter_manager.set_runtime_options('sequential', False)
    parameter_manager.set_runtime_options('netlist_source', 'best')
    parameter_manager.set_runtime_options('parallel_parameters', 4)

    parameter_manager.run_parameters_async()
    return render_template(template_name_or_list='runsim.html', params=params)


def generate_sse():
    num_params = parameter_manager.num_parameters()
    datasheet = parameter_manager.datasheet['parameters']

    params_completed = 0
    while num_params != params_completed:
        aqg = any_queue.get()

        if aqg['task'] == 'end':
            params_completed += 1
        elif aqg['task'] == 'end_stream':
            return

        aqg['param'] = list(datasheet.keys())[
            list(datasheet.values()).index(aqg['param'])
        ]
        yield f'data: {json.dumps(aqg)}\n\n'

    data = {'task': 'close'}
    yield f'data: {json.dumps(data)}\n\n'


@app.route('/stream')
def stream():
    return Response(generate_sse(), content_type='text/event-stream')


@app.route('/end_stream', methods=['POST'])
def end_stream():
    any_queue.put({'task': 'end_stream'})
    return '', 200


@app.route('/simresults')
def simresults():
    parameter_manager.join_parameters()
    result = []

    summary_lines = parameter_manager.summarize_datasheet().split('\n')[7:-2]
    lengths = {
        param: len(
            list(
                parameter_manager.datasheet['parameters'][param]['spec'].keys()
            )
        )
        for param in parameter_manager.get_all_pnames()
    }
    for param in parameter_manager.get_result_types().keys():
        total = 0
        for i in parameter_manager.get_all_pnames():
            if i == param:
                for j in range(lengths[param]):
                    row = summary_lines[total + j].split('|')
                    result.append(
                        {
                            'parameter_str': row[1],
                            'tool_str': row[2],
                            'result_str': row[3],
                            'min_limit_str': row[4],
                            'min_value_str': row[5],
                            'max_limit_str': row[6],
                            'max_value_str': row[7],
                            'typ_limit_str': row[8],
                            'typ_value_str': row[9],
                            'status_str': row[10],
                        }
                    )

            total += lengths[i]

    return render_template(
        template_name_or_list='simresults.html', data=result
    )


def web():
    app.run(debug=True)
