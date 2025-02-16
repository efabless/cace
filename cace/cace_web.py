from flask import Flask, render_template, request, Response
from .parameter import ParameterManager

import queue
import jinja2
import json
import os
import mpld3

# TODO: These should be options on the web interface
parameter_manager = ParameterManager(max_runs=None, run_path=None, jobs=None)
parameter_manager.find_datasheet(os.getcwd())
paramkey_paramdisplay = {
    i: j.get('display', i)
    for i, j in parameter_manager.datasheet['parameters'].items()
}
paramdisplay_paramkey = {
    j.get('display', i): i
    for i, j in parameter_manager.datasheet['parameters'].items()
}

any_queue = queue.Queue()
figures = {}

app = Flask(__name__, template_folder='web', static_folder='web/static')

PROGRESS_TEMPLATE = jinja2.Template(
    """
<table id="progress_table">
  <thead>
    <tr>
      <th>Param</th>
      <th>Progress</th>
    </tr>
  </thead>
  <tbody>
    {% for param in params %}
    <tr>
      <td>{{ param }}</td>
      <td>
        <progress id="{{param}}" value="0" max="100"></progress>
      </td>
    </tr>
    {% endfor %}
    <tr>
      <td>Overall Progress</td>
      <td>
        <progress id="overall_pb" value="0" max="{{params | length}}"></progress>
      </td>
    </tr>
  </tbody>
</table>
<br>
<button id="simresultsbtn" onclick="openTab(event, 'Results')" disabled>Simulation Results</button>
<button onclick="sendData({ 'task': 'cancel_sims' });">Cancel Simulations</button>
<br>
<br>
"""
)

RESULTS_SUMMARY_TEMPLATE = jinja2.Template(
    """
<table>
  <thead>
    <tr>
      <th>Parameter</th>
      <th>Tool</th>
      <th>Result</th>
      <th>Minimum Limit</th>
      <th>Minimum Value</th>
      <th>Typical Limit</th>
      <th>Typical Value</th>
      <th>Maximum Limit</th>
      <th>Maximum Value</th>
      <th>Status</th>
    </tr>
  </thead>
  <tbody>
    {% for row in data %}
    <tr>
      <td>{{ row.parameter_str }}</td>
      <td>{{ row.tool_str }}</td>
      <td>{{ row.result_str }}</td>
      <td>{{ row.min_limit_str }}</td>
      <td>{{ row.min_value_str }}</td>
      <td>{{ row.max_limit_str }}</td>
      <td>{{ row.max_value_str }}</td>
      <td>{{ row.typ_limit_str }}</td>
      <td>{{ row.typ_value_str }}</td>
      <td>{{ row.status_str }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
"""
)

RESULTS_PLOTS_TEMPLATE = jinja2.Template(
    """
{% for div in divs %}
{{ div | safe }}
{% endfor %}
"""
)


@app.route('/')
def homepage():
    pnames = parameter_manager.get_all_pnames()
    parameter_manager.results = {}
    parameter_manager.result_types = {}
    figures = {}
    data = [{'name': pname} for pname in pnames]

    return render_template(template_name_or_list='index.html', data=data)


@app.route('/runsim', methods=['POST'])
def runsim():
    params = json.loads(request.get_data())['selected_params']

    if len(params) == 0:
        return '', 200

    for pname in params:
        parameter_manager.queue_parameter(
            pname=pname,
            start_cb=lambda param, steps: (
                any_queue.put(
                    {
                        'task': 'start',
                        'param': param,
                        'steps': steps,
                    }
                )
            ),
            step_cb=lambda param: (
                any_queue.put({'task': 'step', 'param': param})
            ),
            cancel_cb=lambda param: (
                any_queue.put({'task': 'cancel', 'param': param})
            ),
            end_cb=lambda param: (
                any_queue.put({'task': 'end', 'param': param}),
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
    any_queue.put(
        {'task': 'progress', 'html': PROGRESS_TEMPLATE.render(params=params)}
    )
    return '', 200


def generate_sse():
    datasheet = parameter_manager.datasheet['parameters']

    while True:
        aqg = any_queue.get()

        if aqg['task'] == 'end':
            for i in parameter_manager.running_threads:
                if i.param == aqg['param']:
                    aqg['status'] = i.result_type.name
                    if len(i.plots_dict) > 0:
                        figures[i.pname] = i.plots_dict
        elif aqg['task'] == 'end_stream':
            print('ending sse stream')
            return
        if 'param' in aqg:
            aqg['param'] = list(datasheet.keys())[
                list(datasheet.values()).index(aqg['param'])
            ]
        print(aqg)
        yield f'data: {json.dumps(aqg)}\n\n'


@app.route('/stream')
def stream():
    print('starting sse stream')
    return Response(generate_sse(), content_type='text/event-stream')


@app.route('/receive_data', methods=['POST'])
def receive_data():
    data = request.get_json()
    print(data)

    if data['task'] == 'end_stream':
        any_queue.put({'task': 'end_stream'})
    elif data['task'] == 'cancel_sims':
        parameter_manager.cancel_parameters()
    elif data['task'] == 'fetchresults':
        simresults()
    return '', 200


def simresults():
    parameter_manager.join_parameters()
    result = []
    divs = []

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

    for pname in figures.keys():
        divs.append(f'<h2>Figures for {paramkey_paramdisplay[pname]}</h2>')
        for figure in figures[pname]:
            fig = figures[pname][figure].figure
            fig.set_tight_layout(True)
            fig.set_size_inches(fig.get_size_inches() * 1.25)
            divs.append(mpld3.fig_to_html(fig))
    print(divs)
    any_queue.put(
        {
            'task': 'results',
            'summary': RESULTS_SUMMARY_TEMPLATE.render(data=result),
            'plots': RESULTS_PLOTS_TEMPLATE.render(divs=divs),
        }
    )
    return 200, ''


def web():
    app.run(debug=True)
