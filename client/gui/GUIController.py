#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Python module for main GUI"""

#REFACTOR:  take all application imports out of GUIs so that this isnt circular and can go back to the top

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from core import ProgramState

_instance = None
def get():
  return _instance
  
def start():
  global _instance
  if not _instance:
    if ProgramState.USE_GTK:
      import gui.gtk.Controller
      _instance = gui.gtk.Controller.Controller()
    elif ProgramState.USE_CURSES:
      import gui.curses.Controller
      _instance = gui.curses.Controller.Controller()
    else:
      import gui.console.Controller
      _instance = gui.console.Controller.Controller()
        