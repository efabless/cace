#!/usr/bin/env python3
#
# -----------------------------------------------------------
# Settings window for the characterization tool
#
# -----------------------------------------------------------
# Written by Tim Edwards
# efabless, inc.
# March 17, 2017
# Version 0.1
# --------------------------------------------------------

import re
import tkinter
from tkinter import ttk


class Settings(tkinter.Toplevel):
    """characterization tool settings management."""

    def __init__(
        self, parent=None, fontsize=11, callback=None, *args, **kwargs
    ):
        """See the __init__ for Tkinter.Toplevel."""
        tkinter.Toplevel.__init__(self, parent, *args, **kwargs)

        s = ttk.Style()
        s.configure(
            'normal.TButton',
            font=('Helvetica', fontsize),
            border=3,
            relief='raised',
        )
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.parent = parent
        self.withdraw()
        self.title('Characterization Tool Settings')
        self.sframe = tkinter.Frame(self)
        self.sframe.grid(column=0, row=0, sticky='news')

        self.sframe.stitle = ttk.Label(
            self.sframe, style='title.TLabel', text='Settings'
        )
        self.sframe.stitle.pack(side='top', fill='x', expand='true')
        self.sframe.sbar = ttk.Separator(self.sframe, orient='horizontal')
        self.sframe.sbar.pack(side='top', fill='x', expand='true')

        self.dodebug = tkinter.IntVar(self.sframe)
        self.dodebug.set(0)
        self.sframe.debug = ttk.Checkbutton(
            self.sframe, text='Print debug output', variable=self.dodebug
        )
        self.sframe.debug.pack(side='top', anchor='w')

        self.doforce = tkinter.IntVar(self.sframe)
        self.doforce.set(0)
        self.sframe.force = ttk.Checkbutton(
            self.sframe,
            text='Force netlist regeneration',
            variable=self.doforce,
        )
        # self.sframe.force.pack(side = 'top', anchor = 'w')

        self.doedit = tkinter.IntVar(self.sframe)
        self.doedit.set(0)
        self.sframe.edit = ttk.Checkbutton(
            self.sframe,
            text='Allow edit of all parameters',
            variable=self.doedit,
        )
        self.sframe.edit.pack(side='top', anchor='w')

        self.dosequential = tkinter.IntVar(self.sframe)
        self.dosequential.set(0)
        self.sframe.seq = ttk.Checkbutton(
            self.sframe,
            text='Simulate single-threaded',
            variable=self.dosequential,
        )
        self.sframe.seq.pack(side='top', anchor='w')

        self.dokeep = tkinter.IntVar(self.sframe)
        self.dokeep.set(0)
        self.sframe.keep = ttk.Checkbutton(
            self.sframe, text='Keep simulation files', variable=self.dokeep
        )
        self.sframe.keep.pack(side='top', anchor='w')

        self.noplot = tkinter.IntVar(self.sframe)
        self.noplot.set(0)
        self.sframe.plot = ttk.Checkbutton(
            self.sframe, text='Do not create plot files', variable=self.noplot
        )
        self.sframe.plot.pack(side='top', anchor='w')

        self.doschem = tkinter.IntVar(self.sframe)
        self.doschem.set(0)
        self.sframe.schem = ttk.Checkbutton(
            self.sframe,
            text='Force characterization as schematic only',
            variable=self.doschem,
        )
        self.sframe.schem.pack(side='top', anchor='w')

        self.dolog = tkinter.IntVar(self.sframe)
        self.dolog.set(0)
        self.sframe.log = ttk.Checkbutton(
            self.sframe, text='Log simulation output', variable=self.dolog
        )
        self.sframe.log.pack(side='top', anchor='w')

        # self.sframe.sdisplay.sopts(side = 'top', fill = 'x', expand = 'true')

        self.bbar = ttk.Frame(self)
        self.bbar.grid(column=0, row=1, sticky='news')
        self.bbar.close_button = ttk.Button(
            self.bbar, text='Close', command=self.close, style='normal.TButton'
        )
        self.bbar.close_button.grid(column=0, row=0, padx=5)

        # Callback-on-close
        self.callback = callback

    def grid_configure(self, padx, pady):
        pass

    def redisplay(self):
        pass

    def get_force(self):
        # return the state of the "force netlist regeneration" checkbox
        return False if self.doforce.get() == 0 else True

    def get_edit(self):
        # return the state of the "edit all parameters" checkbox
        return False if self.doedit.get() == 0 else True

    def get_debug(self):
        # return the state of the "print debug output" checkbox
        return False if self.dodebug.get() == 0 else True

    def get_keep(self):
        # return the state of the "keep simulation files" checkbox
        return False if self.dokeep.get() == 0 else True

    def get_sequential(self):
        # return the state of the "simulate single-threaded" checkbox
        return False if self.dosequential.get() == 0 else True

    def get_noplot(self):
        # return the state of the "do not create plot files" checkbox
        return False if self.noplot.get() == 0 else True

    def get_schem(self):
        # return the state of the "characterize as schematic" checkbox
        return False if self.doschem.get() == 0 else True

    def get_log(self):
        # return the state of the "log simulation output" checkbox
        return False if self.dolog.get() == 0 else True

    def close(self):
        # pop down settings window
        self.withdraw()
        # execute the callback function, if one is given
        if self.callback:
            self.callback()

    def open(self):
        # pop up settings window
        self.deiconify()
        self.lift()
