#!/usr/bin/python
#Copyright 2009 InnomiNet
"""Allow direct manipulation of the Tor control connection"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.events import GlobalEvents
from core.tor import TorCtl
from core import ProgramState
from core import ClientUtil

class Console(GlobalEvents.GlobalEventMixin):
  def __init__(self, torApp):
    self.torApp = torApp
    ClientUtil.add_updater(self)
    self.catch_event("tor_ready")
    self.textview = gtk.TextView(buffer=None)
    self.buffer = self.textview.get_buffer()
    self.textview.set_editable(False)  
    self.textview.set_cursor_visible(False)
    self.textview.set_wrap_mode(gtk.WRAP_WORD)
    
    self.textEventList = self.textview
    self.textEventList.show()
    # create a new scrolled window.
    scrolled_window = gtk.ScrolledWindow()
    scrolled_window.set_border_width(10)
    scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    #scrolled_window.set_size_request(300, 350)
    scrolled_window.add_with_viewport(self.textEventList)
    scrolled_window.show()
    
    self.entry = gtk.Entry(100)
    self.entry.connect("activate", self.enter_callback, self.entry)
    self.entry.show()

    vbox = gtk.VBox()
    vbox.pack_start(scrolled_window, True, True, 10)
    vbox.pack_end(self.entry, False, False)
    
    self.label = gtk.Label("Console")
    self.container = vbox
    
  def enter_callback(self, widget, entry):
    entry_text = entry.get_text()
    entry.set_text("")
    self.torApp.conn.sendAndRecv(entry_text + "\r\n")
    
  def on_tor_ready(self):
    #whether we should start showing anything in the Console:
    if ProgramState.DEBUG:
      TorCtl.trackingConsoleChanges = True
    
  #called to append text- the text is dumped at the end of the current text
  #according to the enditer
  def on_update(self):
    #Update the console with any new text we got from the controller:
    line = TorCtl.console_data_string
    TorCtl.console_data_string = ''
    #update the GUI if necessary:
    if TorCtl.trackingConsoleChanges and line:
      enditer = self.buffer.get_end_iter()
      self.buffer.insert(enditer, line)
    