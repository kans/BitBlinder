#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base class for user inputs of various types"""

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import GTKUtils
  
class Entry():
  """Class to make a uniform interface for validated, typed input."""
  def __init__(self, entryRange):
    #: a handle on the larger box if we've made one in make_wrapper
    self.hbox = None
    #: a handle on the error label if we've made one in make_wrapper
    self.errorLabel = None
    #: the GTK object that we are wrapping
    self.entry = None
    #actually make the entry (subclass must provide this method)
    self.make_entry(entryRange)
    assert self.entry != None, "make_entry MUST assign self.entry!"
    
  def get_gtk_element(self):
    return self.entry
  
  def make_entry(self, entryRange):
    raise NotImplementedError()
  
  def set_sensitive(self, val):
    self.entry.set_sensitive(val)
  
  def set_value(self, val):
    raise NotImplementedError()
      
  def get_value(self):
    raise NotImplementedError()
  
  def make_wrapper(self, nameString, helpString=None, helpSize="small"):
    vbox = gtk.VBox()
    self.hbox = gtk.HBox()
    #create a name label:
    nameLabel = GTKUtils.make_text("<span size='large' weight='bold'>%s</span>" % (nameString))
    self.hbox.pack_start(nameLabel, True, True, 5)
    #add the actual entry
    self.hbox.pack_start(self.get_gtk_element(), False, False, 5)
    vbox.pack_start(self.hbox, True, True, 0)
    #create a help label:
    if helpString:
      helpLabel = GTKUtils.make_text("<span size='%s'>%s</span>" % (helpSize, helpString))
      align = gtk.Alignment(xalign=0.0, yalign=0.5, xscale=1.0, yscale=1.0)
      align.add(helpLabel)
      align.set_padding(15, 0, 0, 0)
      vbox.pack_start(align, True, True, 0)
    #create the error label
    self.errorLabel = GTKUtils.make_text("")
    vbox.pack_start(self.errorLabel, True, True, 0)
    #glue
    vbox.set_spacing(0)
    vbox.show_all()
    self.errorLabel.hide()
    return vbox
    