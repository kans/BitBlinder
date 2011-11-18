#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Settings/preferences for each Application class.  Handles saving, loading, and presenting the GUI for changing settings."""

import re
import os
import types

from twisted.internet.abstract import isIPAddress
import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import Files
from common import Globals
from gui.gtk.widget import Entry
from gui.gtk.utils import GTKUtils
  
class StringEntry(Entry.Entry):
  """Accepts unicode strings"""
  def make_entry(self, entryRange):
    self.entry = gtk.Entry(0)
    self.range = entryRange
    return self.entry
  
  def set_value(self, val):
    assert isinstance(val, basestring), "must set to string of some sort"
    val = unicode(val)
    self.entry.set_text(val)
      
  def get_value(self):
    text = unicode(self.entry.get_text())
    if self.range:
      if not re.compile(self.range).match(text):
        raise Exception("Option is not of the form:  %s" % (self.range))
    return text
  
class IntegerEntry(Entry.Entry):
  def make_entry(self, entryRange):
    self.min = None
    self.max = None
    if entryRange != None:
      self.min = entryRange[0]
      self.max = entryRange[1]
    self.entry = gtk.SpinButton()
    self.entry.set_numeric(True)
    self.entry.set_wrap(False)
    self.entry.set_range(self.min, self.max)
    self.entry.set_snap_to_ticks(True)
    self.entry.set_digits(0)
    self.entry.set_increments(1, 10)
    return self.entry
  
  def set_value(self, val):
    try:
      val = int(val)
    except:
      pass
    assert type(val) == types.IntType, "must set to an Int"
    if self.min:
      if val < self.min or val > self.max:
        raise Exception("Value for settings entry is out of range:  %s not in [%s, %s]" % (val, self.min, self.max))
    self.entry.set_value(val)
      
  def get_value(self):
    newVal = int(self.entry.get_value())
    return newVal
  
class UnitEntry(IntegerEntry):
  def make_entry(self, entryRange):
    self.unitName = entryRange
    return IntegerEntry.make_entry(self, (0, 100000))
    
  def make_wrapper(self, nameString, helpString=None, helpSize="small"):
    vbox = IntegerEntry.make_wrapper(self, nameString, helpString, helpSize)
    #create a unit name label:
    unitLabel = gtk.Label("")
    unitLabel.set_markup("<span size='large' weight='bold'>%s</span>" % (self.unitName))
    self.hbox.pack_start(unitLabel, False, False, 0)
    return vbox
  
class FloatEntry(IntegerEntry):
  def make_entry(self, entryRange):
    IntegerEntry.make_entry(self, entryRange)
    self.entry.set_digits(3)
    self.entry.set_increments(0.1, 10.0)
    return self.entry
    
  def set_value(self, val):
    try:
      val = float(val)
    except:
      pass
    assert type(val) == types.FloatType, "must set to a Float"
    if self.min:
      if val < self.min or val > self.max:
        raise Exception("Value for settings entry is out of range:  %s not in [%s, %s]" % (val, self.min, self.max))
    self.entry.set_value(val)
      
  def get_value(self):
    newVal = float(self.entry.get_value())
    return newVal
  
class FolderEntry(Entry.Entry):
  def make_entry(self, entryRange):
    self.entry = gtk.Entry(20)
    def enter_cb(widget):
      GTKUtils.launch_file_selector(self.set_value, unicode(self.entry.get_text()))
    self.folderBox = gtk.HBox()
    button = gtk.Button("Browse...")
    button.connect('clicked', enter_cb)
    self.folderBox.pack_start(self.entry, False, False, 5)
    self.folderBox.pack_start(button, False, False, 5)
    return self.folderBox
  
  def get_gtk_element(self):
    return self.folderBox
  
  def set_value(self, val):
    val = unicode(val)
    if not Files.file_exists(val):
      try:
        os.makedirs(val)
      except Exception, error:
        log_msg("Could not make a dir: %s" % (error), 0)
    if len(val) > self.entry.get_max_length():
      self.entry.set_max_length(len(val) + 10)
    self.entry.set_text(val)
      
  def get_value(self):
    newVal = unicode(self.entry.get_text())
    if not Files.file_exists(newVal):
      os.makedirs(newVal)
    return newVal
  
class BoolEntry(Entry.Entry):
  def make_entry(self, entryRange):
    self.entry = gtk.CheckButton()
  
  def set_value(self, val):
    assert type(val) == types.BooleanType, "must set to a Boolean"
    self.entry.set_active(val)
      
  def get_value(self):
    return self.entry.get_active()
  
class EnumEntry(Entry.Entry):
  def __init__(self, entryRange):
    Entry.Entry.__init__(self, entryRange)
    self._changedValue = False
    self.userChangedFunc = None
    self.entry.connect("changed", self.on_toggled)
    
  def make_entry(self, entryRange):
    self.entry = gtk.combo_box_new_text()
    maxLen = 10
    for val in entryRange:
      self.entry.append_text(val)
      if len(val) > maxLen:
        maxLen = len(val)
    #self.entry.set_size_request(maxLen+5, -1)
    
  def on_toggled(self, widget):
    if self._changedValue:
      self._changedValue = False
    elif self.userChangedFunc:
      self.userChangedFunc(widget)
    
  def connect_user_changed(self, func):
    self.userChangedFunc = func
  
  def set_value(self, val):
    #try to find the value, hope that it's there:
    model = self.entry.get_model()
    for row in model:
      if model.get_value(row.iter, 0) == val:
        #make sure that this is a new row:
        cIter = self.entry.get_active_iter()
        if not cIter or model.get_value(cIter, 0) != val:
          self._changedValue = True
          self.entry.set_active_iter(row.iter)
        return
    raise Exception("Could not find %s in possibilities for option" % (val))
      
  def get_value(self):
    return self.entry.get_active_text()
    
class AnonymityEntry(EnumEntry):
  """values are 1 through 3, directly mappable to path length"""
  TEXT_TUPLE = ("1 (Fastest)", "2 (Normal)", "3 (Best Anonymity)")
  
  def make_entry(self, entryRange):
    return EnumEntry.make_entry(self, self.TEXT_TUPLE)
    
  def set_value(self, val):
    if val < 1 or val > len(self.TEXT_TUPLE):
      raise Exception("Bad value for AnonymityEntry: %s" % (val))
    EnumEntry.set_value(self, self.TEXT_TUPLE[val-1])
      
  def get_value(self):
    text = EnumEntry.get_value(self)
    val = None
    for i in range(0, len(self.TEXT_TUPLE)):
      if self.TEXT_TUPLE[i] == text:
        val = i
        break
    if val is None:
      raise Exception("Bad value for AnonymityEntry: %s" % (val))
    return val+1
  
class IPEntry(StringEntry):
  def get_value(self):
    val = self.entry.get_text()
    if val == "":
      return val
    if not isIPAddress(val):
      raise Exception("Must be a valid IPv4 address.")
    return val
  
class PasswordEntry(StringEntry):
  def make_entry(self, entryRange):
    StringEntry.make_entry(self, entryRange)
    self.entry.set_visibility(False)
