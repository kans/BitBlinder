#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Show a nice set of windows for server settings"""

import gtk
from twisted.internet import defer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common import Globals
from core import ProgramState
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import WrapLabel
from gui.gtk.dialog import MiniSettingsDialog
from Applications import BitBlinder
from Applications import Tor

class ServerSettingsDialog(MiniSettingsDialog.MiniSettingsDialog):
  def __init__(self):
    self._boxes = []
    self._curBoxIdx = 0
    MiniSettingsDialog.MiniSettingsDialog.__init__(self, None, None)
    self.dialogDeferred = defer.Deferred()
    
  def set_current_page(self):
    prevLabel = self.prevButton.child.child.get_children()[1]
    nextLabel = self.nextButton.child.child.get_children()[1]
    prevLabel.set_text("Prev")
    nextLabel.set_text("Next")
    if self._first_page_selected():
      prevLabel.set_text("Cancel")
    elif self._last_page_selected():
      nextLabel.set_text("Done")
    children = self._mainBox.get_children()
    for c in children:
      self._mainBox.remove(c)
    self._mainBox.pack_start(self._boxes[self._curBoxIdx], True, True, 0)
    self._mainBox.show_all()
    self.dia.set_title("Step %s of %s" % (self._curBoxIdx+1, len(self._boxes)))
      
  def _last_page_selected(self):
    return self._curBoxIdx >= len(self._boxes)-1
    
  def _first_page_selected(self):
    return self._curBoxIdx <= 0
    
  def _cancel_response(self):
    if self.dialogDeferred:
      self.dialogDeferred.callback(False)
      self.dialogDeferred = None
      self.dia.destroy()
    
  def _ok_response(self):
    self.apply_settings()
    if self.dialogDeferred:
      self.dialogDeferred.callback(True)
      self.dialogDeferred = None
      self.dia.destroy()

  def on_response(self, dialog, response_id):
    if response_id == gtk.RESPONSE_DELETE_EVENT:
      self._cancel_response()
    #if this was the last tab and we hit next:
    elif response_id == gtk.RESPONSE_OK and self._last_page_selected():
      self._ok_response()
    #if this was the first tab and we hit prev:
    elif response_id == gtk.RESPONSE_CANCEL and self._first_page_selected():
      self._cancel_response()
    #otherwise just advance to the next tab:
    else:
      if response_id == gtk.RESPONSE_OK:
        self._curBoxIdx += 1
      else:
        self._curBoxIdx -= 1
      self.set_current_page()
      return True
    
  def create_box(self):
    #create each of the pages:
    self._mainBox = gtk.HBox()
    self.vbox.pack_start(self._mainBox, True, True, 0)
    BORDER_WIDTH = 10
    def add_var(name, box, ignoreHBar=None):
      return self.add_variable(name, Tor.get().settings, Tor.get(), "", box, ignoreHBar)
    #general settings page:
    vbox = gtk.VBox()
    add_var("orPort", vbox)
    add_var("dirPort", vbox)
    add_var("dhtPort", vbox)
    vbox.set_border_width(BORDER_WIDTH)
    #windows settings, if necessary
    if System.IS_WINDOWS:
      startOnBootEntry = self.add_variable("startBitBlinderOnBoot", BitBlinder.get().settings, BitBlinder.get(), "", vbox)
      #NOTE:  change the default to starting on bootup if we're a server now
      if not Tor.get().settings.wasRelay:
        startOnBootEntry.set_value(True)
      self.add_variable("halfOpenConnections", BitBlinder.get().settings, BitBlinder.get(), "", vbox)
    self._boxes.append(vbox)
    #exit traffic page:
    vbox = gtk.VBox()
    vbox.set_border_width(BORDER_WIDTH)
    exitTypeEntry = add_var("exitType", vbox, True)
    exitTypeEntry.set_value("Both")
    vbox.pack_start(GTKUtils.make_html_link("Learn more about exit traffic", "%s/overview/" % (ProgramState.Conf.BASE_HTTP)), False, False, 2)
    self._boxes.append(vbox)
    #bandwidth page:
    vbox = gtk.VBox()
    vbox.set_border_width(BORDER_WIDTH)
    label = WrapLabel.WrapLabel("")
    label.set_markup("""<span size='large' weight='bold'>You should run BitBlinder in the background to accumulate credits.
</span>
""")
    vbox.pack_start(label, False, False, 0)
#    vbox.pack_start(gtk.HSeparator(), False, False, 0)
    add_var("monthlyCap", vbox)
    add_var("bwRate", vbox)
    add_var("bwSchedule", vbox)
    self._boxes.append(vbox)
    self._mainBox.set_size_request(600, -1)
    self.set_current_page()
    
