#!/usr/bin/env python3
#
# --------------------------------------------------------
# cace_gui.py
# Project Manager GUI.
#
# This is a Python tkinter script that handles local
# project management.  Much of this involves the
# running of ng-spice for characterization, allowing
# the user to determine where a circuit is failing
# characterization.
#
# --------------------------------------------------------
# Written by Tim Edwards
# Efabless Corporation
# Created September 9, 2016
# 	Version 1.0
# 	System running on the Efabless Open Galaxy
# 	servers.
#
# (Some intermediate versions were not recorded)
#
# Updated March 14, 2023
# 	Version 3.0
# 	Ported from the Efabless Open Galaxy servers
# 	to open_pdks.
#
# Updated November 22, 2023
# 	Version 4.0
# 	Ported from open_pdks to a standalone repository
# 	renamed from cace.py to cace_gui.py
# --------------------------------------------------------

import io
import re
import os
import sys
import copy
import json
import time
import signal
import select
import datetime
import contextlib
import subprocess
import multiprocessing

import tkinter
from tkinter import ttk
from tkinter import filedialog

from .gui.tksimpledialog import *
from .gui.tooltip import *
from .gui.consoletext import ConsoleText
from .gui.helpwindow import HelpWindow
from .gui.failreport import FailReport
from .gui.textreport import TextReport
from .gui.editparam import EditParam
from .gui.settings import Settings
from .gui.simhints import SimHints

from .common.cace_read import *
from .common.cace_compat import *
from .common.cace_write import *
from .cace_cli import *

# User preferences file (if it exists)
prefsfile = '~/design/.profile/prefs.json'

# Application path (path where this script is located)
apps_path = os.path.realpath(os.path.dirname(__file__))

# ------------------------------------------------------
# Simple dialog for confirming quit
# ------------------------------------------------------


class ConfirmDialog(Dialog):
    def body(self, master, warning, seed):
        ttk.Label(master, text=warning, wraplength=500).grid(
            row=0, columnspan=2, sticky='wns'
        )
        return self

    def apply(self):
        return 'okay'


# ------------------------------------------------------
# Simple dialog with no "OK" button (can only cancel)
# ------------------------------------------------------


class PuntDialog(Dialog):
    def body(self, master, warning, seed):
        if warning:
            ttk.Label(master, text=warning, wraplength=500).grid(
                row=0, columnspan=2, sticky='wns'
            )
        return self

    def buttonbox(self):
        # Add button box with "Cancel" only.
        box = ttk.Frame(self.obox)
        w = ttk.Button(box, text='Cancel', width=10, command=self.cancel)
        w.pack(side='left', padx=5, pady=5)
        self.bind('<Escape>', self.cancel)
        box.pack(fill='x', expand='true')

    def apply(self):
        return 'okay'


# ---------------------------------------------------------
# Routine for a child process to capture signal SIGUSR1
# and exit gracefully.
# ---------------------------------------------------------


def child_process_exit(signum, frame):
    print('CACE GUI:  Received forced stop.')
    try:
        multiprocessing.current_process().terminate()
    except AttributeError:
        print('Terminate failed; Child PID is ' + str(os.getpid()))
        print('Waiting on process to finish.')


# ------------------------------------------------------
# Main class for this application
# ------------------------------------------------------


class CACECharacterize(ttk.Frame):
    """local characterization GUI."""

    def __init__(self, parent, *args, **kwargs):
        ttk.Frame.__init__(self, parent, *args, **kwargs)
        self.root = parent
        self.init_gui()
        parent.protocol('WM_DELETE_WINDOW', self.on_quit)

    def on_quit(self):
        """Exits program."""
        if not self.check_saved():
            warning = 'Warning:  Simulation results have not been saved.'
            confirm = ConfirmDialog(self, warning).result
            if not confirm == 'okay':
                print('Quit canceled.')
                return
        if self.logfile:
            self.logfile.close()
        quit()

    def on_mousewheel(self, event):
        if event.num == 5:
            self.datasheet_viewer.yview_scroll(1, 'units')
        elif event.num == 4:
            self.datasheet_viewer.yview_scroll(-1, 'units')

    def init_gui(self):
        """Builds GUI."""
        global prefsfile

        message = []
        fontsize = 11

        # Read user preferences file, get default font size from it.
        prefspath = os.path.expanduser(prefsfile)
        if os.path.exists(prefspath):
            with open(prefspath, 'r') as f:
                self.prefs = json.load(f)
            if 'fontsize' in self.prefs:
                fontsize = self.prefs['fontsize']
        else:
            self.prefs = {}

        s = ttk.Style()

        available_themes = s.theme_names()
        s.theme_use(available_themes[0])

        s.configure('bg.TFrame', background='gray40')
        s.configure('italic.TLabel', font=('Helvetica', fontsize, 'italic'))
        s.configure(
            'title.TLabel',
            font=('Helvetica', fontsize, 'bold italic'),
            foreground='brown',
            anchor='center',
        )
        s.configure('normal.TLabel', font=('Helvetica', fontsize))
        s.configure(
            'red.TLabel', font=('Helvetica', fontsize), foreground='red'
        )
        s.configure(
            'green.TLabel', font=('Helvetica', fontsize), foreground='green3'
        )
        s.configure(
            'blue.TLabel', font=('Helvetica', fontsize), foreground='blue'
        )
        s.configure(
            'hlight.TLabel', font=('Helvetica', fontsize), background='gray93'
        )
        s.configure(
            'rhlight.TLabel',
            font=('Helvetica', fontsize),
            foreground='red',
            background='gray93',
        )
        s.configure(
            'ghlight.TLabel',
            font=('Helvetica', fontsize),
            foreground='green3',
            background='gray93',
        )
        s.configure(
            'blue.TLabel', font=('Helvetica', fontsize), foreground='blue'
        )
        s.configure(
            'blue.TMenubutton',
            font=('Helvetica', fontsize),
            foreground='blue',
            border=3,
            relief='raised',
        )
        s.configure(
            'normal.TButton',
            font=('Helvetica', fontsize),
            border=3,
            relief='raised',
        )
        s.configure(
            'red.TButton',
            font=('Helvetica', fontsize),
            foreground='red',
            border=3,
            relief='raised',
        )
        s.configure(
            'green.TButton',
            font=('Helvetica', fontsize),
            foreground='green3',
            border=3,
            relief='raised',
        )
        s.configure(
            'hlight.TButton',
            font=('Helvetica', fontsize),
            border=3,
            relief='raised',
            background='gray93',
        )
        s.configure(
            'rhlight.TButton',
            font=('Helvetica', fontsize),
            foreground='red',
            border=3,
            relief='raised',
            background='gray93',
        )
        s.configure(
            'ghlight.TButton',
            font=('Helvetica', fontsize),
            foreground='green3',
            border=3,
            relief='raised',
            background='gray93',
        )
        s.configure(
            'blue.TButton',
            font=('Helvetica', fontsize),
            foreground='blue',
            border=3,
            relief='raised',
        )
        s.configure(
            'redtitle.TButton',
            font=('Helvetica', fontsize, 'bold italic'),
            foreground='red',
            border=3,
            relief='raised',
        )
        s.configure(
            'bluetitle.TButton',
            font=('Helvetica', fontsize, 'bold italic'),
            foreground='blue',
            border=3,
            relief='raised',
        )

        # Create the help window
        self.help = HelpWindow(self, fontsize=fontsize)

        with io.StringIO() as buf, contextlib.redirect_stdout(buf):
            helpfile = os.path.join(apps_path, 'doc', 'characterize_help.txt')
            self.help.add_pages_from_file(helpfile)
            helpfile = os.path.join(apps_path, 'doc', 'format.txt')
            self.help.add_pages_from_file(helpfile)
            message = buf.getvalue()

        # Set the help display to the first page
        self.help.page(0)

        # Create the failure report window
        self.failreport = FailReport(self, fontsize=fontsize)

        # LVS results get a text window of results
        self.textreport = TextReport(self, fontsize=fontsize)

        # Create the settings window
        self.settings = Settings(self, fontsize=fontsize)

        # Create the simulation hints window
        self.simhints = SimHints(self, fontsize=fontsize)

        # Create the edit parameter window
        self.editparam = EditParam(self, fontsize=fontsize)

        # Variables used by option menus and other stuff
        self.origin = tkinter.StringVar(self)
        self.cur_project = tkinter.StringVar(self)
        self.filename = '(no selection)'
        self.datasheet = {}
        self.status = {}
        self.procs_pending = {}
        self.logfile = None

        # Create a multiprocessing data queue for passing information between
        # the parent and child processes (cace_run)
        self.queue = multiprocessing.Queue()

        # Root window title
        self.root.title('Characterization')
        self.root.option_add('*tearOff', 'FALSE')
        self.pack(side='top', fill='both', expand='true')

        pane = tkinter.PanedWindow(
            self, orient='vertical', sashrelief='groove', sashwidth=6
        )
        pane.pack(side='top', fill='both', expand='true')
        self.toppane = ttk.Frame(pane)
        self.botpane = ttk.Frame(pane)

        self.toppane.title_frame = ttk.Frame(self.toppane)
        self.toppane.title_frame.grid(column=0, row=2, sticky='nswe')
        self.toppane.title_frame.datasheet_label = ttk.Label(
            self.toppane.title_frame,
            text='CACE Datasheet:',
            style='normal.TLabel',
        )
        self.toppane.title_frame.datasheet_label.grid(column=0, row=0, ipadx=5)

        # New datasheet select button
        self.toppane.title_frame.datasheet_select = ttk.Button(
            self.toppane.title_frame,
            text=self.filename,
            style='normal.TButton',
            command=self.choose_datasheet,
        )
        self.toppane.title_frame.datasheet_select.grid(
            column=1, row=0, ipadx=5
        )

        ToolTip(
            self.toppane.title_frame.datasheet_select,
            text='Select new datasheet file',
        )

        # Show path to datasheet
        self.toppane.title_frame.path_label = ttk.Label(
            self.toppane.title_frame, text=self.filename, style='normal.TLabel'
        )
        self.toppane.title_frame.path_label.grid(
            column=2, row=0, ipadx=5, padx=10
        )

        # Spacer in middle moves selection button to right
        self.toppane.title_frame.sep_label = ttk.Label(
            self.toppane.title_frame, text=' ', style='normal.TLabel'
        )
        self.toppane.title_frame.sep_label.grid(
            column=3, row=0, ipadx=5, padx=10
        )
        self.toppane.title_frame.columnconfigure(3, weight=1)
        self.toppane.title_frame.rowconfigure(0, weight=0)

        # Selection for origin of netlist
        self.toppane.title_frame.origin_label = ttk.Label(
            self.toppane.title_frame,
            text='Netlist from:',
            style='normal.TLabel',
        )
        self.toppane.title_frame.origin_label.grid(
            column=4, row=0, ipadx=5, padx=10
        )

        self.origin.set('Schematic Capture')
        self.toppane.title_frame.origin_select = ttk.OptionMenu(
            self.toppane.title_frame,
            self.origin,
            'Schematic Capture',
            'Schematic Capture',
            'Layout Extracted',
            'C Extracted',
            'R-C Extracted',
            style='blue.TMenubutton',
            command=self.swap_results,
        )
        self.toppane.title_frame.origin_select.grid(column=5, row=0, ipadx=5)

        # ---------------------------------------------
        ttk.Separator(self.toppane, orient='horizontal').grid(
            column=0, row=3, sticky='news'
        )
        # ---------------------------------------------

        # Datasheet information goes here when datasheet is loaded.
        self.mframe = ttk.Frame(self.toppane)
        self.mframe.grid(column=0, row=4, sticky='news')

        # Row 4 (mframe) is expandable, the other rows are not.
        self.toppane.rowconfigure(0, weight=0)
        self.toppane.rowconfigure(1, weight=0)
        self.toppane.rowconfigure(2, weight=0)
        self.toppane.rowconfigure(3, weight=0)
        self.toppane.rowconfigure(4, weight=1)
        self.toppane.columnconfigure(0, weight=1)

        # ---------------------------------------------
        # ttk.Separator(self, orient='horizontal').grid(column=0, row=5, sticky='ew')
        # ---------------------------------------------

        # Add a text window below the datasheet to capture output.  Redirect
        # print statements to it.

        self.botpane.console = ttk.Frame(self.botpane)
        self.botpane.console.pack(side='top', fill='both', expand='true')

        self.text_box = ConsoleText(
            self.botpane.console, wrap='word', height=4
        )
        self.text_box.pack(side='left', fill='both', expand='true')
        console_scrollbar = ttk.Scrollbar(self.botpane.console)
        console_scrollbar.pack(side='right', fill='y')
        # attach console to scrollbar
        self.text_box.config(yscrollcommand=console_scrollbar.set)
        console_scrollbar.config(command=self.text_box.yview)

        # Add button bar at the bottom of the window
        self.bbar = ttk.Frame(self.botpane)
        self.bbar.pack(side='top', fill='x')
        # Progress bar expands with the window, buttons don't
        self.bbar.columnconfigure(7, weight=1)

        # Define the "quit" button and action
        self.bbar.quit_button = ttk.Button(
            self.bbar,
            text='Quit',
            command=self.on_quit,
            style='normal.TButton',
        )
        self.bbar.quit_button.grid(column=0, row=0, padx=5)

        # Define the save button
        self.bbar.save_button = ttk.Button(
            self.bbar,
            text='Save',
            command=self.save_results,
            style='normal.TButton',
        )
        self.bbar.save_button.grid(column=1, row=0, padx=5)

        # Define the save-as button
        self.bbar.saveas_button = ttk.Button(
            self.bbar,
            text='Save As',
            command=self.save_manual,
            style='normal.TButton',
        )
        self.bbar.saveas_button.grid(column=2, row=0, padx=5)

        # Also a load button
        self.bbar.load_button = ttk.Button(
            self.bbar,
            text='Load',
            command=self.load_manual,
            style='normal.TButton',
        )
        self.bbar.load_button.grid(column=3, row=0, padx=5)

        # Define the HTML generate button
        self.bbar.html_button = ttk.Button(
            self.bbar,
            text='HTML',
            command=self.generate_html,
            style='normal.TButton',
        )
        self.bbar.html_button.grid(column=4, row=0, padx=5)

        # Define help button
        self.bbar.help_button = ttk.Button(
            self.bbar,
            text='Help',
            command=self.help.open,
            style='normal.TButton',
        )
        self.bbar.help_button.grid(column=5, row=0, padx=5)

        # Define settings button
        self.bbar.settings_button = ttk.Button(
            self.bbar,
            text='Settings',
            command=self.settings.open,
            style='normal.TButton',
        )
        self.bbar.settings_button.grid(column=6, row=0, padx=5)

        ToolTip(self.bbar.quit_button, text='Exit characterization tool')
        ToolTip(
            self.bbar.save_button, text='Save current characterization state'
        )
        ToolTip(
            self.bbar.saveas_button, text='Save current characterization state'
        )
        ToolTip(self.bbar.html_button, text='Generate HTML output')
        ToolTip(
            self.bbar.load_button, text='Load characterization state from file'
        )
        ToolTip(self.bbar.help_button, text='Start help tool')
        ToolTip(
            self.bbar.settings_button,
            text='Manage characterization tool settings',
        )

        # Inside frame with main electrical parameter display and scrollbar
        # To make the frame scrollable, it must be a frame inside a canvas.
        self.datasheet_viewer = tkinter.Canvas(self.mframe)
        self.datasheet_viewer.grid(row=0, column=0, sticky='nsew')
        self.datasheet_viewer.dframe = ttk.Frame(
            self.datasheet_viewer, style='bg.TFrame'
        )
        # Place the frame in the canvas
        self.datasheet_viewer.create_window(
            (0, 0),
            window=self.datasheet_viewer.dframe,
            anchor='nw',
            tags='self.frame',
        )

        # Make sure the main window resizes, not the scrollbars.
        self.mframe.rowconfigure(0, weight=1)
        self.mframe.columnconfigure(0, weight=1)
        # X scrollbar for datasheet viewer
        main_xscrollbar = ttk.Scrollbar(self.mframe, orient='horizontal')
        main_xscrollbar.grid(row=1, column=0, sticky='nsew')
        # Y scrollbar for datasheet viewer
        main_yscrollbar = ttk.Scrollbar(self.mframe, orient='vertical')
        main_yscrollbar.grid(row=0, column=1, sticky='nsew')
        # Attach console to scrollbars
        self.datasheet_viewer.config(xscrollcommand=main_xscrollbar.set)
        main_xscrollbar.config(command=self.datasheet_viewer.xview)
        self.datasheet_viewer.config(yscrollcommand=main_yscrollbar.set)
        main_yscrollbar.config(command=self.datasheet_viewer.yview)

        # Make sure that scrollwheel pans window
        self.datasheet_viewer.bind_all('<Button-4>', self.on_mousewheel)
        self.datasheet_viewer.bind_all('<Button-5>', self.on_mousewheel)

        # Set up configure callback
        self.datasheet_viewer.dframe.bind('<Configure>', self.frame_configure)

        # Add the panes once the internal geometry is known
        pane.add(self.toppane)
        pane.add(self.botpane)
        pane.paneconfig(self.toppane, stretch='first')

        # Initialize variables

        # Capture time of start to compare against the annotated
        # output file timestamp.
        self.starttime = time.time()

        # Redirect stdout and stderr to the console as the last thing to do. . .
        # Otherwise errors in the GUI get sucked into the void.
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = ConsoleText.StdoutRedirector(self.text_box)
        sys.stderr = ConsoleText.StderrRedirector(self.text_box)

        if message:
            print(message)

    def frame_configure(self, event):
        self.update_idletasks()
        self.datasheet_viewer.configure(
            scrollregion=self.datasheet_viewer.bbox('all')
        )

    def logstart(self):
        # Start a logfile (or append to it, if it already exists)
        # Disabled by default, as it can get very large.
        # Can be enabled from Settings.
        if self.settings.get_log() == True:
            dataroot = os.path.splitext(self.filename)[0]
            if not self.logfile:
                self.logfile = open(dataroot + '.log', 'a')

                # Print some initial information to the logfile.
                self.logprint('-------------------------')
                self.logprint(
                    'Starting new log file '
                    + datetime.datetime.now().strftime('%c'),
                    doflush=True,
                )

    def logstop(self):
        if self.logfile:
            self.logprint('-------------------------', doflush=True)
            self.logfile.close()
            self.logfile = []

    def logprint(self, message, doflush=False):
        if self.logfile:
            self.logfile.buffer.write(message.encode('utf-8'))
            self.logfile.buffer.write('\n'.encode('utf-8'))
            if doflush:
                self.logfile.flush()

    def set_working_directory(self, datasheet):
        # CACE should be run from the location of the datasheet's root
        # directory.  Typically, the datasheet is in the "cace" subdirectory
        # and "root" is "..".

        rootpath = None
        if 'paths' in datasheet:
            paths = datasheet['paths']
            if 'root' in paths:
                rootpath = paths['root']

        dspath = os.path.split(self.filename)[0]
        if rootpath:
            dspath = os.path.join(dspath, rootpath)
            paths['root'] = '.'

        os.chdir(dspath)
        print(
            'Working directory set to '
            + dspath
            + ' ('
            + os.path.abspath(dspath)
            + ')'
        )

    def set_datasheet(self, datasheet):
        if self.logfile:
            self.logprint('end of log.')
            self.logprint('-------------------------', doflush=True)
            self.logfile.close()
            self.logfile = None

        if not os.path.isfile(datasheet):
            print('Error:  File ' + datasheet + ' not found.')
            return

        debug = self.settings.get_debug()

        [dspath, dsname] = os.path.split(datasheet)
        # Read the datasheet
        if os.path.splitext(datasheet)[1] == '.json':
            with open(datasheet) as ifile:
                try:
                    # "data-sheet" as a sub-entry of the input file is deprecated.
                    datatop = json.load(ifile)
                    if 'data-sheet' in datatop:
                        datatop = datatop['data-sheet']
                except json.decoder.JSONDecodeError as e:
                    print(
                        'Error:  Parse error reading JSON file '
                        + datasheet
                        + ':'
                    )
                    print(str(e))
                    return
        else:
            datatop = cace_read(datasheet, debug)

        # Ensure that datasheet complies with CACE version 4.0 format
        dsheet = cace_compat(datatop, debug)

        self.filename = datasheet
        self.datasheet = dsheet
        self.create_datasheet_view()
        self.toppane.title_frame.datasheet_select.configure(text=dsname)
        self.toppane.title_frame.path_label.configure(text=datasheet)

        # Attempt to set the datasheet viewer width to the interior width
        # but do not set it larger than the available desktop.
        self.update_idletasks()
        widthnow = self.datasheet_viewer.winfo_width()
        width = self.datasheet_viewer.dframe.winfo_width()
        screen_width = self.root.winfo_screenwidth()
        if width > widthnow:
            if width < screen_width - 10:
                self.datasheet_viewer.configure(width=width)
            else:
                self.datasheet_viewer.configure(width=screen_width - 10)
        elif widthnow > screen_width:
            self.datasheet_viewer.configure(width=screen_width - 10)
        elif widthnow > width:
            self.datasheet_viewer.configure(width=width)

        # Likewise for the height, up to 3/5 of the desktop height.
        height = self.datasheet_viewer.dframe.winfo_height()
        heightnow = self.datasheet_viewer.winfo_height()
        screen_height = self.root.winfo_screenheight()
        if height > heightnow:
            if height < screen_height * 0.6:
                self.datasheet_viewer.configure(height=height)
            else:
                self.datasheet_viewer.configure(height=screen_height * 0.6)
        elif heightnow > screen_height:
            self.datasheet_viewer.configure(height=screen_height - 10)
        elif heightnow > height:
            self.datasheet_viewer.configure(height=height)

        # Set the current working directory from the datasheet's "path"
        # dictionary, then reset the root path to the current working
        # directory.
        self.set_working_directory(dsheet)

    def choose_datasheet(self):
        datasheet = filedialog.askopenfilename(
            multiple=False,
            initialdir=os.getcwd(),
            filetypes=(
                ('Text file', '*.txt'),
                ('JSON File', '*.json'),
                ('All Files', '*.*'),
            ),
            title='Find a datasheet.',
        )
        if datasheet != '':
            self.set_datasheet(datasheet)

    def topfilter(self, line):
        # Check output for ubiquitous "Reference value" lines and remove them.
        # This happens before logging both to the file and to the console.
        refrex = re.compile('Reference value')
        rmatch = refrex.match(line)
        if not rmatch:
            return line
        else:
            return None

    def spicefilter(self, line):
        # Check for the alarmist 'tran simulation interrupted' message and remove it.
        # Check for error or warning and print as stderr or stdout accordingly.
        intrex = re.compile('tran simulation interrupted')
        warnrex = re.compile('.*warning', re.IGNORECASE)
        errrex = re.compile('.*error', re.IGNORECASE)

        imatch = intrex.match(line)
        if not imatch:
            ematch = errrex.match(line)
            wmatch = warnrex.match(line)
            if ematch or wmatch:
                print(line, file=sys.stderr)
            else:
                print(line, file=sys.stdout)

    def printwarn(self, output):
        # Check output for warning or error
        if not output:
            return 0

        warnrex = re.compile('.*warning', re.IGNORECASE)
        errrex = re.compile('.*error', re.IGNORECASE)

        errors = 0
        outlines = output.splitlines()
        for line in outlines:
            try:
                wmatch = warnrex.match(line)
            except TypeError:
                line = line.decode('utf-8')
                wmatch = warnrex.match(line)
            ematch = errrex.match(line)
            if ematch:
                errors += 1
            if ematch or wmatch:
                print(line)
        return errors

    def sim_all(self):
        if self.procs_pending != {}:
            # Failsafe
            print('Simulation in progress must finish first.')
            return

        # Create netlist if necessary, check for valid result
        if self.sim_param('check') == False:
            return

        # Simulate all of the electrical parameters in turn.  These
        # are multiprocessed.
        for pname in self.status:
            self.sim_param(pname)

        # Button now stops the simulations
        self.allsimbutton.configure(
            style='redtitle.TButton',
            text='Stop Simulations',
            command=self.stop_sims,
        )

    def stop_sims(self):
        # Make sure there will be no more simulations

        if self.procs_pending == {}:
            print('No simulation running.')
            return

        # Force termination of threads and wait for them to exit.
        # NOTE:  The processes are nested, so do *not* use "terminate".
        # Instead, have each process set the same process group and then
        # send all process groups the SIGUSR1 signal.  Each child will
        # catch the SIGUSR1 and then terminate itself.

        os.killpg(os.getpid(), signal.SIGUSR1)
        print('Waiting for all processes to stop.')
        for procname in self.procs_pending.copy().keys():
            proc = self.procs_pending[procname]
            proc.join()
            self.procs_pending.pop(procname)

        print('All processes have stopped.')
        self.allsimbutton.configure(
            style='bluetitle.TButton',
            text='Simulate All',
            command=self.sim_all,
        )

        # Return all individual "Simulate" buttons to normal text
        for simbname in self.simbuttons.keys():
            simbutton = self.simbuttons[simbname]
            simbutton.configure(text='Simulate')

    def edit_param(self, param):
        # Edit the conditions under which the parameter is tested.
        if (
            'editable' in param and param['editable'] == True
        ) or self.settings.get_edit() == True:
            self.editparam.populate(param)
            self.editparam.open()
        else:
            print('Parameter is not editable')

    def copy_param(self, param):
        # Make a copy of the parameter (for editing)
        newparam = param.copy()
        # Make the copied parameter editable
        newparam['editable'] = True
        # Append this to the electrical parameter list after the item being copied
        if 'display' in param:
            newparam['display'] = param['display'] + ' (copy)'
        dsheet = self.datasheet
        eparams = dsheet['electrical_parameters']
        eidx = eparams.index(param)
        eparams.insert(eidx + 1, newparam)
        self.create_datasheet_view()

    def delete_param(self, param):
        # Remove an electrical parameter from the datasheet.  This is only
        # allowed if the parameter has been copied from another and so does
        # not belong to the original set of parameters.
        dsheet = self.datasheet
        eparams = dsheet['electrical_parameters']
        eidx = eparams.index(param)
        eparams.pop(eidx)
        self.create_datasheet_view()

    def add_hints(self, param, simbutton):
        # Raise hints window and configure appropriately for the parameter.
        # Fill in any existing hints.
        self.simhints.populate(param, simbutton)
        self.simhints.open()

    # Run cace_run and drop output onto the indicated queue
    def cace_process(self, datasheet, name):
        # Restore output, as the I/O redirection does not work inside
        # the child process (to do:  fix this?)
        sys.stdout = self.stdout
        sys.stderr = self.stderr

        # Set group ID for signaling.  Use the parent process ID as the group ID
        runtime_options = datasheet['runtime_options']
        if 'pid' in runtime_options:
            os.setpgid(os.getpid(), runtime_options['pid'])
            signal.signal(signal.SIGUSR1, child_process_exit)

        charresult = cace_run(datasheet, name)
        charresult['simname'] = name
        self.queue.put(charresult)
        sys.stdout.flush()
        sys.stderr.flush()

    # Get the value for runtime options['netlist_source']
    def get_netlist_source(self):
        netlist_text = self.origin.get()
        if netlist_text == 'Schematic Capture':
            return 'schematic'
        elif netlist_text == 'Layout Extracted':
            return 'layout'
        elif netlist_text == 'C Extracted':
            return 'pex'
        elif netlist_text == 'R-C Extracted':
            return 'rcx'
        else:
            print('Unhandled netlist source ' + netlist_text)
            print('Reverting to schematic.')
            return 'schematic'

    # Simulate a parameter (or run a physical parameter evaluation)
    def sim_param(self, name):
        dsheet = self.datasheet

        if 'runtime_options' in dsheet:
            runtime_options = dsheet['runtime_options']
        else:
            runtime_options = {}
            dsheet['runtime_options'] = runtime_options

        runtime_options['netlist_source'] = self.get_netlist_source()
        runtime_options['force'] = self.settings.get_force()
        runtime_options['keep'] = self.settings.get_keep()
        runtime_options['sequential'] = self.settings.get_sequential()
        runtime_options['noplot'] = self.settings.get_noplot()
        runtime_options['debug'] = self.settings.get_debug()

        if (
            'electrical_parameters' not in dsheet
            and 'physical_parameters' not in dsheet
        ):
            print('Error running parameter check on ' + name)
            print('No parameters found in datasheet')
            print('Datasheet entries are:')
            for key in dsheet.keys():
                print(key)
            return

        if name == 'check':
            # For the special keyword "check", do not multiprocess,
            # and return a pass/fail result according to the runtime status.
            cace_run(dsheet, name)
            if 'status' in runtime_options:
                status = runtime_options['status']
                runtime_options.pop('status')
                if status == 'failed':
                    return False
            return True

        try:
            eparam = next(
                item
                for item in dsheet['electrical_parameters']
                if item['name'] == name
            )
        except:
            try:
                pparam = next(
                    item
                    for item in dsheet['physical_parameters']
                    if item['name'] == name
                )
            except:
                print('Unknown parameter "' + name + '"')
                if 'electrical_parameters' in dsheet:
                    print('Known electrical parameters are:')
                    for eparam in dsheet['electrical_parameters']:
                        print(eparam['name'])
                if 'physical_parameters' in dsheet:
                    print('Known physical parameters are:')
                    for pparam in dsheet['physical_parameters']:
                        print(pparam['name'])
                return
            else:
                param = pparam
        else:
            param = eparam

        if name in self.procs_pending:
            print(
                'Process already running. . . Cancel process before re-running'
            )
            return

        # From the GUI, simulation is forced, so clear any "skip" status.
        # TO DO:  "gray out" entries marked as "skip" and require entry to
        # be set to "active" before simulating.
        if 'status' in param:
            if param['status'] == 'skip':
                print(
                    'Note: Parameter status changed from "skip" to "active".'
                )
                param['status'] = 'active'

        # Set the "Simulate" button to say "in progress"
        simbutton = self.simbuttons[name]
        simbutton.configure(text='(in progress)')

        # Diagnostic
        print('Simulating parameter ' + name)
        # NOTE: Commenting out the following line prevents the use of
        # the process ID to set a common group ID that can be used to
        # stop simulations by sending a kill signal to all threads.
        # The method is not working, and on some systems os.setpgid()
        # will not run.
        #
        # runtime_options['pid'] = os.getpid()
        p = multiprocessing.Process(
            target=self.cace_process,
            args=(
                dsheet,
                name,
            ),
        )
        # Save process pointer so it can be joined after it finishes.
        self.procs_pending[name] = p
        p.start()

        # Call watchproc() to start periodically watching the queue for
        # simulation results.
        self.watchproc()

    def watchproc(self):
        # Routine which is turned on when a cace_run
        # process is spawned, and periodically checks to see if a result
        # is available on the queue.  If so, then it pulls the datasheet
        # result from the queue, merges it back into the datasheet, joins
        # the spawned process, and removes the process from the list of
        # pending processes.  If the list of pending processes is not empty,
        # then watchproc() sets a timer to repeat itself.

        # If nothing is pending then return immediately and do not set a
        # repeat check.
        if self.procs_pending == {}:
            return

        # Check queue, non-blocking
        debug = self.settings.get_debug()
        try:
            charresult = self.queue.get(block=False)
        except:
            if debug:
                print(
                    'Watchproc found nothing in the queue; will wait longer.'
                )
            # Set watchproc to repeat after 1/2 second
            self.after(500, lambda: self.watchproc())
            return
        else:
            newparam = None
            iseparam = True
            pname = charresult['simname']

            # Return "Simulate" button to original text
            simbutton = self.simbuttons[pname]
            simbutton.configure(text='Simulate')

            print('Simulation of ' + pname + ' has completed.')
            if 'electrical_parameters' in charresult:
                eparams = charresult['electrical_parameters']
                for param in eparams:
                    if param['name'] == pname:
                        newparam = param
                        break
            if newparam == None and 'physical_parameters' in charresult:
                pparams = charresult['physical_parameters']
                for param in pparams:
                    if param['name'] == pname:
                        newparam = param
                        iseparam = False
                        break
            if newparam == None:
                print('Simulation failure on ' + pname + '.')
                return

            if not param:
                print('Error:  parameter ' + pname + ' not found in results!')
                return

            if pname in self.procs_pending:
                p = self.procs_pending[pname]
                self.procs_pending.pop(pname)
                if debug:
                    print('Now waiting to join process')
                p.join()
                if self.procs_pending == {}:
                    self.allsimbutton.configure(
                        style='bluetitle.TButton',
                        text='Simulate All',
                        command=self.sim_all,
                    )
            else:
                print(
                    'Error:  Parameter '
                    + pname
                    + ' has results but no process!'
                )

            # Replace the parameter in the master datasheet
            if 'electrical_parameters' in charresult and iseparam:
                eparamlist = self.datasheet['electrical_parameters']
                for i in range(0, len(eparamlist)):
                    checkparam = eparamlist[i]
                    if checkparam['name'] == pname:
                        eparamlist[i] = newparam
                        break

            if 'physical_parameters' in charresult and not iseparam:
                pparamlist = self.datasheet['physical_parameters']
                for i in range(0, len(pparamlist)):
                    checkparam = pparamlist[i]
                    if checkparam['name'] == pname:
                        pparamlist[i] = newparam
                        break

            # Regenerate datasheet view with parameter results
            self.create_datasheet_view()

    def clear_results(self, dsheet):
        # Remove results from the window by clearing parameter results
        paramstodo = []
        if 'electrical_parameters' in dsheet:
            paramstodo.extend(dsheet['electrical_parameters'])
        if 'physical_parameters' in dsheet:
            paramstodo.extend(dsheet['physical_parameters'])

        for param in paramstodo:
            # Fill frame with electrical parameter information
            if 'max' in param:
                maxrec = param['max']
                if 'value' in maxrec:
                    maxrec.pop('value')
                if 'score' in maxrec:
                    maxrec.pop('score')
            if 'typ' in param:
                typrec = param['typ']
                if 'value' in typrec:
                    typrec.pop('value')
                if 'score' in typrec:
                    typrec.pop('score')
            if 'min' in param:
                minrec = param['min']
                if 'value' in minrec:
                    minrec.pop('value')
                if 'score' in minrec:
                    minrec.pop('score')
            if 'results' in param:
                param.pop('results')

            if 'plot' in param:
                plotrec = param['plot']
                if 'status' in plotrec:
                    plotrec.pop('status')

        # Regenerate datasheet view
        self.create_datasheet_view()

    def annotate(self, suffix, checktime):
        # Pull results back from datasheet_anno.json.  Do NOT load this
        # file if it predates the unannotated datasheet (that indicates
        # simulator failure, and no results).
        dspath = os.path.split(self.filename)[0]
        if dspath == '':
            dspath = '.'
        dsdir = dspath + '/ngspice'
        anno = dsdir + '/datasheet_' + suffix + '.json'
        unanno = dsdir + '/datasheet.json'

        if os.path.exists(anno):
            statbuf = os.stat(anno)
            mtimea = statbuf.st_mtime
            if checktime >= mtimea:
                # print('original = ' + str(checktime) + ' annotated = ' + str(mtimea))
                print(
                    'Error in simulation, no update to results.',
                    file=sys.stderr,
                )
            elif statbuf.st_size == 0:
                print('Error in simulation, no results.', file=sys.stderr)
            elif os.path.splitext(anno)[1] == '.json':
                with open(anno, 'r') as file:
                    self.datasheet = json.load(file)
            else:
                debug = self.settings.get_debug()
                self.datasheet = cace_read(file, debug)
        else:
            print(
                'Error in simulation, no update to results.', file=sys.stderr
            )

        # Regenerate datasheet view
        self.create_datasheet_view()

        # Close log file, if it was enabled in the settings
        self.logstop()

    def save_results(self):
        # Write datasheet_save with all the locally processed results.
        dspath = os.path.split(self.filename)[0]

        # Save to simulation directory (may want to change this)
        dsheet = self.datasheet
        paths = dsheet['paths']
        dsdir = os.path.join(dspath, paths['root'], paths['simulation'])

        dfile = os.path.split(self.filename)[1]
        dfileroot = os.path.splitext(dfile)[0]
        dfileext = os.path.splitext(dfile)[1]

        # Output filename is the input datasheet filename + "_save",
        # and the same file extension.
        doutname = dfileroot + '_save' + dfileext
        doutfile = os.path.join(dsdir, doutname)

        if dfileext == '.json':
            with open(doutfile, 'w') as ofile:
                json.dump(self.datasheet, ofile, indent=4)
        else:
            # NOTE:  This file contains the run-time settings dictionary
            cace_write(self.datasheet, doutfile)

        self.last_save = os.path.getmtime(doutfile)

        print('Characterization results saved.')

    def check_saved(self):
        # Check if there is a file 'datasheet_save' and if it is more
        # recent than 'datasheet_anno'.  If so, return True, else False.

        [dspath, dsname] = os.path.split(self.filename)
        dsdir = dspath + '/ngspice'

        savefile = dsdir + '/datasheet_save.json'

        annofile = dsdir + '/datasheet_anno.json'
        if os.path.exists(annofile):
            annotime = os.path.getmtime(annofile)

            # If nothing has been updated since the characterization
            # tool was started, then there is no new information to save.
            if annotime < self.starttime:
                return True

            if os.path.exists(savefile):
                savetime = os.path.getmtime(savefile)
                # return True if (savetime > annotime) else False
                if savetime > annotime:
                    print('Save is more recent than sim, so no need to save.')
                    return True
                else:
                    print('Sim is more recent than save, so need to save.')
                    return False
            else:
                # There is a datasheet_anno file but no datasheet_save,
                # so there are necessarily unsaved results.
                print('no datasheet_save, so any results have not been saved.')
                return False
        else:
            # There is no datasheet_anno file, so datasheet_save
            # is either current or there have been no simulations.
            print('no datasheet_anno, so there are no results to save.')
            return True

    def save_manual(self, value={}):
        dspath = self.filename
        # Set initialdir to the project where datasheet is located
        dsparent = os.path.split(dspath)[0]

        datasheet = filedialog.asksaveasfilename(
            initialdir=dsparent,
            confirmoverwrite=True,
            defaultextension='.txt',
            filetypes=(
                ('Text file', '*.txt'),
                ('JSON File', '*.json'),
                ('All Files', '*.*'),
            ),
            title='Select filename for saved datasheet.',
        )

        if isinstance(datasheet, str):
            if os.path.splitext(datasheet)[1] == '.json':
                with open(datasheet, 'w') as ofile:
                    json.dump(self.datasheet, ofile, indent=4)
            else:
                cace_write(self.datasheet, datasheet)

    def load_manual(self, value={}):
        dspath = self.filename
        # Set initialdir to the project where datasheet is located
        dsparent = os.path.split(dspath)[0]

        datasheet = filedialog.askopenfilename(
            multiple=False,
            initialdir=dsparent,
            filetypes=(
                ('Text file', '*.txt'),
                ('JSON File', '*.json'),
                ('All Files', '*.*'),
            ),
            title='Find a datasheet.',
        )
        if datasheet != '':
            print('Reading file ' + datasheet)
            if os.path.splitext(datasheet)[1] == '.json':
                with open(datasheet, 'r') as file:
                    try:
                        self.datasheet = json.load(file)
                    except:
                        print(
                            'Error in file, no update to results.',
                            file=sys.stderr,
                        )
                    else:
                        # Regenerate datasheet view
                        self.create_datasheet_view()
            else:
                debug = self.settings.get_debug()
                try:
                    self.datasheet = cace_read(datasheet, debug)
                except:
                    print(
                        'Error in file, no update to results.', file=sys.stderr
                    )
                else:
                    # Regenerate datasheet view
                    self.set_working_directory(self.datasheet)
                    self.create_datasheet_view()

    def generate_html(self, value={}):
        debug = self.settings.get_debug()
        cace_generate_html(self.datasheet, None, debug)

    def swap_results(self, value={}):
        # This routine just calls self.create_datasheet_view(), but the
        # button callback has an argument that needs to be handled even
        # if it is just discarded.
        self.create_datasheet_view()

    def load_results(self, value={}):

        # Check if datasheet_save exists and is more recent than the
        # latest design netlist.  If so, load it;  otherwise, not.
        # NOTE:  Name of .spice file comes from the project 'name'
        # in the datasheet.

        [dspath, dsname] = os.path.split(self.filename)
        try:
            dsheet = self.datasheet
        except KeyError:
            return

        if dspath == '':
            dspath = '.'

        dsroot = dsheet['name']

        # Remove any existing results from the datasheet records
        self.clear_results(dsheet)

        # Also must be more recent than datasheet
        jtime = os.path.getmtime(self.filename)

        # dsroot = os.path.splitext(dsname)[0]

        paths = dsheet['paths']
        dsdir = os.path.join(dspath, paths['root'], paths['simulation'])

        if not os.path.exists(dsdir):
            # Try 'spice' as a subdirectory of the datasheet directory as a
            # fallback.
            dsdir = dspath + '/spice'
            if not os.path.exists(dsdir):
                print('Error:  Cannot find directory spice/ in path ' + dspath)

        if self.origin.get() == 'Layout Extracted':
            spifile = dsdir + '/layout/' + dsroot + '.spice'
        if self.origin.get() == 'C Extracted':
            spifile = dsdir + '/pex/' + dsroot + '.spice'
        elif self.origin.get() == 'R-C Extracted':
            spifile = dsdir + '/rcx/' + dsroot + '.spice'
        else:
            spifile = dsdir + '/' + dsroot + '.spice'

        dsdir = dspath + '/ngspice'
        savefile = dsdir + '/datasheet_save.json'

        if os.path.exists(savefile):
            savetime = os.path.getmtime(savefile)

        if os.path.exists(spifile):
            spitime = os.path.getmtime(spifile)

            if os.path.exists(savefile):
                if savetime > spitime and savetime > jtime:
                    self.annotate('save', 0)
                    print('Characterization results loaded.')
                    # print('(' + savefile + ' timestamp = ' + str(savetime) + '; ' + self.datasheet + ' timestamp = ' + str(jtime))
                else:
                    print('Saved datasheet is out-of-date, not loading')
            else:
                print('Datasheet file ' + savefile)
                print('No saved datasheet file, nothing to pre-load')
        else:
            print('No netlist file ' + spifile + '!')

        # Remove outdated datasheet.json and datasheet_anno.json to prevent
        # them from overwriting characterization document entries

        if os.path.exists(savefile):
            if savetime < jtime:
                print('Removing outdated save file ' + savefile)
                os.remove(savefile)

        savefile = dsdir + '/datasheet_anno.json'
        if os.path.exists(savefile):
            savetime = os.path.getmtime(savefile)
            if savetime < jtime:
                print('Removing outdated results file ' + savefile)
                os.remove(savefile)

        savefile = dsdir + '/datasheet.json'
        if os.path.exists(savefile):
            savetime = os.path.getmtime(savefile)
            if savetime < jtime:
                print('Removing outdated results file ' + savefile)
                os.remove(savefile)

    def create_datasheet_view(self):
        dframe = self.datasheet_viewer.dframe

        # Destroy the existing datasheet frame contents (if any)
        for widget in dframe.winfo_children():
            widget.destroy()
        self.status = {}  	# Clear dictionary

        dsheet = self.datasheet
        if 'runtime_options' in dsheet:
            runtime_options = dsheet['runtime_options']
        else:
            runtime_options = {}
            dsheet['runtime_options'] = runtime_options

        runtime_options['netlist_source'] = self.get_netlist_source()

        # Add basic information at the top

        n = 0
        dframe.cframe = ttk.Frame(dframe)
        dframe.cframe.grid(column=0, row=n, sticky='ewns', columnspan=10)

        dframe.cframe.plabel = ttk.Label(
            dframe.cframe, text='Project IP name:', style='italic.TLabel'
        )
        dframe.cframe.plabel.grid(column=0, row=n, sticky='ewns', ipadx=5)
        dframe.cframe.pname = ttk.Label(
            dframe.cframe, text=dsheet['name'], style='normal.TLabel'
        )
        dframe.cframe.pname.grid(column=1, row=n, sticky='ewns', ipadx=5)
        if 'foundry' in dsheet:
            dframe.cframe.fname = ttk.Label(
                dframe.cframe, text=dsheet['foundry'], style='normal.TLabel'
            )
            dframe.cframe.fname.grid(column=2, row=n, sticky='ewns', ipadx=5)
        if 'PDK' in dsheet:
            dframe.cframe.fname = ttk.Label(
                dframe.cframe, text=dsheet['PDK'], style='normal.TLabel'
            )
            dframe.cframe.fname.grid(column=3, row=n, sticky='ewns', ipadx=5)
        if 'description' in dsheet:
            dframe.cframe.pdesc = ttk.Label(
                dframe.cframe,
                text=dsheet['description'],
                style='normal.TLabel',
            )
            dframe.cframe.pdesc.grid(column=4, row=n, sticky='ewns', ipadx=5)

        n = 1
        ttk.Separator(dframe, orient='horizontal').grid(
            column=0, row=n, sticky='ewns', columnspan=10
        )

        # Title block
        n += 1
        dframe.desc_title = ttk.Label(
            dframe, text='Parameter', style='title.TLabel'
        )
        dframe.desc_title.grid(column=0, row=n, sticky='ewns')
        dframe.method_title = ttk.Label(
            dframe, text='Testbench', style='title.TLabel'
        )
        dframe.method_title.grid(column=1, row=n, sticky='ewns')
        dframe.min_title = ttk.Label(dframe, text='Min', style='title.TLabel')
        dframe.min_title.grid(column=2, row=n, sticky='ewns', columnspan=2)
        dframe.typ_title = ttk.Label(dframe, text='Typ', style='title.TLabel')
        dframe.typ_title.grid(column=4, row=n, sticky='ewns', columnspan=2)
        dframe.max_title = ttk.Label(dframe, text='Max', style='title.TLabel')
        dframe.max_title.grid(column=6, row=n, sticky='ewns', columnspan=2)
        dframe.stat_title = ttk.Label(
            dframe, text='Status', style='title.TLabel'
        )
        dframe.stat_title.grid(column=8, row=n, sticky='ewns')

        if self.procs_pending == {}:
            self.allsimbutton = ttk.Button(
                dframe,
                text='Simulate All',
                style='bluetitle.TButton',
                command=self.sim_all,
            )
        else:
            self.allsimbutton = ttk.Button(
                dframe,
                text='Stop Simulations',
                style='redtitle.TButton',
                command=self.stop_sims,
            )
        self.allsimbutton.grid(column=9, row=n, sticky='ewns')

        ToolTip(self.allsimbutton, text='Simulate all electrical parameters')

        # Make all columns equally expandable
        for i in range(10):
            dframe.columnconfigure(i, weight=1)

        # Parse the file for electrical parameters
        n += 1
        binrex = re.compile(r'([0-9]*)\'([bodh])', re.IGNORECASE)
        paramstodo = []
        if 'electrical_parameters' in dsheet:
            paramstodo.extend(dsheet['electrical_parameters'])
        if 'physical_parameters' in dsheet:
            paramstodo.extend(dsheet['physical_parameters'])

        if self.origin.get() == 'Schematic Capture':
            isschem = True
        else:
            isschem = False

        # Track the "Simulate" buttons by parameter name (dictionary)
        self.simbuttons = {}

        for param in paramstodo:
            pname = param['name']
            # Fill frame with electrical parameter information
            if 'simulate' in param:
                mdict = param['simulate']
                p = mdict['template']
                if pname in self.status:
                    # This method was used before, so give it a unique identifier
                    j = 1
                    while True:
                        pname = p + '.' + str(j)
                        if pname not in self.status:
                            break
                        else:
                            j += 1
                else:
                    j = 0
                paramtype = 'electrical'
            elif 'evaluate' in param:
                paramtype = 'physical'
                mdict = param['evaluate']
                p = mdict['tool']
                if isinstance(p, list):
                    p = p[0]
                j = 0
            else:
                p = 'none'
                paramtype = 'unknown'
                print('Parameter ' + pname + ' unknown type.')

            if 'editable' in param and param['editable'] == True:
                normlabel = 'hlight.TLabel'
                redlabel = 'rhlight.TLabel'
                greenlabel = 'ghlight.TLabel'
                normbutton = 'hlight.TButton'
                redbutton = 'rhlight.TButton'
                greenbutton = 'ghlight.TButton'
            else:
                normlabel = 'normal.TLabel'
                redlabel = 'red.TLabel'
                greenlabel = 'green.TLabel'
                normbutton = 'normal.TButton'
                redbutton = 'red.TButton'
                greenbutton = 'green.TButton'

            if 'display' in param:
                dtext = param['display']
            else:
                dtext = p

            # Special handling:  Change LVS_errors to "device check" when using
            # schematic netlist.
            if paramtype == 'physical':
                if isschem:
                    if p == 'cace_lvs':
                        dtext = 'Invalid device check'
                    if p == 'cace_area':
                        dtext = 'Area estimate'

            dframe.description = ttk.Label(dframe, text=dtext, style=normlabel)

            dframe.description.grid(column=0, row=n, sticky='ewns')
            dframe.method = ttk.Label(dframe, text=p, style=normlabel)
            dframe.method.grid(column=1, row=n, sticky='ewns')
            if 'plot' in param:
                # For plots, the status still comes from the 'results' dictionary
                status_style = normlabel
                dframe.plots = ttk.Frame(dframe)
                dframe.plots.grid(column=2, row=n, columnspan=6, sticky='ewns')
                status_value = '(not checked)'

                if 'results' in param:
                    reslist = param['results']
                    if 'netlist_source' in runtime_options:
                        netlist_source = runtime_options['netlist_source']
                    if isinstance(reslist, list):
                        try:
                            resdict = next(
                                item
                                for item in reslist
                                if item['name'] == netlist_source
                            )
                        except:
                            resdict = None
                    elif reslist['name'] == netlist_source:
                        resdict = reslist
                    else:
                        resdict = None

                    if resdict:
                        if 'status' in resdict:
                            status_value = resdict['status']

                plotrec = param['plot']
                if 'filename' in plotrec:
                    plottext = plotrec['filename']
                elif 'type' in plotrec:
                    plottext = plotrec['type']
                else:
                    plottext = 'plot'
                dframe_plot = ttk.Label(
                    dframe.plots, text=plottext, style=normlabel
                )
                dframe_plot.grid(column=j, row=n, sticky='ewns')
            else:
                # For schematic capture, mark physical parameters that can't and won't be
                # checked as "not applicable".
                status_value = '(not checked)'
                if paramtype == 'physical':
                    if isschem:
                        if (
                            p == 'cace_width'
                            or p == 'cace_height'
                            or p == 'cace_drc'
                        ):
                            status_value = '(N/A)'

                # Grab the electrical parameter's 'spec' and 'result' dictionaries
                if 'spec' in param:
                    specdict = param['spec']
                else:
                    specdict = {}

                # Which information is provided depends on which origin is
                # selected.

                valid = False
                if 'results' in param:
                    resultlist = param['results']
                    if not isinstance(resultlist, list):
                        resultlist = [resultlist]

                    if self.origin.get() == 'R-C Extracted':
                        for resultdict in resultlist:
                            if resultdict['name'] == 'rcx':
                                valid = True
                                break
                    elif self.origin.get() == 'C Extracted':
                        for resultdict in resultlist:
                            if resultdict['name'] == 'pex':
                                valid = True
                                break
                    elif self.origin.get() == 'Layout Extracted':
                        for resultdict in resultlist:
                            if resultdict['name'] == 'layout':
                                valid = True
                                break
                    else:  	# Schematic capture
                        for resultdict in resultlist:
                            if resultdict['name'] == 'schematic':
                                valid = True
                                break

                if valid == False:
                    # No result dictionary exists for this netlist origin type
                    resultdict = {}

                # Fill in information for the spec minimum and result
                if 'minimum' in specdict:
                    status_style = normlabel
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
                        else:
                            score = None
                    else:
                        value = None
                        score = None

                    if pmin == 'any':
                        dframe.min = ttk.Label(
                            dframe, text='(no limit)', style=normlabel
                        )
                    else:
                        if 'unit' in param and not binrex.match(param['unit']):
                            targettext = pmin + ' ' + param['unit']
                        else:
                            targettext = pmin
                        dframe.min = ttk.Label(
                            dframe, text=targettext, style=normlabel
                        )

                    if score:
                        if score != 'fail':
                            status_style = greenlabel
                            if status_value != 'fail':
                                status_value = 'pass'
                        else:
                            status_style = redlabel
                            status_value = 'fail'
                    if value:
                        if value == 'failure' or value == 'fail':
                            status_value = '(not checked)'
                            status_style = redlabel
                            valuetext = value
                        elif 'unit' in param and not binrex.match(
                            param['unit']
                        ):
                            valuetext = value + ' ' + param['unit']
                        else:
                            valuetext = value
                        dframe.value = ttk.Label(
                            dframe, text=valuetext, style=status_style
                        )
                        dframe.value.grid(column=3, row=n, sticky='ewns')
                else:
                    dframe.min = ttk.Label(
                        dframe, text='(no limit)', style=normlabel
                    )

                dframe.min.grid(column=2, row=n, sticky='ewns')

                # Fill in information for the spec typical and result
                if 'typical' in specdict:
                    status_style = normlabel
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
                        else:
                            score = None
                    else:
                        value = None
                        score = None

                    if ptyp == 'any':
                        dframe.typ = ttk.Label(
                            dframe, text='(no target)', style=normlabel
                        )
                    else:
                        if 'unit' in param and not binrex.match(param['unit']):
                            targettext = ptyp + ' ' + param['unit']
                        else:
                            targettext = ptyp
                        dframe.typ = ttk.Label(
                            dframe, text=targettext, style=normlabel
                        )

                    if score:
                        # Note:  You can't fail a "typ" score, but there is only one "Status",
                        # so if it is a "fail", it must remain a "fail".
                        if score != 'fail':
                            status_style = greenlabel
                            if status_value != 'fail':
                                status_value = 'pass'
                        else:
                            status_style = redlabel
                            status_value = 'fail'
                    if value:
                        if value == 'failure' or value == 'fail':
                            status_value = '(not checked)'
                            status_style = redlabel
                            valuetext = value
                        elif 'unit' in param and not binrex.match(
                            param['unit']
                        ):
                            valuetext = value + ' ' + param['unit']
                        else:
                            valuetext = value
                        dframe.value = ttk.Label(
                            dframe, text=valuetext, style=status_style
                        )
                        dframe.value.grid(column=5, row=n, sticky='ewns')
                else:
                    dframe.typ = ttk.Label(
                        dframe, text='(no target)', style=normlabel
                    )
                dframe.typ.grid(column=4, row=n, sticky='ewns')

                # Fill in information for the spec maximum and result
                if 'maximum' in specdict:
                    status_style = normlabel
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
                        else:
                            score = None
                    else:
                        value = None
                        score = None

                    if pmax == 'any':
                        dframe.max = ttk.Label(
                            dframe, text='(no limit)', style=normlabel
                        )
                    else:
                        if 'unit' in param and not binrex.match(param['unit']):
                            targettext = pmax + ' ' + param['unit']
                        else:
                            targettext = pmax
                        dframe.max = ttk.Label(
                            dframe, text=targettext, style=normlabel
                        )

                    if score:
                        if score != 'fail':
                            status_style = greenlabel
                            if status_value != 'fail':
                                status_value = 'pass'
                        else:
                            status_style = redlabel
                            status_value = 'fail'
                    if value:
                        if value == 'failure' or value == 'fail':
                            status_value = '(not checked)'
                            status_style = redlabel
                            valuetext = value
                        elif 'unit' in param and not binrex.match(
                            param['unit']
                        ):
                            valuetext = value + ' ' + param['unit']
                        else:
                            valuetext = value
                        dframe.value = ttk.Label(
                            dframe, text=valuetext, style=status_style
                        )
                        dframe.value.grid(column=7, row=n, sticky='ewns')
                else:
                    dframe.max = ttk.Label(
                        dframe, text='(no limit)', style=normlabel
                    )
                dframe.max.grid(column=6, row=n, sticky='ewns')

            if paramtype == 'electrical':
                if 'hints' in param:
                    simtext = '\u2022Simulate'
                else:
                    simtext = 'Simulate'
            else:
                simtext = 'Check'

            if self.procs_pending:
                if pname in self.procs_pending:
                    simtext = '(in progress)'

            simbutton = ttk.Menubutton(dframe, text=simtext, style=normbutton)
            self.simbuttons[pname] = simbutton

            # Generate pull-down menu on Simulate button.  Most items apply
            # only to electrical parameters (at least for now)
            simmenu = tkinter.Menu(simbutton)
            simmenu.add_command(
                label='Run', command=lambda pname=pname: self.sim_param(pname)
            )
            simmenu.add_command(label='Stop', command=self.stop_sims)
            if paramtype == 'electrical':
                # simmenu.add_command(label='Hints',
                # 	command = lambda param=param, simbutton=simbutton: self.add_hints(param, simbutton))
                simmenu.add_command(
                    label='Edit',
                    command=lambda param=param: self.edit_param(param),
                )
                simmenu.add_command(
                    label='Copy',
                    command=lambda param=param: self.copy_param(param),
                )
                if 'editable' in param and param['editable'] == True:
                    simmenu.add_command(
                        label='Delete',
                        command=lambda param=param: self.delete_param(param),
                    )

            # Attach the menu to the button
            simbutton.config(menu=simmenu)

            # simbutton = ttk.Button(dframe, text=simtext, style = normbutton)
            # 		command = lambda pname=pname: self.sim_param(pname))

            simbutton.grid(column=9, row=n, sticky='ewns')

            if paramtype == 'electrical':
                ToolTip(simbutton, text='Simulate one electrical parameter')
            else:
                ToolTip(simbutton, text='Check one physical parameter')

            # If 'pass', then just display message.  If 'fail', then create a button that
            # opens and configures the failure report window.
            if status_value == '(not checked)':
                bstyle = normbutton
                stat_label = ttk.Label(dframe, text=status_value, style=bstyle)
            else:
                if status_value == 'fail' or status_value == 'failure':
                    bstyle = redbutton
                else:
                    bstyle = greenbutton
                if paramtype == 'electrical':
                    stat_label = ttk.Button(
                        dframe,
                        text=status_value,
                        style=bstyle,
                        command=lambda param=param, dsheet=dsheet: self.failreport.display(
                            param, dsheet, self.datasheet
                        ),
                    )
                elif p == 'LVS_errors':
                    dspath = os.path.split(self.filename)[0]
                    datasheet = os.path.split(self.filename)[1]
                    dsheet = self.datasheet
                    designname = dsheet['name']
                    if self.origin.get() == 'Schematic Capture':
                        lvs_file = dspath + '/mag/precheck.log'
                    else:
                        lvs_file = dspath + '/mag/comp.out'
                    if not os.path.exists(lvs_file):
                        if os.path.exists(dspath + '/mag/precheck.log'):
                            lvs_file = dspath + '/mag/precheck.log'
                        elif os.path.exists(dspath + '/mag/comp.out'):
                            lvs_file = dspath + '/mag/comp.out'

                    stat_label = ttk.Button(
                        dframe,
                        text=status_value,
                        style=bstyle,
                        command=lambda lvs_file=lvs_file: self.textreport.display(
                            lvs_file
                        ),
                    )
                else:
                    stat_label = ttk.Label(
                        dframe, text=status_value, style=bstyle
                    )
                ToolTip(
                    stat_label,
                    text='Show detail view of simulation conditions and results',
                )
            stat_label.grid(column=8, row=n, sticky='ewns')
            self.status[pname] = stat_label
            n += 1

        for child in dframe.winfo_children():
            child.grid_configure(ipadx=5, ipady=1, padx=2, pady=2)


# --------------------------------------------------------------------------
# Print usage information for cace_gui.py
# --------------------------------------------------------------------------


def usage():
    print('')
    print('CACE GUI')
    print(
        '   Graphical interface for the Circuit Automatic Characterization Engine,'
    )
    print('   an analog and mixed-signal design flow system.')
    print('')
    print('Usage:')
    print('   cace_gui.py [characterization_file] [option]')
    print('')
    print('where:')
    print('   characterization_file is a text or JSON file with the')
    print('       specification of the circuit.')
    print('')
    print('and valid options are:')
    print('   -term')
    print('       Generate all output to the terminal, not the window.')
    print('   -help')
    print('       Print this help text.')
    print('')


# --------------------------------------------------------------------------
# Main entry point for cace_gui.py
# --------------------------------------------------------------------------


def gui():
    options = []
    arguments = []
    for item in sys.argv[1:]:
        if item.find('-', 0) == 0:
            options.append(item.strip('-'))
        else:
            arguments.append(item)

    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    root = tkinter.Tk()
    app = CACECharacterize(root)

    if 'term' in options or 'help' in options:
        # Revert output to the terminal
        sys.stdout = app.stdout
        sys.stderr = app.stderr

    if 'help' in options:
        usage()
        sys.exit(0)

    if arguments:
        print('Setting datasheet to ' + arguments[0])
        app.set_datasheet(arguments[0])
    else:
        # Check the current working directory and determine if there
        # is a .txt or .json file with the name of the directory, which
        # is assumed to have the same name as the project circuit.  Also
        # check subdirectories one level down.
        curdir = os.getcwd()
        dirname = os.path.split(curdir)[1]
        dirlist = os.listdir(curdir)

        # Look through all directories for a '.txt' file
        found = False
        for item in dirlist:
            if os.path.isfile(item):
                fileext = os.path.splitext(item)[1]
                basename = os.path.splitext(item)[0]
                if fileext == '.txt':
                    if basename == dirname:
                        print('Setting datasheet to ' + item)
                        app.set_datasheet(item)
                        found = True
                        break
            elif os.path.isdir(item):
                subdirlist = os.listdir(item)
                for subitem in subdirlist:
                    subitemref = os.path.join(item, subitem)
                    if os.path.isfile(subitemref):
                        fileext = os.path.splitext(subitem)[1]
                        basename = os.path.splitext(subitem)[0]
                        if fileext == '.txt':
                            if basename == dirname:
                                print('Setting datasheet to ' + subitemref)
                                app.set_datasheet(subitemref)
                                found = True
                                break

        # Look through all directories for a '.json' file
        # ('.txt') is preferred to ('.json')

        if not found:
            for item in dirlist:
                if os.path.isfile(item):
                    fileext = os.path.splitext(item)[1]
                    basename = os.path.splitext(item)[0]
                    if fileext == '.json':
                        if basename == dirname:
                            print('Setting datasheet to ' + item)
                            app.set_datasheet(item)
                            found = True
                            break
                elif os.path.isdir(item):
                    subdirlist = os.listdir(item)
                    for subitem in subdirlist:
                        subitemref = os.path.join(item, subitem)
                        if os.path.isfile(subitemref):
                            fileext = os.path.splitext(subitem)[1]
                            basename = os.path.splitext(subitem)[0]
                            if fileext == '.json':
                                if basename == dirname:
                                    print('Setting datasheet to ' + subitemref)
                                    app.set_datasheet(subitemref)
                                    found = True
                                    break

        if not found:
            print('No datasheet found in local project (JSON or text file).')

    root.mainloop()


if __name__ == '__main__':
    gui()
