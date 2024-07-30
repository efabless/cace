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
import tkinter
from tkinter import ttk

from .tooltip import *

binrex = re.compile(r'([0-9]*)\'([bodh])', re.IGNORECASE)


class RowWidget:
    """The RowWidget contains all widgets for a given parameter"""

    parameter_widget = None
    testbench_widget = None
    min_limit_widget = None
    min_value_widget = None
    typ_limit_widget = None
    typ_value_widget = None
    max_limit_widget = None
    max_value_widget = None
    plot_widget = None
    status_widget = None
    simulate_widget = None

    paramtype = None
    is_plot = None

    normlabel = 'normal.TLabel'
    redlabel = 'red.TLabel'
    greenlabel = 'green.TLabel'
    normbutton = 'normal.TButton'
    redbutton = 'red.TButton'
    greenbutton = 'green.TButton'

    def __init__(self, param, dframe, netlist_source, row, parameter_manager):

        self.parameter_manager = parameter_manager
        self.netlist_source = netlist_source

        # Set the new parameter
        self.update_param(param)

        # Create widgets accordingly
        self.create_widgets(dframe, row)

    def set_functions(
        self, start, stop, edit, copy, delete, failreport, textreport
    ):

        self.fnc_start = start
        self.fnc_stop = stop
        self.fnc_edit = edit
        self.fnc_copy = copy
        self.fnc_delete = delete
        self.fnc_failreport = failreport
        self.fnc_textreport = textreport

    def update_param(self, param):

        self.param = param
        pname = self.param['name']

        if 'editable' in self.param and self.param['editable'] == True:
            self.normlabel = 'hlight.TLabel'
            self.redlabel = 'rhlight.TLabel'
            self.greenlabel = 'ghlight.TLabel'
            self.normbutton = 'hlight.TButton'
            self.redbutton = 'rhlight.TButton'
            self.greenbutton = 'ghlight.TButton'
        else:
            self.normlabel = 'normal.TLabel'
            self.redlabel = 'red.TLabel'
            self.greenlabel = 'green.TLabel'
            self.normbutton = 'normal.TButton'
            self.redbutton = 'red.TButton'
            self.greenbutton = 'green.TButton'

        # Electrical parameter information
        if 'simulate' in self.param:
            self.paramtype = 'electrical'
        # Physical parameter information
        elif 'evaluate' in self.param:
            self.paramtype = 'physical'
        else:
            self.paramtype = None
            print(f'Parameter {pname} unknown type.')

        if 'plot' in param:
            self.is_plot = True
        else:
            self.is_plot = False

    def parameter_text(self):

        # Get the display text
        dtext = self.param['display']

        return dtext

    def tool_text(self):

        tool = self.param['tool']

        # Get the name of the tool
        if isinstance(tool, str):
            toolname = tool
        else:
            toolname = list(tool.keys())[0]

        return toolname

    def plot_text(self):

        plotrec = self.param['plot']
        if 'filename' in plotrec:
            plottext = plotrec['filename']
        elif 'type' in plotrec:
            plottext = plotrec['type']
        else:
            plottext = 'plot'

        return plottext

    def status_text(self):

        status_value = '(not checked)'
        button_style = self.normbutton

        if self.is_plot:
            resdict = self.get_resultdict()

            if resdict:
                if 'status' in resdict:
                    status_value = resdict['status']
        else:
            # Grab the electrical parameter's 'spec' dictionary
            if 'spec' in self.param:
                specdict = self.param['spec']
            else:
                specdict = {}

            if 'minimum' in specdict:
                (value, score) = self.get_min_results()

                if score:
                    if score != 'fail':
                        if status_value != 'fail':
                            status_value = 'pass'
                    else:
                        status_value = 'fail'
                if value:
                    if value == 'failure' or value == 'fail':
                        status_value = '(not checked)'

            if 'typical' in specdict:
                (value, score) = self.get_typ_results()

                if score:
                    # Note:  You can't fail a "typ" score, but there is only one "Status",
                    # so if it is a "fail", it must remain a "fail".
                    if score != 'fail':
                        if status_value != 'fail':
                            status_value = 'pass'
                    else:
                        status_value = 'fail'
                if value:
                    if value == 'failure' or value == 'fail':
                        status_value = '(not checked)'

            if 'maximum' in specdict:
                (value, score) = self.get_max_results()

                if score:
                    if score != 'fail':
                        if status_value != 'fail':
                            status_value = 'pass'
                    else:
                        status_value = 'fail'
                if value:
                    if value == 'failure' or value == 'fail':
                        status_value = '(not checked)'

        # Button style
        if status_value == 'fail' or status_value == 'failure':
            button_style = self.redbutton
        else:
            button_style = self.greenbutton

        return (status_value, button_style)

    def get_resultdict(self):

        # Return resultdict depending on source
        if 'results' in self.param and self.param['results']:
            resultlist = self.param['results']
            if not isinstance(resultlist, list):
                resultlist = [resultlist]

            for resultdict in resultlist:
                if resultdict['name'] == self.netlist_source:
                    return resultdict

        return {}

    def get_min_results(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        resultdict = self.get_resultdict()

        value = None
        score = None

        if 'minimum' in specdict:
            pmin = specdict['minimum']
            if isinstance(pmin, list):
                penalty = pmin[1]
                pmin = pmin[0]
            else:
                penalty = None

            if 'minimum' in resultdict:
                value = resultdict['minimum']
                if isinstance(value, list):
                    score = value[1]
                    value = value[0]

        return (value, score)

    def min_limit_text(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        # Fill in information for the spec minimum and result
        min_limit = '(no limit)'

        if 'minimum' in specdict:
            pmin = specdict['minimum']['value']

            if pmin != 'any':
                if 'unit' in self.param and not binrex.match(
                    self.param['unit']
                ):
                    targettext = f'{pmin} {self.param["unit"]}'
                else:
                    targettext = str(pmin)
                min_limit = targettext

        return min_limit

    def min_value_text(self):

        min_value = ' '
        min_status_style = self.normlabel

        (value, score) = self.get_min_results()

        if score:
            if score != 'fail':
                min_status_style = self.greenlabel
            else:
                min_status_style = self.redlabel

        if value:
            if value == 'failure' or value == 'fail':
                valuetext = value
                min_status_style = self.redlabel
            elif 'unit' in self.param and not binrex.match(self.param['unit']):
                valuetext = value + ' ' + self.param['unit']
            else:
                valuetext = value
            min_value = valuetext

        return (min_value, min_status_style)

    def get_typ_results(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        resultdict = self.get_resultdict()

        value = None
        score = None

        if 'typical' in specdict:
            ptyp = specdict['typical']
            if isinstance(ptyp, list):
                penalty = ptyp[1]
                ptyp = ptyp[0]
            else:
                penalty = None

            if 'typical' in resultdict:
                value = resultdict['typical']
                if isinstance(value, list):
                    score = value[1]
                    value = value[0]

        return (value, score)

    def typ_limit_text(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        # Fill in information for the spec minimum and result
        typ_limit = '(no target)'

        if 'typical' in specdict:
            ptyp = specdict['typical']['value']

            if ptyp != 'any':
                if 'unit' in self.param and not binrex.match(
                    self.param['unit']
                ):
                    targettext = f'{ptyp} {self.param["unit"]}'
                else:
                    targettext = str(ptyp)
                typ_limit = targettext

        return typ_limit

    def typ_value_text(self):

        typ_value = ' '
        typ_status_style = self.normlabel

        (value, score) = self.get_typ_results()

        if score:
            if score != 'fail':
                typ_status_style = self.greenlabel
            else:
                typ_status_style = self.redlabel

        if value:
            if value == 'failure' or value == 'fail':
                valuetext = value
                typ_status_style = self.redlabel
            elif 'unit' in self.param and not binrex.match(self.param['unit']):
                valuetext = value + ' ' + self.param['unit']
            else:
                valuetext = value
            typ_value = valuetext

        return (typ_value, typ_status_style)

    def get_max_results(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        resultdict = self.get_resultdict()

        value = None
        score = None

        if 'maximum' in specdict:
            pmax = specdict['maximum']
            if isinstance(pmax, list):
                penalty = pmax[1]
                pmax = pmax[0]
            else:
                penalty = None

            if 'maximum' in resultdict:
                value = resultdict['maximum']
                if isinstance(value, list):
                    score = value[1]
                    value = value[0]

        return (value, score)

    def max_limit_text(self):
        # Grab the electrical parameter's 'spec' dictionary
        if 'spec' in self.param:
            specdict = self.param['spec']
        else:
            specdict = {}

        # Fill in information for the spec minimum and result
        max_limit = '(no limit)'

        if 'maximum' in specdict:
            pmax = specdict['maximum']['value']

            if pmax != 'any':
                if 'unit' in self.param and not binrex.match(
                    self.param['unit']
                ):
                    targettext = f'{pmax} {self.param["unit"]}'
                else:
                    targettext = str(pmax)
                max_limit = targettext

        return max_limit

    def max_value_text(self):

        max_value = ' '
        max_status_style = self.normlabel

        (value, score) = self.get_max_results()

        if score:
            if score != 'fail':
                max_status_style = self.greenlabel
            else:
                max_status_style = self.redlabel

        if value:
            if value == 'failure' or value == 'fail':
                valuetext = value
                max_status_style = self.redlabel
            elif 'unit' in self.param and not binrex.match(self.param['unit']):
                valuetext = value + ' ' + self.param['unit']
            else:
                valuetext = value
            max_value = valuetext

        return (max_value, max_status_style)

    def simulate_text(self):

        if self.paramtype == 'electrical':
            if 'hints' in self.param:
                simtext = '\u2022Simulate'
            else:
                simtext = 'Simulate'
        else:
            simtext = 'Check'

        return simtext

    def create_widgets(self, dframe, n):

        pname = self.param['name']

        # Parameter name
        self.parameter_widget = ttk.Label(
            dframe, text=self.parameter_text(), style=self.normlabel
        )
        self.parameter_widget.grid(column=0, row=n, sticky='ewns')

        # Testbench name
        self.testbench_widget = ttk.Label(
            dframe, text=self.tool_text(), style=self.normlabel
        )
        self.testbench_widget.grid(column=1, row=n, sticky='ewns')

        # Get the status of the last simulation
        (status_value, button_style) = self.status_text()

        if self.is_plot:

            plot_frame = ttk.Frame(dframe)
            plot_frame.grid(column=2, row=n, columnspan=6, sticky='ewns')

            self.plot_widget = ttk.Label(
                plot_frame, text=self.plot_text(), style=self.normlabel
            )
            self.plot_widget.grid(column=0, row=n, sticky='ewns')

        else:
            # Minimum widgets
            self.min_limit_widget = ttk.Label(
                dframe, text=self.min_limit_text(), style=self.normlabel
            )
            self.min_limit_widget.grid(column=2, row=n, sticky='ewns')

            (min_value, min_status_style) = self.min_value_text()
            self.min_value_widget = ttk.Label(
                dframe, text=min_value, style=min_status_style
            )
            self.min_value_widget.grid(column=3, row=n, sticky='ewns')

            # Typical widgets
            self.typ_limit_widget = ttk.Label(
                dframe, text=self.typ_limit_text(), style=self.normlabel
            )
            self.typ_limit_widget.grid(column=4, row=n, sticky='ewns')

            (typ_value, typ_status_style) = self.typ_value_text()
            self.typ_value_widget = ttk.Label(
                dframe, text=typ_value, style=typ_status_style
            )
            self.typ_value_widget.grid(column=5, row=n, sticky='ewns')

            # Maximum widgets
            self.max_limit_widget = ttk.Label(
                dframe, text=self.max_limit_text(), style=self.normlabel
            )
            self.max_limit_widget.grid(column=6, row=n, sticky='ewns')

            (max_value, max_status_style) = self.max_value_text()
            self.max_value_widget = ttk.Label(
                dframe, text=max_value, style=max_status_style
            )
            self.max_value_widget.grid(column=7, row=n, sticky='ewns')

        # Status Widget

        # ngspice
        if self.tool_text() == 'ngspice':
            self.status_widget = ttk.Button(
                dframe,
                text=status_value,
                style=button_style,
                command=lambda pname=pname: self.fnc_failreport(pname),
            )
        # LVS
        elif self.tool_text() == 'netgen_lvs':
            filename = self.parameter_manager.get_runtime_options('filename')
            dspath = os.path.split(filename)[0]
            datasheet = os.path.split(filename)[1]
            dsheet = self.parameter_manager.get_datasheet()
            designname = dsheet['name']

            root_path = self.parameter_manager.get_path('root')

            lvs_file = os.path.join(
                root_path,
                self.parameter_manager.run_dir,
                'parameters',
                pname,
                f'{designname}_comp.out',
            )

            self.status_widget = ttk.Button(
                dframe,
                text=status_value,
                style=button_style,
                command=lambda lvs_file=lvs_file: self.fnc_textreport(
                    lvs_file
                ),
            )

        # Area
        elif self.tool_text() == 'magic_area':
            self.status_widget = ttk.Button(
                dframe,
                text=status_value,
                style=button_style,
            )

        # DRC
        elif self.tool_text() == 'magic_drc':
            self.status_widget = ttk.Button(
                dframe,
                text=status_value,
                style=button_style,
            )

        # Other parameters, disabled
        else:
            self.status_widget = ttk.Button(
                dframe, text=status_value, style=button_style, state='disabled'
            )

        # Not yet checked, disabled
        if status_value == '(not checked)' or status_value == '(N/A)':
            self.status_widget.configure(
                text=status_value, style=button_style, state='disabled'
            )

        ToolTip(
            self.status_widget,
            text='Show detail view of simulation conditions and results',
        )

        self.status_widget.grid(column=8, row=n, sticky='ewns')

        # Simulate widget
        self.simulate_widget = ttk.Menubutton(
            dframe, text=self.simulate_text(), style=self.normbutton
        )

        # Generate pull-down menu on Simulate button.  Most items apply
        # only to electrical parameters (at least for now)
        simmenu = tkinter.Menu(self.simulate_widget)
        simmenu.add_command(
            label='Run',
            command=lambda pname=pname: self.fnc_start(pname),
        )
        simmenu.add_command(
            label='Stop',
            command=lambda pname=pname: self.fnc_stop(pname),
        )
        if self.paramtype == 'electrical':
            # simmenu.add_command(label='Hints',
            # 	command = lambda param=param, simbutton=simbutton: self.add_hints(param, simbutton))
            simmenu.add_command(
                label='Edit',
                command=lambda pname=pname: self.fnc_edit(pname),
            )
            simmenu.add_command(
                label='Copy',
                command=lambda pname=pname: self.fnc_copy(pname),
            )
            if 'editable' in self.param and self.param['editable'] == True:
                simmenu.add_command(
                    label='Delete',
                    command=lambda pname=pname: self.fnc_delete(pname),
                )

        # Attach the menu to the button
        self.simulate_widget.config(menu=simmenu)

        # simbutton = ttk.Button(dframe, text=simtext, style = normbutton)
        # 		command = lambda pname=pname: self.sim_param(pname))

        self.simulate_widget.grid(column=9, row=n, sticky='ewns')

        if self.paramtype == 'electrical':
            ToolTip(
                self.simulate_widget,
                text='Simulate one electrical parameter',
            )
        else:
            ToolTip(
                self.simulate_widget,
                text='Check one physical parameter',
            )

    def update_widgets(self):

        # Parameter name
        self.parameter_widget.configure(text=self.parameter_text())

        # Testbench name
        self.testbench_widget.configure(text=self.tool_text())

        # Get the status of the last simulation
        (status_value, button_style) = self.status_text()

        if self.is_plot:
            # Plot text
            self.plot_widget.configure(text=self.plot_text())
        else:
            # Minimum widgets
            self.min_limit_widget.configure(text=self.min_limit_text())
            (min_value, min_status_style) = self.min_value_text()
            self.min_value_widget.configure(
                text=min_value, style=min_status_style
            )

            # Typical widgets
            self.typ_limit_widget.configure(text=self.typ_limit_text())
            (typ_value, typ_status_style) = self.typ_value_text()
            self.typ_value_widget.configure(
                text=typ_value, style=typ_status_style
            )

            # Maximum widgets
            self.max_limit_widget.configure(text=self.max_limit_text())
            (max_value, max_status_style) = self.max_value_text()
            self.max_value_widget.configure(
                text=max_value, style=max_status_style
            )

        # Status Widget

        # Electrical
        if self.tool_text() == 'ngspice':
            self.status_widget.configure(
                text=status_value, style=button_style, state='enabled'
            )

        # Physical: LVS
        elif self.tool_text() == 'cace_lvs':
            self.status_widget.configure(
                text=status_value, style=button_style, state='enabled'
            )

        # Physical: Area
        elif self.tool_text() == 'cace_area':
            self.status_widget.configure(
                text=status_value, style=button_style, state='enabled'
            )

        # Physical: DRC
        elif self.tool_text() == 'cace_drc':
            self.status_widget.configure(
                text=status_value, style=button_style, state='enabled'
            )

        # Other physical parameters, disabled
        else:
            self.status_widget.configure(
                text=status_value, style=button_style, state='disabled'
            )

        # Not yet checked, disabled
        if status_value == '(not checked)' or status_value == '(N/A)':
            self.status_widget.configure(
                text=status_value, style=button_style, state='disabled'
            )

        # Simulate widget
        self.simulate_widget.configure(text=self.simulate_text())
