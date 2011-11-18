#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Contains information about the program's global state, and eventually,
methods for testing that state (for example, see if we are admin, have write access, etc"""

import sys

#: whether the main loop should exit
DONE = False
#: whether this is using the live network or not:
IS_LIVE = True
#: controls whether to run in debug mode or not:
DEBUG = False
#: when the program was started
START_TIME = None
#: whether the program has admin privleges or not
IS_ADMIN = False
#: whether we've been installed or are running via a python interpretter:
INSTALLED = False
#: whether this is running as a py2exe application (installed on windows) or not:
PY2EXE = hasattr(sys, "frozen")
#: whether this run was directly after an update
JUST_UPDATED = False

#: current working directory that BitBlinder was started in
STARTING_DIR = None
#: directory that bitblinder was installed/check out to
INSTALL_DIR = None
#: directory for storing this user's settings
USER_DIR = None
#: full path to python.exe or bitblinder.exe (depending on if PY2EXE'd or not)
EXECUTABLE = None
#: name of the currently running main script (or BitBlinder.exe if we are py2exe'd)
MAIN_SCRIPT = None

#: whether to use GTK for the GUI and main loop:
USE_GTK = True
#: whether to use curses for the GUI:
USE_CURSES = False

#: points to either common.conf.Dev or common.conf.Live as appropriate (depending on IS_LIVE)
Conf = None
#TODO:  remove this, restructure objects to deal with their own updates
#: whether on_update functions will be called
DO_UPDATES = False
#: this is just for debugging, so that we can attach to a Tor.exe that is being debugged
USE_EXISTING_TOR = False

