#!/usr/bin/python

import time
import sys
import pygtk
pygtk.require('2.0')
import gtk, gobject

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class RegistryDialog():
  def __init__(self, programName, root, fileTypeName, cb):
    buttons = (gtk.STOCK_YES, gtk.RESPONSE_YES, gtk.STOCK_NO, gtk.RESPONSE_NO)
    dia = gtk.Dialog("Handle %s files?" % (fileTypeName),
      root,
      gtk.DIALOG_DESTROY_WITH_PARENT,
      buttons)
    
    #A text entry telling the user what to do:
    self.label = gtk.Label("Make %s the default program for %s files?" % (programName, fileTypeName))
    self.label.set_selectable(True)
    #self.label.set_size_request(200,-1)
    self.label.set_line_wrap(True)
    
    #if we should always check:
    self.checkAtStartup = gtk.CheckButton("Always check at startup.")

    dia.vbox.pack_start(self.label, True, True, 20)
    dia.vbox.pack_start(self.checkAtStartup, True, True, 10)

    self.checkAtStartup.set_active(True)
    
    dia.show_all()

    #connect the handler:
    dia.connect("response", self.on_response, cb)
    self.dia = dia
    
  #handle the result of the dialog:
  def on_response(self, dialog, response_id, cb):
    if (response_id == gtk.RESPONSE_YES):
      response = "yes"
    else:
      response = "no"
    cb(response, self.checkAtStartup.get_active())
    self.dia.destroy()
    