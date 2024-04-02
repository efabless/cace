#!/usr/bin/env python3
#
# --------------------------------------------------------
# Help Window for the Project manager
#
# --------------------------------------------------------
# Written by Tim Edwards
# efabless, inc.
# September 12, 2016
# Version 0.1
# --------------------------------------------------------

import re
import webbrowser
import tkinter
from tkinter import ttk
from tkinter.font import Font, nametofont

from ..__version__ import __version__


class LinkButton(ttk.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use the default font.
        label_font = nametofont('TkDefaultFont').cget('family')
        self.font = Font(family=label_font, size=9)

        # Label-like styling.
        style = ttk.Style()
        style.configure('Link.TLabel', foreground='#357fde')
        self.configure(style='Link.TLabel', cursor='hand2')
        self.bind('<Enter>', self.on_mouse_enter)
        self.bind('<Leave>', self.on_mouse_leave)

    def on_mouse_enter(self, event):
        self.font.configure(underline=True)

    def on_mouse_leave(self, event):
        self.font.configure(underline=False)


class HelpWindow(tkinter.Toplevel):
    """help window"""

    def __init__(self, parent=None, fontsize=11, *args, **kwargs):
        """See the __init__ for Tkinter.Toplevel."""
        tkinter.Toplevel.__init__(self, parent, *args, **kwargs)

        self.geometry('520x300')

        self.protocol('WM_DELETE_WINDOW', self.close)

        self.withdraw()
        self.title('Help')

        # Automatically fit the window
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(6, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Title
        helptitle = ttk.Label(
            self,
            text=f'CACE {__version__}',
            style='title.TLabel',
            justify='center',
        )
        helptitle.grid(column=0, row=0)

        # Subtitle
        helptext1 = ttk.Label(
            self,
            text="""Graphical interface for the Circuit Automatic Characterization Engine,
    an analog and mixed-signal design flow system.""",
            justify='center',
        )
        helptext1.grid(column=0, row=1)

        # Bar
        helpbar = ttk.Separator(self, orient='horizontal')
        helpbar.grid(column=0, row=2, sticky='ew')

        # Text
        helptext2 = ttk.Label(
            self,
            text='The repository and documentation are hosted online at:',
            justify='center',
        )
        helptext2.grid(column=0, row=3)

        # URL repository
        project_frame = ttk.Frame(self)
        project_frame.grid(column=0, row=4, columnspan=2)

        title = ttk.Label(project_frame, text='Repository: ')
        title.grid(column=0, row=0)

        url1 = 'https://github.com/efabless/cace'
        link = LinkButton(project_frame, text=url1)
        link.bind('<Button-1>', lambda e: webbrowser.open_new(url1))
        link.grid(column=1, row=0)

        # URL documentation
        docs_frame = ttk.Frame(self)
        docs_frame.grid(column=0, row=5, columnspan=2)

        title = ttk.Label(docs_frame, text='Documentation: ')
        title.grid(column=0, row=0)

        url2 = 'https://cace.readthedocs.io/'
        link = LinkButton(docs_frame, text=url2)
        link.bind('<Button-1>', lambda e: webbrowser.open_new(url2))
        link.grid(column=1, row=0)

        # Placeholder
        docs_frame = ttk.Frame(self)
        docs_frame.grid(column=0, row=6, columnspan=1)

    def close(self):
        # pop down help window
        self.withdraw()

    def open(self):
        # pop up help window
        self.deiconify()
        self.lift()
