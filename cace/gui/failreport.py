#!/usr/bin/env python3
#
# --------------------------------------------------------------------
# Characterization Report Window for the project manager
#
# --------------------------------------------------------------------
# Written by Tim Edwards
# efabless, inc.
# September 12, 2016
# Version 0.1
# ----------------------------------------------------------

import os
import base64
import subprocess

import tkinter
from tkinter import ttk

from .tooltip import *
from ..common.cace_makeplot import *
from ..common.spiceunits import spice_unit_unconvert


class FailReport(tkinter.Toplevel):
    """failure report window."""

    def __init__(self, parent=None, fontsize=11, *args, **kwargs):
        """See the __init__ for Tkinter.Toplevel."""
        tkinter.Toplevel.__init__(self, parent, *args, **kwargs)

        self.parent = parent
        self.withdraw()
        self.title('Local Characterization Report')
        self.root = parent.root
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Scrolled frame:  Need frame, then canvas and scrollbars;  finally, the
        # actual grid of results gets placed in the canvas.
        self.failframe = ttk.Frame(self)
        self.failframe.grid(column=0, row=0, sticky='nsew')
        self.mainarea = tkinter.Canvas(self.failframe)
        self.mainarea.grid(row=0, column=0, sticky='nsew')

        self.mainarea.faildisplay = ttk.Frame(self.mainarea)
        self.mainarea.create_window(
            (0, 0),
            window=self.mainarea.faildisplay,
            anchor='nw',
            tags='self.frame',
        )

        # Create a frame for displaying plots, but don't put it in the grid.
        # Make it resizeable.
        self.plotframe = ttk.Frame(self)
        self.plotframe.rowconfigure(0, weight=1)
        self.plotframe.columnconfigure(0, weight=1)

        # Main window resizes, not the scrollbars
        self.failframe.rowconfigure(0, weight=1)
        self.failframe.columnconfigure(0, weight=1)
        # Add scrollbars
        xscrollbar = ttk.Scrollbar(self.failframe, orient='horizontal')
        xscrollbar.grid(row=1, column=0, sticky='nsew')
        yscrollbar = ttk.Scrollbar(self.failframe, orient='vertical')
        yscrollbar.grid(row=0, column=1, sticky='nsew')
        # Attach viewing area to scrollbars
        self.mainarea.config(xscrollcommand=xscrollbar.set)
        xscrollbar.config(command=self.mainarea.xview)
        self.mainarea.config(yscrollcommand=yscrollbar.set)
        yscrollbar.config(command=self.mainarea.yview)
        # Set up configure callback
        self.mainarea.faildisplay.bind('<Configure>', self.frame_configure)

        self.bbar = ttk.Frame(self)
        self.bbar.grid(column=0, row=1, sticky='news')
        self.bbar.close_button = ttk.Button(
            self.bbar, text='Close', command=self.close, style='normal.TButton'
        )
        self.bbar.close_button.grid(column=0, row=0, padx=5)
        # Table button returns to table view but is only displayed for plots.
        self.bbar.table_button = ttk.Button(
            self.bbar, text='Table', style='normal.TButton'
        )

        self.protocol('WM_DELETE_WINDOW', self.close)
        ToolTip(
            self.bbar.close_button,
            text='Close detail view of conditions and results',
        )

        self.sortdir = False
        self.data = []

    def grid_configure(self, padx, pady):
        pass

    def frame_configure(self, event):
        self.update_idletasks()
        self.mainarea.configure(scrollregion=self.mainarea.bbox('all'))

    def check_failure(self, record, calc, value):
        #
        # record will be a list of <value> ['fail'|''] [<calc-type>]
        #
        # Return on any condition that is not specified as a failure

        if len(record) < 2 or record[1] != 'fail':
            return None
        else:
            target = record[0]
            if target == 'any':
                return None

        if calc == 'minimum':
            targval = float(target)
            if value < targval:
                return True
        elif calc == 'maximum':
            targval = float(target)
            if value > targval:
                return True
        else:
            return None

    # Given an electrical parameter 'param' and a condition name 'condname', find
    # the units of that condition.  If the condition isn't found in the local
    # parameters, then it is searched for in dsheet['global_conditions'].

    def findunit(self, condname, param, dsheet):
        unit = ''
        try:
            loccond = next(
                item
                for item in param['conditions']
                if item['name'] == condname
            )
        except StopIteration:
            globcond = dsheet['default_conditions']
            try:
                globitem = next(
                    item for item in globcond if item['name'] == condname
                )
            except (TypeError, StopIteration):
                unit = ''  	# No units
            else:
                if 'unit' in globitem:
                    unit = globitem['unit']
                else:
                    unit = ''  	# No units
        else:
            if 'unit' in loccond:
                unit = loccond['unit']
            else:
                unit = ''  	# No units
        return unit

    def size_plotreport(self):
        self.update_idletasks()
        width = self.plotframe.winfo_width()
        height = self.plotframe.winfo_height()
        if width < 3 * height:
            self.plotframe.configure(width=height * 3)

    def size_failreport(self):
        # Attempt to set the datasheet viewer width to the interior width
        # but do not set it larger than the available desktop.

        self.update_idletasks()
        width = self.mainarea.faildisplay.winfo_width()
        screen_width = self.root.winfo_screenwidth()
        if width > screen_width - 20:
            self.mainarea.configure(width=screen_width - 20)
        else:
            self.mainarea.configure(width=width)

        # Likewise for the height, up to the desktop height.  Note that this
        # needs to account for both the button bar at the bottom of the GUI
        # window plus the bar at the bottom of the desktop.
        height = self.mainarea.faildisplay.winfo_height()
        screen_height = self.root.winfo_screenheight()
        if height > screen_height - 120:
            self.mainarea.configure(height=screen_height - 120)
        else:
            self.mainarea.configure(height=height)

    def table_to_histogram(self, dsheet, filename):
        # Switch from a table view to a histogram plot view, using the
        # result as the X axis variable and count for the Y axis.

        # Destroy existing contents.
        for widget in self.plotframe.winfo_children():
            widget.destroy()

        param = self.data
        plotrec = {}
        plotrec['xaxis'] = param['name']
        plotrec['xlabel'] = param['name']
        plotrec['ylabel'] = 'COUNT'
        plotrec['type'] = 'histogram'
        if 'unit' in param:
            plotrec['xlabel'] += ' (' + param['unit'] + ')'

        # Temporarily set a 'plot' record in param
        param['plot'] = plotrec

        # faild = self.mainarea.faildisplay	# definition for convenience
        self.failframe.grid_forget()
        self.plotframe.grid(row=0, column=0, sticky='nsew')
        canvas = cace_makeplot(dsheet, param, parent=self.plotframe)
        param.pop('plot')

        if 'display' in param:
            ttk.Label(
                self.plotframe, text=param['display'], style='title.TLabel'
            ).grid(row=1, column=0)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky='nsew')
        # Finally, open the window if it was not already open.
        self.open()

    def table_to_plot(self, condition, pname):
        # Switch from a table view to a plot view, using the condname as
        # the X axis variable.

        # Destroy existing contents.
        for widget in self.plotframe.winfo_children():
            widget.destroy()

        dsheet = self.parent.parameter_manager.get_datasheet()

        # Find parameter
        if pname:
            param = self.parent.parameter_manager.find_parameter(pname)
        # Reuse the last parameter
        else:
            param = self.data

        filename = self.parent.parameter_manager.get_runtime_options(
            'filename'
        )

        plotrec = {}
        plotrec['xaxis'] = condition
        plotrec['xlabel'] = condition
        # Note: cace_makeplot adds text for units, if available
        plotrec['ylabel'] = param['name']
        plotrec['type'] = 'xyplot'

        # faild = self.mainarea.faildisplay	# definition for convenience
        self.failframe.grid_forget()
        self.plotframe.grid(row=0, column=0, sticky='nsew')

        # Temporarily set a 'plot' record in param
        param['plot'] = plotrec

        canvas = cace_makeplot(dsheet, param, parent=self.plotframe)
        param.pop('plot')
        if 'display' in param:
            ttk.Label(
                self.plotframe, text=param['display'], style='title.TLabel'
            ).grid(row=1, column=0)

        if canvas:
            canvas.draw()
            canvas.get_tk_widget().grid(row=0, column=0, sticky='nsew')

            # Display the button to return to the table view
            # except for transient and Monte Carlo simulations which are too large to tabulate.
            if not condition == 'time':
                self.bbar.table_button.grid(column=1, row=0, padx=5)
                self.bbar.table_button.configure(
                    command=lambda pname=pname: self.display(pname)
                )

            # Finally, open the window if it was not already open.
            self.open()
        else:
            # Plot failed;  revert to the table view
            self.display(param, dsheet, filename)

    def display(self, pname=None):
        # (Diagnostic)
        # print('failure report:  passed parameter ' + str(param))

        dsheet = self.parent.parameter_manager.get_datasheet()

        # Find parameter
        if pname:
            param = self.parent.parameter_manager.find_parameter(pname)
        # Reuse the last parameter
        else:
            param = self.data

        filename = self.parent.parameter_manager.get_runtime_options(
            'filename'
        )

        # Destroy existing contents.
        for widget in self.mainarea.faildisplay.winfo_children():
            widget.destroy()

        # 'param' is a dictionary pulled in from the annotate datasheet.
        # If the failure display was called, then 'param' should contain
        # record called 'results'.  If the parameter has no results, then
        # there is nothing to do.

        if 'plot' in param:
            self.failframe.grid_forget()
            self.plotframe.grid(row=0, column=0, sticky='nsew')

            # Clear the plotframe and remake
            for widget in self.plotframe.winfo_children():
                widget.destroy()

            canvas = cace_makeplot(dsheet, param, parent=self.plotframe)
            if 'display' in param:
                ttk.Label(
                    self.plotframe, text=param['display'], style='title.TLabel'
                ).grid(row=1, column=0)
            canvas.draw()
            canvas.get_tk_widget().grid(row=0, column=0, sticky='nsew')
            self.data = param
            # Display the button to return to the table view
            self.bbar.table_button.grid(column=1, row=0, padx=5)
            self.bbar.table_button.configure(
                command=lambda param=param, dsheet=dsheet, filename=filename: self.display(
                    param, dsheet, filename
                )
            )

        elif not 'testbenches' in param:
            print('No testbench results to build a report with.')
            return

        else:
            self.data = param
            self.plotframe.grid_forget()
            self.failframe.grid(column=0, row=0, sticky='nsew')
            faild = self.mainarea.faildisplay  	# definition for convenience
            testbenches = param['testbenches']

            # Rearrange testbench results;  this is due to legacy code and
            # might work better to leave the testbench results in the existing
            # format.

            names = ['result']
            units = [param['unit']]
            if not isinstance(testbenches, list):
                testbenches = [testbenches]

            # Assuming that the condition names and units are the same for
            # all testbenches.
            for condition in testbenches[0]['conditions']:
                names.append(condition[0])
                if len(condition) == 3:
                    units.append(condition[1])
                else:
                    units.append('')

            names.append('testbench')
            units.append('')
            results = []

            for testbench in testbenches:
                tresult = []
                result = testbench['results']
                # To do:  handle vector results here, which imply
                # that conditions list needs to be expanded by variables.
                if isinstance(result, list):
                    if len(result) > 1:
                        print(
                            'Warning: result truncated from length '
                            + str(len(result))
                        )
                    result = result[0]

                # Results get double-nested?
                if isinstance(result, list):
                    if len(result) > 1:
                        print(
                            'Warning: result truncated from length '
                            + str(len(result))
                        )
                    result = result[0]
                tresult.append(result)

                for condition in testbench['conditions']:
                    if len(condition) == 3:
                        tresult.append(condition[2])
                    else:
                        tresult.append(condition[1])
                # Add the testbench filename as the last entry
                tresult.append(os.path.split(testbench['filename'])[1])
                results.append(tresult)

            # Check for transient simulation
            if 'time' in names:
                # Transient data are (usually) too numerous to tabulate, so go straight to plot
                self.table_to_plot('time', pname)
                return

            # Check for Monte Carlo simulation
            if 'iterations' in names:
                # Monte Carlo data are too numerous to tabulate, so go straight to plot
                self.table_to_histogram(dsheet, filename)
                return
            else:
                # Check for "collate: iterations" in simulate dictionary.  This is
                # equivalent to having one testbench per iteration, but more compact.
                simdict = param['simulate']
                if 'collate' in simdict:
                    if simdict['collate'] == 'iterations':
                        self.table_to_histogram(dsheet, filename)
                        return

            # Numerically sort by result (to be done:  sort according to up/down
            # criteria, which will be retained per header entry)
            try:
                results.sort(
                    key=lambda row: float(row[0]), reverse=self.sortdir
                )
            except:
                print('Failure to sort results:  results = ' + str(results))

            # To get ranges, transpose the results matrix, then make unique
            ranges = list(map(list, zip(*results)))[0:-1]
            for r, vrange in enumerate(ranges):
                try:
                    vmin = min(float(v) for v in vrange)
                    vmax = max(float(v) for v in vrange)
                    if vmin == vmax:
                        ranges[r] = [str(vmin)]
                    else:
                        ranges[r] = [str(vmin), str(vmax)]
                except ValueError:
                    ranges[r] = list(set(vrange))
                    pass
            # For testbench names, just use the testbench number as the range.
            ranges.append(['1', str(len(results))])

            faild.titlebar = ttk.Frame(faild)
            faild.titlebar.grid(row=0, column=0, sticky='ewns')

            faild.titlebar.label1 = ttk.Label(
                faild.titlebar,
                text='Electrical Parameter: ',
                style='italic.TLabel',
            )
            faild.titlebar.label1.pack(side='left', padx=6, ipadx=3)
            if 'display' in param:
                faild.titlebar.label2 = ttk.Label(
                    faild.titlebar,
                    text=param['display'],
                    style='normal.TLabel',
                )
                faild.titlebar.label2.pack(side='left', padx=6, ipadx=3)
                faild.titlebar.label3 = ttk.Label(
                    faild.titlebar, text='  Testbench: ', style='italic.TLabel'
                )
                faild.titlebar.label3.pack(side='left', padx=6, ipadx=3)
            simulate = param['simulate']
            faild.titlebar.label4 = ttk.Label(
                faild.titlebar,
                text=simulate['template'],
                style='normal.TLabel',
            )
            faild.titlebar.label4.pack(side='left', padx=6, ipadx=3)

            if 'spec' in param:
                spec = param['spec']
            else:
                spec = {}

            if 'minimum' in spec:
                faild.titlebar.label7 = ttk.Label(
                    faild.titlebar, text='  Min Limit: ', style='italic.TLabel'
                )
                faild.titlebar.label7.pack(side='left', padx=3, ipadx=3)
                faild.titlebar.label8 = ttk.Label(
                    faild.titlebar, text=spec['minimum'], style='normal.TLabel'
                )
                faild.titlebar.label8.pack(side='left', padx=6, ipadx=3)
                if 'unit' in param:
                    faild.titlebar.label9 = ttk.Label(
                        faild.titlebar,
                        text=param['unit'],
                        style='italic.TLabel',
                    )
                    faild.titlebar.label9.pack(side='left', padx=3, ipadx=3)
            if 'maximum' in spec:
                faild.titlebar.label10 = ttk.Label(
                    faild.titlebar, text='  Max Limit: ', style='italic.TLabel'
                )
                faild.titlebar.label10.pack(side='left', padx=6, ipadx=3)
                faild.titlebar.label11 = ttk.Label(
                    faild.titlebar, text=spec['maximum'], style='normal.TLabel'
                )
                faild.titlebar.label11.pack(side='left', padx=6, ipadx=3)
                if 'unit' in param:
                    faild.titlebar.label12 = ttk.Label(
                        faild.titlebar,
                        text=param['unit'],
                        style='italic.TLabel',
                    )
                    faild.titlebar.label12.pack(side='left', padx=3, ipadx=3)

            # Simplify view by removing constant values from the table and just listing them
            # on the second line.

            faild.constants = ttk.Frame(faild)
            faild.constants.grid(row=1, column=0, sticky='ewns')
            faild.constants.title = ttk.Label(
                faild.constants,
                text='Constant Conditions: ',
                style='italic.TLabel',
            )
            faild.constants.title.grid(row=0, column=0, padx=6, ipadx=3)
            j = 0
            for condname, unit, drange in zip(names, units, ranges):
                if len(drange) == 1:
                    labtext = condname
                    # unit = self.findunit(condname, param, dsheet)
                    labtext += ' = ' + drange[0] + ' ' + unit + ' '
                    row = int(j / 3)
                    col = 1 + (j % 3)
                    ttk.Label(
                        faild.constants, text=labtext, style='blue.TLabel'
                    ).grid(row=row, column=col, padx=6, sticky='nsew')
                    j += 1

            body = ttk.Frame(faild, style='bg.TFrame')
            body.grid(row=2, column=0, sticky='ewns')

            # Print out names
            j = 0
            for condname, unit, drange in zip(names, units, ranges):
                # Now find the range for each entry from the global and local conditions.
                # Use local conditions if specified, otherwise default to global condition.
                # Each result is a list of three numbers for min, typ, and max.  List
                # entries may be left unfilled.

                if len(drange) == 1:
                    continue

                labtext = condname
                plottext = condname
                if j == 0:
                    # Add unicode arrow up/down depending on sort direction
                    labtext += ' \u21e9' if self.sortdir else ' \u21e7'
                    header = ttk.Button(
                        body,
                        text=labtext,
                        style='title.TButton',
                        command=lambda pname=pname: self.changesort(pname),
                    )
                    ToolTip(header, text='Reverse order of results')
                elif labtext == 'testbench':
                    header = ttk.Label(
                        body,
                        text=labtext,
                        style='title.TLabel',
                    )
                else:
                    header = ttk.Button(
                        body,
                        text=labtext,
                        style='title.TLabel',
                        command=lambda plottext=plottext, pname=pname: self.table_to_plot(
                            plottext, pname
                        ),
                    )
                    ToolTip(
                        header,
                        text='Plot results with this condition on the X axis',
                    )
                header.grid(row=0, column=j, sticky='ewns')

                # Second row is the measurement unit
                # if j == 0:
                #     # Measurement unit of result in first column
                #     if 'unit' in param:
                #         unit = param['unit']
                #     else:
                #         unit = ''    # No units
                # else:
                #     # Measurement unit of condition in other columns
                #     # Find condition in local conditions else global conditions
                #     unit = self.findunit(condname, param, dsheet)

                unitlabel = ttk.Label(body, text=unit, style='brown.TLabel')
                unitlabel.grid(row=1, column=j, sticky='ewns')

                # (Pick up limits when all entries have been processed---see below)
                j += 1

            # Now list entries for each failure record.  These should all be in the
            # same order.
            m = 2
            for result in results:
                m += 1
                j = 0
                condition = result[0]
                lstyle = 'normal.TLabel'
                value = float(condition)

                # scaled_value is 'value' scaled to the units used by param.
                if 'unit' in param:
                    scaled_value = spice_unit_unconvert([param['unit'], value])
                else:
                    scaled_value = value

                if 'minimum' in spec:
                    minrec = spec['minimum']
                    calc = minrec[2] if len(minrec) > 2 else 'minimum'
                    if self.check_failure(minrec, calc, scaled_value):
                        lstyle = 'red.TLabel'
                if 'maximum' in spec:
                    maxrec = spec['maximum']
                    calc = maxrec[2] if len(maxrec) > 2 else 'maximum'
                    if self.check_failure(maxrec, calc, scaled_value):
                        lstyle = 'red.TLabel'

                for condition, drange in zip(result, ranges):
                    if len(drange) > 1:
                        if j == 0:
                            pname = ttk.Label(
                                body, text=str(scaled_value), style=lstyle
                            )
                        else:
                            pname = ttk.Label(
                                body, text=condition, style=lstyle
                            )
                        pname.grid(row=m, column=j, sticky='ewns')
                        j += 1

            # Row 2 contains the ranges of each column
            j = 1
            k = 1
            for vrange in ranges[1:]:
                if len(vrange) > 1:

                    condlimits = '( '

                    # This is a bit of a hack;  results are assumed floating-point
                    # unless they can't be resolved as a number.  So numerical values
                    # that should be treated as integers or strings must be handled
                    # here according to the condition type.
                    if names[k].split(':')[0] == 'DIGITAL':
                        for l in vrange:
                            condlimits += str(int(float(l))) + ' '
                    else:
                        for l in vrange:
                            condlimits += l + ' '
                    condlimits += ')'
                    header = ttk.Label(
                        body, text=condlimits, style='blue.TLabel'
                    )
                    header.grid(row=2, column=j, sticky='ewns')
                    j += 1

                k += 1

            # Add padding around widgets in the body of the failure report, so that
            # the frame background comes through, making a grid.
            for child in body.winfo_children():
                child.grid_configure(ipadx=5, ipady=1, padx=2, pady=2)

            # Resize the window to fit in the display, if necessary.
            self.size_failreport()

        # Don't put the button at the bottom to return to table view.
        self.bbar.table_button.grid_forget()
        # Finally, open the window if it was not already open.
        self.open()

    def changesort(self, pname):
        self.sortdir = False if self.sortdir == True else True
        self.display(pname)

    def close(self):
        # pop down failure report window
        self.withdraw()

    def open(self):
        # pop up failure report window
        self.deiconify()
        self.lift()
