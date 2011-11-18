#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Ask the user if they want to update right now"""

import pygtk
import gtk

from gui import GUIController
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class UpdateDialog():
  def __init__(self, newVersion, prompt, cb):
    self.newVersion = newVersion
    self.cb = cb
    buttons = (gtk.STOCK_YES, gtk.RESPONSE_YES, gtk.STOCK_NO, gtk.RESPONSE_NO)
    dia = gtk.Dialog("Update?", None, 0, buttons)
    #A text entry telling the user what to do:
    self.label = gtk.Label(prompt)
    self.label.set_line_wrap(True)
    #add to gui
    dia.vbox.pack_start(self.label, True, True, 20)
    #connect the handler:
    dia.connect("response", self.on_response)
    self.dia = dia
    #start the dialog
    dia.show_all()
    
  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    if (response_id == gtk.RESPONSE_YES):
      self.cb(self.newVersion)
    else:
      log_msg("User elected not to update.", 4)
    GUIController.get().updateDialog = None
    self.dia.destroy()
    