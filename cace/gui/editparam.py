#!/usr/bin/env python3
#
# -----------------------------------------------------------
# Parameter editing for the characterization tool
# -----------------------------------------------------------
# Written by Tim Edwards
# efabless, inc.
# March 28, 2017
# Version 0.1
# --------------------------------------------------------

import os
import re
import tkinter
from tkinter import ttk

from ..common.common import get_condition_names_used


class Condition(object):
    def __init__(self, parent=None):
        self.min = tkinter.StringVar(parent)
        self.typ = tkinter.StringVar(parent)
        self.max = tkinter.StringVar(parent)
        self.step = tkinter.StringVar(parent)
        self.steptype = tkinter.StringVar(parent)
        self.unit = tkinter.StringVar(parent)
        self.condition = tkinter.StringVar(parent)
        self.display = tkinter.StringVar(parent)


class Limit(object):
    def __init__(self, parent=None):
        self.target = tkinter.StringVar(parent)
        self.penalty = tkinter.StringVar(parent)
        self.calc = tkinter.StringVar(parent)
        self.limit = tkinter.StringVar(parent)


class EditParam(tkinter.Toplevel):
    """Characterization tool electrical parameter editor."""

    def __init__(self, parent=None, fontsize=11, *args, **kwargs):
        """See the __init__ for Tkinter.Toplevel."""
        tkinter.Toplevel.__init__(self, parent, *args, **kwargs)

        self.parent = parent
        self.withdraw()
        self.title('Electrical parameter editor')
        self.sframe = tkinter.Frame(self)
        self.sframe.grid(column=0, row=0, sticky='news')

        # Keep current parameter
        self.param = None

        # -------------------------------------------------------------
        # Add the entries that are common to all electrical parameters

        self.name = tkinter.StringVar(self)
        self.display = tkinter.StringVar(self)
        self.description = tkinter.StringVar(self)
        self.template = tkinter.StringVar(self)
        self.unit = tkinter.StringVar(self)
        self.minrec = Limit(self)
        self.typrec = Limit(self)
        self.maxrec = Limit(self)
        self.cond = []

        # --------------------------------------------------------

        self.bbar = ttk.Frame(self)
        self.bbar.grid(column=0, row=2, sticky='news')

        self.bbar.apply_button = ttk.Button(
            self.bbar, text='Apply', command=self.apply, style='normal.TButton'
        )
        self.bbar.apply_button.grid(column=0, row=0, padx=5)

        self.bbar.close_button = ttk.Button(
            self.bbar, text='Close', command=self.close, style='normal.TButton'
        )
        self.bbar.close_button.grid(column=1, row=0, padx=5)

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)

        self.protocol('WM_DELETE_WINDOW', self.close)

    def grid_configure(self, padx, pady):
        return

    def redisplay(self):
        return

    def populate(self, param):
        # Remove all existing contents
        for widget in self.sframe.winfo_children():
            widget.destroy()

        # Add major frames

        frame1 = ttk.Frame(self.sframe)
        frame1.grid(column=0, row=0, sticky='news')
        frame2 = ttk.Frame(self.sframe)
        frame2.grid(column=0, row=1, sticky='news')
        frame3 = ttk.Frame(self.sframe)
        frame3.grid(column=0, row=2, sticky='news')

        # The Conditions area is the one that grows
        self.sframe.rowconfigure(2, weight=1)
        self.sframe.columnconfigure(0, weight=1)

        ttk.Separator(frame3, orient='horizontal').grid(
            row=0, column=0, sticky='news'
        )

        # The conditions list can get very big, so build out a
        # scrolled canvas.

        frame3.canvas = tkinter.Canvas(frame3)
        frame3.canvas.grid(row=1, column=0, sticky='nswe')
        frame3.canvas.dframe = ttk.Frame(frame3.canvas, style='bg.TFrame')
        # Save the canvas widget, as we need to access it from places like
        # the scrollbar callbacks.
        self.canvas = frame3.canvas
        # Place the frame in the canvas
        frame3.canvas.create_window(
            (0, 0), window=frame3.canvas.dframe, anchor='nw'
        )
        # Make sure the main window resizes, not the scrollbars.
        frame3.rowconfigure(1, weight=1)
        frame3.columnconfigure(0, weight=1)
        # X scrollbar for conditions list
        main_xscrollbar = ttk.Scrollbar(frame3, orient='horizontal')
        main_xscrollbar.grid(row=2, column=0, sticky='nswe')
        # Y scrollbar for conditions list
        main_yscrollbar = ttk.Scrollbar(frame3, orient='vertical')
        main_yscrollbar.grid(row=1, column=1, sticky='nswe')
        # Attach console to scrollbars
        frame3.canvas.config(xscrollcommand=main_xscrollbar.set)
        main_xscrollbar.config(command=frame3.canvas.xview)
        frame3.canvas.config(yscrollcommand=main_yscrollbar.set)
        main_yscrollbar.config(command=frame3.canvas.yview)

        # Make sure that scrollwheel pans the window
        frame3.canvas.bind_all('<Button-4>', self.on_mousewheel)
        frame3.canvas.bind_all('<Button-5>', self.on_mousewheel)

        # Set up configure callback
        frame3.canvas.dframe.bind('<Configure>', self.frame_configure)

        # Get the parent's datasheet
        dsheet = self.parent.simulation_manager.get_datasheet()

        # Get list of methods from testbench folder
        # ("dspath" should be the same as "tbpath"---is there any case
        # where it would not be?
        # dspath = os.path.split(self.parent.filename)[0]
        paths = dsheet['paths']
        tbpath = os.path.join(paths['root'], paths['testbench'])
        tbfiles = os.listdir(tbpath)
        methods = []
        for spicefile in tbfiles:
            if os.path.splitext(spicefile)[1] == '.spice':
                methods.append(os.path.splitext(spicefile))

        # Get list of pins from parent datasheet
        pins = dsheet['pins']
        pinlist = []
        for pin in pins:
            pinlist.append(pin['name'])
        pinlist.append('(none)')

        # Add common elements
        frame1.lname = ttk.Label(
            frame1, text='Name:', style='blue.TLabel', anchor='e'
        )
        frame1.ldescription = ttk.Label(
            frame1, text='Description:', style='blue.TLabel', anchor='e'
        )
        frame1.ldisplay = ttk.Label(
            frame1, text='Display:', style='blue.TLabel', anchor='e'
        )
        frame1.lmethod = ttk.Label(
            frame1, text='Testbench:', style='blue.TLabel', anchor='e'
        )
        frame1.lunit = ttk.Label(
            frame1, text='Unit:', style='blue.TLabel', anchor='e'
        )

        # Find method and apply to OptionMenu
        if 'simulate' in param:
            simrec = param['simulate']

        # XXX WIP TO DO: Handle other records
        if 'template' in simrec:
            self.template.set(simrec['template'])
        else:
            self.template.set('(none)')

        frame1.name = ttk.Entry(frame1, textvariable=self.name)
        frame1.display = ttk.Entry(frame1, textvariable=self.display)
        frame1.description = ttk.Entry(frame1, textvariable=self.description)
        frame1.method = ttk.OptionMenu(
            frame1, self.template, self.template.get(), *methods
        )
        frame1.unit = ttk.Entry(frame1, textvariable=self.unit)

        frame1.lname.grid(column=0, row=0, sticky='news', padx=5, pady=5)
        frame1.name.grid(column=1, row=0, sticky='news', padx=5, pady=5)
        frame1.ldescription.grid(
            column=0, row=1, sticky='news', padx=5, pady=5
        )
        frame1.description.grid(column=1, row=1, sticky='news', padx=5, pady=3)
        frame1.ldisplay.grid(column=0, row=2, sticky='news', padx=5, pady=5)
        frame1.display.grid(column=1, row=2, sticky='news', padx=5, pady=3)
        frame1.lmethod.grid(column=0, row=3, sticky='news', padx=5, pady=5)
        frame1.method.grid(column=1, row=3, sticky='news', padx=5, pady=3)
        frame1.lunit.grid(column=0, row=4, sticky='news', padx=5, pady=5)
        frame1.unit.grid(column=1, row=4, sticky='news', padx=5, pady=3)

        frame1.columnconfigure(0, weight=0)
        frame1.columnconfigure(1, weight=1)

        frame1.name.delete(0, 'end')
        if 'name' in param:
            frame1.name.insert(0, param['name'])
        else:
            frame1.name.insert(0, '(none)')

        frame1.display.delete(0, 'end')
        if 'display' in param:
            frame1.display.insert(0, param['display'])
        else:
            frame1.display.insert(0, '(none)')

        frame1.description.delete(0, 'end')
        if 'description' in param:
            frame1.description.insert(0, param['description'])
        else:
            frame1.description.insert(0, '(none)')

        frame1.unit.delete(0, 'end')
        if 'unit' in param:
            frame1.unit.insert(0, param['unit'])
        else:
            frame1.unit.insert(0, '(none)')

        ttk.Separator(frame1, orient='horizontal').grid(
            row=5, column=0, columnspan=2, sticky='nsew'
        )

        if 'spec' in param:
            spec = param['spec']
        else:
            spec = {}

        # Calculation types
        calctypes = [
            'minimum',
            'maximum',
            'average',
            'diffmin',
            'diffmax',
            '(none)',
        ]
        limittypes = ['above', 'below', 'exact', 'legacy', '(none)']

        # Add min/typ/max (To-do:  Add plot)

        frame2min = ttk.Frame(frame2, borderwidth=2, relief='groove')
        frame2min.grid(row=0, column=0, padx=2, pady=2, sticky='news')
        ttk.Label(
            frame2min, text='Minimum:', style='blue.TLabel', anchor='w'
        ).grid(row=0, column=0, padx=5, sticky='news')

        if 'minimum' in spec:
            minrec = spec['minimum']
        else:
            minrec = []
        if isinstance(minrec, str):
            minrec = [minrec]
        ttk.Label(
            frame2min, text='Limit:', anchor='e', style='normal.TLabel'
        ).grid(row=1, column=0, padx=5, sticky='news')
        frame2min.tmin = ttk.Entry(frame2min, textvariable=self.minrec.target)
        frame2min.tmin.grid(row=1, column=1, padx=5, sticky='news')
        frame2min.tmin.delete(0, 'end')
        if minrec:
            frame2min.tmin.insert(0, minrec[0])
        ttk.Label(
            frame2min, text='Penalty:', anchor='e', style='normal.TLabel'
        ).grid(row=2, column=0, padx=5, sticky='news')
        frame2min.pmin = ttk.Entry(frame2min, textvariable=self.minrec.penalty)
        frame2min.pmin.grid(row=2, column=1, padx=5, sticky='news')
        frame2min.pmin.delete(0, 'end')
        if len(minrec) > 1:
            frame2min.pmin.insert(0, minrec[1])
        if len(minrec) > 2:
            calcrec = minrec[2]
            try:
                calctype, limittype = calcrec.split('-')
            except ValueError:
                calctype = calcrec
                if calctype == 'minimum':
                    limittype = 'above'
                elif calctype == 'maximum':
                    limittype = 'below'
                elif calctype == 'average':
                    limittype = 'exact'
                elif calctype == 'diffmin':
                    limittype = 'above'
                elif calctype == 'diffmax':
                    limittype = 'below'
                else:
                    limittype = '(none)'
        else:
            calctype = 'minimum'
            limittype = 'above'

        ttk.Label(
            frame2min, text='Calculation:', anchor='e', style='normal.TLabel'
        ).grid(row=3, column=0, padx=5, sticky='news')
        self.cmin = tkinter.StringVar(self)
        self.cmin.set(calctype)
        frame2min.cmin = ttk.OptionMenu(
            frame2min, self.cmin, calctype, *calctypes
        )
        frame2min.cmin.grid(row=3, column=1, padx=5, sticky='news')
        ttk.Label(
            frame2min, text='Limit:', anchor='e', style='normal.TLabel'
        ).grid(row=4, column=0, padx=5, sticky='news')
        self.lmin = tkinter.StringVar(self)
        self.lmin.set(limittype)
        frame2min.lmin = ttk.OptionMenu(
            frame2min, self.lmin, limittype, *limittypes
        )
        frame2min.lmin.grid(row=4, column=1, padx=5, sticky='news')

        frame2typ = ttk.Frame(frame2, borderwidth=2, relief='groove')
        frame2typ.grid(row=0, column=1, padx=2, pady=2, sticky='news')
        ttk.Label(
            frame2typ, text='Typical:', style='blue.TLabel', anchor='w'
        ).grid(row=0, column=0, padx=5, sticky='news')
        if 'typical' in spec:
            typrec = spec['typical']
        else:
            typrec = []
        if isinstance(typrec, str):
            typrec = [typrec]
        ttk.Label(
            frame2typ, text='Target:', anchor='e', style='normal.TLabel'
        ).grid(row=1, column=0, padx=5, sticky='news')
        frame2typ.ttyp = ttk.Entry(frame2typ, textvariable=self.typrec.target)
        frame2typ.ttyp.grid(row=1, column=1, padx=5, sticky='news')
        frame2typ.ttyp.delete(0, 'end')
        if typrec:
            frame2typ.ttyp.insert(0, typrec[0])
        ttk.Label(
            frame2typ, text='Penalty:', anchor='e', style='normal.TLabel'
        ).grid(row=2, column=0, padx=5, sticky='news')
        frame2typ.ptyp = ttk.Entry(frame2typ, textvariable=self.typrec.penalty)
        frame2typ.ptyp.grid(row=2, column=1, padx=5, sticky='news')
        frame2typ.ptyp.delete(0, 'end')
        if len(typrec) > 1:
            frame2typ.ptyp.insert(0, typrec[1])
        if len(typrec) > 2:
            calcrec = typrec[2]
            try:
                calctype, limittype = calcrec.split('-')
            except ValueError:
                calctype = calcrec
                if calctype == 'minimum':
                    limittype = 'above'
                elif calctype == 'maximum':
                    limittype = 'below'
                elif calctype == 'average':
                    limittype = 'exact'
                elif calctype == 'diffmin':
                    limittype = 'above'
                elif calctype == 'diffmax':
                    limittype = 'below'
                else:
                    limittype = '(none)'
        else:
            calctype = 'average'
            limittype = 'exact'

        ttk.Label(
            frame2typ, text='Calculation:', anchor='e', style='normal.TLabel'
        ).grid(row=3, column=0, padx=5, sticky='news')
        self.ctyp = tkinter.StringVar(self)
        self.ctyp.set(calctype)
        frame2typ.ctyp = ttk.OptionMenu(
            frame2typ, self.ctyp, calctype, *calctypes
        )
        frame2typ.ctyp.grid(row=3, column=1, padx=5, sticky='news')
        ttk.Label(
            frame2typ, text='Limit:', anchor='e', style='normal.TLabel'
        ).grid(row=4, column=0, padx=5, sticky='news')
        self.ltyp = tkinter.StringVar(self)
        self.ltyp.set(limittype)
        frame2typ.ltyp = ttk.OptionMenu(
            frame2typ, self.ltyp, limittype, *limittypes
        )
        frame2typ.ltyp.grid(row=4, column=1, padx=5, sticky='news')

        frame2max = ttk.Frame(frame2, borderwidth=2, relief='groove')
        frame2max.grid(row=0, column=2, padx=2, pady=2, sticky='news')
        ttk.Label(
            frame2max, text='Maximum:', style='blue.TLabel', anchor='w'
        ).grid(row=0, column=0, padx=5, sticky='news')
        if 'maximum' in spec:
            maxrec = spec['maximum']
        else:
            maxrec = []
        if isinstance(maxrec, str):
            maxrec = [maxrec]
        ttk.Label(
            frame2max, text='Limit:', anchor='e', style='normal.TLabel'
        ).grid(row=1, column=0, padx=5, sticky='news')
        frame2max.tmax = ttk.Entry(frame2max, textvariable=self.maxrec.target)
        frame2max.tmax.grid(row=1, column=1, padx=5, sticky='news')
        frame2max.tmax.delete(0, 'end')
        if maxrec != []:
            frame2max.tmax.insert(0, maxrec[0])
        ttk.Label(
            frame2max, text='Penalty:', anchor='e', style='normal.TLabel'
        ).grid(row=2, column=0, padx=5, sticky='news')
        frame2max.pmax = ttk.Entry(frame2max, textvariable=self.maxrec.penalty)
        frame2max.pmax.grid(row=2, column=1, padx=5, sticky='news')
        frame2max.pmax.delete(0, 'end')
        if len(maxrec) > 1:
            frame2max.pmax.insert(0, maxrec[1])
        if len(maxrec) > 2:
            calcrec = maxrec[2]
            try:
                calctype, limittype = calcrec.split('-')
            except ValueError:
                calctype = calcrec
                if calctype == 'minimum':
                    limittype = 'above'
                elif calctype == 'maximum':
                    limittype = 'below'
                elif calctype == 'average':
                    limittype = 'exact'
                elif calctype == 'diffmin':
                    limittype = 'above'
                elif calctype == 'diffmax':
                    limittype = 'below'
                else:
                    limittype = '(none)'
        else:
            calctype = 'maximum'
            limittype = 'below'

        ttk.Label(
            frame2max, text='Calculation:', anchor='e', style='normal.TLabel'
        ).grid(row=3, column=0, padx=5, sticky='news')
        self.cmax = tkinter.StringVar(self)
        self.cmax.set(calctype)
        frame2max.cmax = ttk.OptionMenu(
            frame2max, self.cmax, calctype, *calctypes
        )
        frame2max.cmax.grid(row=3, column=1, padx=5, sticky='news')
        ttk.Label(
            frame2max, text='Limit:', anchor='e', style='normal.TLabel'
        ).grid(row=4, column=0, padx=5, sticky='news')
        self.lmax = tkinter.StringVar(self)
        self.lmax.set(limittype)
        frame2max.lmax = ttk.OptionMenu(
            frame2max, self.lmax, limittype, *limittypes
        )
        frame2max.lmax.grid(row=4, column=1, padx=5, sticky='news')

        dframe = frame3.canvas.dframe

        ttk.Label(
            dframe, text='Conditions:', style='blue.TLabel', anchor='w'
        ).grid(row=0, column=0, padx=5, sticky='news', columnspan=5)

        # Reserved variables
        reserved = [
            'filename',
            'simpath',
            'DUT_name',
            'N',
            'DUT_path',
            'PDK_ROOT',
            'PDK',
            'include_DUT',
            'DUT_call',
            'steptime',
            'random',
            '+',
            '-',
            '*',
            '/',
            'MIN',
            'NEG',
            'INT',
            'FUNCTIONAL',
        ]

        # Add conditions from the template's testbench
        # TO DO: Refresh this list if the testbench changes.
        conddict = get_condition_names_used(tbpath, simrec['template'])
        condtypes = []
        for type in conddict.keys():
            if type not in reserved:
                condtypes.append(type)

        steptypes = ['linear', 'logarithmic', '(none)']

        n = 0
        r = 1
        self.crec = []
        self.cond = []
        for cond in param['conditions']:
            # If over 5 columns of conditions, create a new row.
            if n >= 5:
                r += 1
                n = 0
            # New column
            frame3c = ttk.Frame(dframe, borderwidth=2, relief='groove')
            frame3c.grid(row=r, column=n, padx=2, pady=2, sticky='news')

            crec = Condition(self)
            # Condition description
            ttk.Label(
                frame3c, text='Display:', style='normal.TLabel', anchor='e'
            ).grid(row=0, column=0, padx=5, sticky='news')
            c1 = ttk.Entry(frame3c, textvariable=crec.display)
            c1.grid(row=0, column=1, padx=5, sticky='news')
            c1.delete(0, 'end')
            if 'display' in cond:
                c1.insert(0, cond['display'])
            else:
                c1.insert(0, '(none)')
            # Condition type (pulldown menu)
            if 'name' in cond:
                crec.condition.set(cond['name'])
            else:
                crec.condition.set('(none)')
            ttk.Label(
                frame3c, text='Name:', style='normal.TLabel', anchor='e'
            ).grid(row=1, column=0, padx=5, sticky='news')
            c2 = ttk.OptionMenu(
                frame3c, crec.condition, crec.condition.get(), *condtypes
            )
            c2.grid(row=1, column=1, padx=5, sticky='news')
            # Condition unit
            ttk.Label(
                frame3c, text='Unit:', style='normal.TLabel', anchor='e'
            ).grid(row=3, column=0, padx=5, sticky='news')
            c4 = ttk.Entry(frame3c, textvariable=crec.unit)
            c4.grid(row=3, column=1, padx=5, sticky='news')
            c4.delete(0, 'end')
            if 'unit' in cond:
                c4.insert(0, cond['unit'])
            else:
                c4.insert(0, '(none)')
            # Condition min
            ttk.Label(
                frame3c, text='Minimum:', style='normal.TLabel', anchor='e'
            ).grid(row=4, column=0, padx=5, sticky='news')
            c5 = ttk.Entry(frame3c, textvariable=crec.min)
            c5.grid(row=4, column=1, padx=5, sticky='news')
            c5.delete(0, 'end')
            if 'minimum' in cond:
                c5.insert(0, cond['minimum'])
            else:
                c5.insert(0, '(none)')
            # Condition typ
            ttk.Label(
                frame3c, text='Typical:', style='normal.TLabel', anchor='e'
            ).grid(row=5, column=0, padx=5, sticky='news')
            c6 = ttk.Entry(frame3c, textvariable=crec.typ)
            c6.grid(row=5, column=1, padx=5, sticky='news')
            c6.delete(0, 'end')
            if 'typical' in cond:
                c6.insert(0, cond['typical'])
            else:
                c6.insert(0, '(none)')
            # Condition max
            ttk.Label(
                frame3c, text='Maximum:', style='normal.TLabel', anchor='e'
            ).grid(row=6, column=0, padx=5, sticky='news')
            c7 = ttk.Entry(frame3c, textvariable=crec.max)
            c7.grid(row=6, column=1, padx=5, sticky='news')
            c7.delete(0, 'end')
            if 'maximum' in cond:
                c7.insert(0, cond['maximum'])
            else:
                c7.insert(0, '(none)')
            # Condition steptype
            ttk.Label(
                frame3c, text='Step type:', style='normal.TLabel', anchor='e'
            ).grid(row=7, column=0, padx=5, sticky='news')
            c8 = ttk.OptionMenu(
                frame3c, crec.steptype, crec.steptype.get(), *steptypes
            )
            c8.grid(row=7, column=1, padx=5, sticky='news')
            if 'linstep' in cond:
                crec.steptype.set('linear')
            elif 'logstep' in cond:
                crec.steptype.set('logarithmic')
            else:
                crec.steptype.set('(none)')
            # Condition step
            ttk.Label(
                frame3c, text='Step:', style='normal.TLabel', anchor='e'
            ).grid(row=8, column=0, padx=5, sticky='news')
            c9 = ttk.Entry(frame3c, textvariable=crec.step)
            c9.grid(row=8, column=1, padx=5, sticky='news')
            c9.delete(0, 'end')
            if 'linstep' in cond:
                c9.insert(0, cond['linstep'])
            elif 'logstep' in cond:
                c9.insert(0, cond['logstep'])
            else:
                c9.insert(0, '(none)')

            n += 1
            self.cond.append(crec)
            # Condition remove
            c10 = ttk.Button(
                frame3c,
                text='Remove',
                style='normal.TButton',
                command=lambda cond=cond: self.remove_condition(cond),
            )
            c10.grid(row=9, column=1, padx=5, sticky='news')

        # Add 'add condition' button
        dframe.bcond = ttk.Button(
            dframe,
            text='Add Condition',
            style='blue.TButton',
            command=self.add_condition,
        )
        if n >= 5:
            dframe.bcond.grid(
                row=r + 1, column=0, padx=5, pady=3, sticky='nsw'
            )
        else:
            dframe.bcond.grid(row=r, column=n, padx=5, pady=3, sticky='new')

        # Set the current parameter
        self.param = param

    def on_mousewheel(self, event):
        if event.num == 5:
            self.canvas.yview_scroll(1, 'units')
        elif event.num == 4:
            self.canvas.yview_scroll(-1, 'units')

    def frame_configure(self, event):
        self.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def add_condition(self):
        # Add a new condition
        newcond = {}
        newcond['name'] = '(none)'
        self.param['conditions'].append(newcond)
        self.populate(self.param)

    def remove_condition(self, cond):
        # Remove and existing condition
        condlist = self.param['conditions']
        eidx = condlist.index(cond)
        condlist.pop(eidx)
        self.populate(self.param)

    def apply(self):
        # Apply the values back to the parameter record

        simrec = self.param['simulate']

        simrec['template'] = self.template.get()
        unit = self.unit.get()
        if not (unit == '(none)' or unit == ''):
            self.param['unit'] = unit
        name = self.name.get()
        if not (name == '(none)' or name == ''):
            self.param['name'] = name
        display = self.display.get()
        if not (display == '(none)' or display == ''):
            self.param['display'] = display
        description = self.description.get()
        if not (description == '(none)' or description == ''):
            self.param['description'] = description

        spec = self.param['spec']

        targmin = self.minrec.target.get()
        if not (targmin == '(none)' or targmin == ''):
            pmin = targmin
            pen = self.minrec.penalty.get()
            if not (pen == '(none)' or pen == ''):
                pmin = []
                pmin.append(targmin)
                pmin.append(pen)
            cmin = self.minrec.calc.get()
            if not (cmin == '(none)' or cmin == ''):
                lmin = self.minrec.limit.get()
                if not (lmin == '(none)' or lmin == ''):
                    pmin.append(cmin + '-' + lmin)
                else:
                    pmin.append(cmin)
            spec['minimum'] = pmin

        targtyp = self.typrec.target.get()
        if not (targtyp == '(none)' or targtyp == ''):
            ptyp = targtyp
            pen = self.typrec.penalty.get()
            if not (pen == '(none)' or pen == ''):
                ptyp = []
                ptyp.append(targtyp)
                ptyp.append(pen)
            ctyp = self.typrec.calc.get()
            if not (ctyp == '(none)' or ctyp == ''):
                ltyp = self.typrec.limit.get()
                if not (ltyp == '(none)' or ltyp == ''):
                    ptyp.append(ctyp + '-' + ltyp)
                else:
                    ptyp.append(ctyp)
            spec['typical'] = ptyp

        targmax = self.maxrec.target.get()
        if not (targmax == '(none)' or targmax == ''):
            pmax = targmax
            pen = self.maxrec.penalty.get()
            if not (pen == '(none)' or pen == ''):
                pmax = []
                pmax.append(targmax)
                pmax.append(pen)
            cmax = self.maxrec.calc.get()
            if not (cmax == '(none)' or cmax == ''):
                lmax = self.maxrec.limit.get()
                if not (lmax == '(none)' or lmax == ''):
                    pmax.append(cmax + '-' + lmax)
                else:
                    pmax.append(cmax)
            spec['maximum'] = pmax

        condlist = []
        for crec in self.cond:
            cond = {}
            cname = crec.condition.get()
            if cname == '(none)' or cname == '':
                continue
            cond['name'] = cname
            display = crec.display.get()
            if not (display == '(none)' or display == ''):
                cond['display'] = display
            min = crec.min.get()
            if not (min == '(none)' or min == ''):
                cond['minimum'] = min
            typ = crec.typ.get()
            if not (typ == '(none)' or typ == ''):
                cond['typical'] = typ
            max = crec.max.get()
            if not (max == '(none)' or max == ''):
                cond['maximum'] = max
            unit = crec.unit.get()
            if not (unit == '(none)' or unit == ''):
                cond['unit'] = unit
            steptype = crec.steptype.get()
            step = crec.step.get()
            if not (step == '(none)' or step == ''):
                if steptype == 'linear':
                    cond['linstep'] = step
                elif steptype == 'logarithmic':
                    cond['logstep'] = step
            condlist.append(cond)
        self.param['conditions'] = condlist

        self.parent.create_datasheet_view()
        return

    def close(self):
        # pop down settings window
        self.withdraw()

    def open(self):
        # pop up settings window
        self.deiconify()
        self.lift()
