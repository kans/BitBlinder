#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Python module for top level window widgets"""

import time
import os
import sys
import pygtk
import gtk, gobject
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.events import GlobalEvents
from common.events import ListenerMixin
from common.events import GeneratorMixin
from gui.utils import Strings
from gui import GUIController
from gui.gtk.utils import GTKUtils
from gui.gtk.dialog import SettingsDialog
from gui.gtk.widget import StatusIcon
from Applications import BitBlinder

class Window(gtk.Window, GlobalEvents.GlobalEventMixin, ListenerMixin.ListenerMixin, GeneratorMixin.GeneratorMixin):
  """a top level window"""
  def __init__(self, title,  app):
    """A window that can sets the title, icon, and statusicon. 
    @param app: application associated with the window
    """
    gtk.Window.__init__(self, type=gtk.WINDOW_TOPLEVEL)
    ListenerMixin.ListenerMixin.__init__(self)
    GeneratorMixin.GeneratorMixin.__init__(self)
    self.app = app
    self.oldX = None
    self.oldY = None
    self.settingsDialog = None
    self.set_title(title)
    self._add_events("shown", "hidden")

    #each top window gets its own settings screen
    self.settingsDialog = None
#    self.set_icon_from_file(os.path.realpath(os.path.join(u'data', u'bb_logo.png')))

    self.connect("delete_event", self.delete_cb)
    
    #not really, but gtk anounces the state at start up by emiting a signal which we want to ignore
    self.isMinimized = True
    
  def refit(self):
    self.resize(*self.size_request())
    
  def is_visible(self):
    return not self.isMinimized

  def __set_minimized(self, val):
    self.isMinimized = val
    if self.isMinimized:
      self.iconify()
      self.hide()
      self._trigger_event("hidden")
    else:
      self.deiconify()
      self.show()
      self._trigger_event("shown")
      
  def toggle_window_state(self, widget=None):
    """changes the window from iconified to deiconified"""
    log_msg("state toggle %s" % (self.isMinimized), 4, "gui")
    if self.isMinimized:
      self.start()
    else:
      self.stop()
    
  def start(self):
    self.__set_minimized(False)
    if self.window:
      self.window.raise_()
    
  def stop(self):
    self.__set_minimized(True)
    
  def _start_cb(self, widget=None):
    if self.isMinimized:
      self.start()

#  def go(self):
#    self.present()
#    self.window.focus()
#    self.window.raise_()
#    
#    import win32ui
#    import win32gui
#    title = self.get_title()
#    handle = win32gui.FindWindowEx(None, None, None, title)
#    mywin = win32ui.CreateWindowFromHandle(handle)
#    mywin.SetForegroundWindow()
    
  def delete_cb(self, widget=None, event=None, Data=None):
    """delete event kills our root window"""
    self.__set_minimized(True)
    return True
    
