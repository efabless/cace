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
import tkinter
from tkinter import ttk

# User preferences file (if it exists)
prefsfile = '~/design/.profile/prefs.json'


def init_style():
    """Sets the global style"""

    fontsize = 11

    # Read user preferences file, get default font size from it.
    prefspath = os.path.expanduser(prefsfile)
    if os.path.exists(prefspath):
        with open(prefspath, 'r') as f:
            prefs = json.load(f)
        if 'fontsize' in prefs:
            fontsize = prefs['fontsize']
    else:
        prefs = {}

    s = ttk.Style()

    available_themes = s.theme_names()
    s.theme_use(available_themes[0])

    s.configure('bg.TFrame', background='gray40')
    s.configure(
        'italic.TLabel', font=('Helvetica', fontsize, 'italic')
    )   # anchor='west'
    s.configure(
        'title.TLabel',
        font=('Helvetica', fontsize, 'bold'),
        foreground='brown',
        anchor='center',
    )
    s.configure('normal.TLabel', font=('Helvetica', fontsize))
    s.configure('red.TLabel', font=('Helvetica', fontsize), foreground='red')
    s.configure(
        'green.TLabel',
        font=('Helvetica', fontsize),
        foreground='green3',  # green4
    )
    s.configure('blue.TLabel', font=('Helvetica', fontsize), foreground='blue')
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
        foreground='green3',  # green4
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
        font=('Helvetica', fontsize, 'bold'),
        foreground='blue',
        border=3,
        relief='raised',
    )
    s.configure(
        'brown.TLabel',
        font=('Helvetica', fontsize, 'italic'),
        foreground='brown',
        anchor='center',
    )
    s.configure(
        'title.TButton',
        font=('Helvetica', fontsize, 'bold italic'),
        foreground='brown',
        border=0,
        relief='groove',
    )

    return fontsize
