#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Make a settings screen with only a few settings on it"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.events import GlobalEvents
from gui.gtk.display import SettingsDisplay

HELP_TEXT_SIZE = "large"

class MiniSettingsDialog(GlobalEvents.GlobalEventMixin):
  def __init__(self, responseHandler=None, root=None):
    #make the dialog:
    flags = 0
    if root:
      flags = gtk.DIALOG_DESTROY_WITH_PARENT
    self.dia = gtk.Dialog("Settings", root, flags, None)
    
    self.shouldSave = True
    self.variables = []
    #connect the handlers:
    self.responseHandler = responseHandler
    self.dia.connect("response", self.on_response)
    #add the buttons:
    self.prevButton = self.dia.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
    self.nextButton = self.dia.add_button(gtk.STOCK_OK, gtk.RESPONSE_OK)
    #glue:
    self.vbox = gtk.VBox()
    self.dia.vbox.pack_start(self.vbox, True, True, 10)
    #create whatever settings we're supposed to have:
    self.create_box()
    self.dia.vbox.show_all()
    #and show the dialog:
    self.dia.show()
    
  def add_variable(self, varName, settingsObj, app, category, box=None, ignoreHBar=None):
    if not box:
      box = self.vbox
    if len(self.variables) > 0 and not ignoreHBar:
      box.pack_start(gtk.HSeparator(), False, False, 0)
    entry = SettingsDisplay.make_entry(settingsObj.ranges[varName], getattr(settingsObj, varName))
    box.pack_start(entry.make_wrapper(settingsObj.displayNames[varName], settingsObj.helpStrings[varName], HELP_TEXT_SIZE), False, False, 5)
    self.variables.append([varName, settingsObj, entry, app, category])
    return entry
    
  def create_box(self):
    """Subclasses should override this method to populate the dialog with whatever settings they care about"""
    raise NotImplementedError()
    
  def apply_settings(self):
    for name, settingsObj, entry, app, category in self.variables:
      setattr(settingsObj, name, entry.get_value())
      if self.shouldSave:
        if not settingsObj.on_apply(app, category):
          raise Exception("Should not be possible to enter invalid input in minisettings!")
        settingsObj.save()
        
  def show(self):
    #have to reset all the values:
    for name, settingsObj, entry, app, category in self.variables:
      entry.set_value(getattr(settingsObj, name))
    return self.dia.show()
    
  def hide(self):
    return self.dia.hide()
    
  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    success = False
    if response_id == gtk.RESPONSE_OK:
      self.apply_settings()
      success = True
    elif response_id in (gtk.RESPONSE_CANCEL, gtk.RESPONSE_DELETE_EVENT):
      pass
    else:
      raise Exception("Got unknown response ID:  %s" % (response_id))
    if self.responseHandler:
      self.responseHandler(success)
    self.dia.destroy()
    return True