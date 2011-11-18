#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base class for settings/preferences.  Handles saving, loading, validating."""

import types

import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.widget import Entries
from gui.gtk.widget import SchedulerEntry
from gui.gtk.utils import GTKUtils

def make_entry(entryRange, entryValue):
  """Create a GTK element to handle input for a given entryRange.
  @param entryRange:  the possible values that the setting can have
  @type  entryRange:  settings range
                 these can be many different types.  They should probably be consolidated to a class.
  @param entryValue:  the starting value for the Entry
  @type  entryValue:  unknown
  @return:       Entry"""
  entry = None
  if type(entryRange) == types.TupleType and type(entryRange[0]) != types.StringType:
    if type(entryRange[0]) == types.FloatType:
      entry = Entries.FloatEntry(entryRange)
    elif type(entryRange[0]) == types.IntType:
      entry = Entries.IntegerEntry(entryRange)
    else:
      raise Exception("Weird type for entryRange")
  elif type(entryRange) == types.TupleType and type(entryRange[0]) == types.StringType:
    entry = Entries.EnumEntry(entryRange)
  elif type(entryValue) == types.BooleanType:
    #create a simple text entry:
    entry = Entries.BoolEntry(entryRange)
  #default to text entry for special types that need validation
  elif type(entryRange) == types.StringType:
    if entryRange == "folder":
      entry = Entries.FolderEntry(entryRange)
    elif entryRange == "ip":
      entry = Entries.IPEntry(entryRange)
    elif entryRange in ("GB", "KBps"):
      entry = Entries.UnitEntry(entryRange)
    elif entryRange == "password":
      entry = Entries.PasswordEntry(entryRange)
    elif entryRange == "scheduler":
      entry = SchedulerEntry.SchedulerEntry(entryRange)
    elif entryRange == "anonymity level":
      entry = Entries.AnonymityEntry(entryRange)
    else:
      entry = Entries.StringEntry(entryRange)
  if not entry:
    raise Exception("Unknown range/value combination (%s, %s)" % (entryRange, entryValue))
  entry.set_value(entryValue)
  return entry

class SettingsDisplay():
  """Make a box containing entries for all of the settings in a specific category for a given application settings class"""
  #TODO:  make it possible to tab between each of these entries, auto-full-selecting the existing text
  def __init__(self, settings, category):
    """Create a GUI interface for setting all of our values.
    @param settings:  the Settings class that we should display
    @type  settings:  Applications.Settings
    @param category:  what subcategory of the settings should be shown in this box.
    @type  category:  str
    @return:          gtk.Box"""
    self.settings = settings
    self.category = category
    self.__entries = {}

    #create a nice table to put them in:
    settingsBox = gtk.VBox()
    for attr in settings.settings_to_save:
      if not attr in settings.categories[category]:
        continue
      #create the appropriate type of Entry:
      self.__entries[attr] = make_entry(settings.ranges[attr], getattr(settings, attr))
      #create some GUI elements to make the Entry presentable:
      box = self.__entries[attr].make_wrapper(settings.displayNames[attr], settings.helpStrings[attr])
      if settings.isVisible[attr]:
        box.show()
        sep = gtk.HSeparator()
        sep.show()
        #pack it into our box:
        settingsBox.pack_start(box, False, False, 10)
        settingsBox.pack_start(sep, False, False, 0)
    settingsBox.set_spacing(5)
    scrolled_window = GTKUtils.make_scroll_box(settingsBox)
    scrolled_window.set_size_request(-1, 300)
    scrolled_window.show()
    settingsBox.show()
    
    self._hide_error_labels()
    self.container = scrolled_window
    
  def clear_parent(self):
    """Remove our contianer from any gui that it is currently a part of"""
    if self.container.parent:
      self.container.parent.remove(self.container)
  
  def _hide_error_labels(self):
    """Hide all of the error labels for the given category.
    """
    for attr in self.settings.settings_to_save:
      if not attr in self.settings.categories[self.category]:
        continue
      self.__entries[attr].errorLabel.hide()
      
  def reset_defaults(self):
    """Reset all settings and Entry's to their default values.
    """
    for attr, entry in self.__entries.iteritems():
      val = self.settings.defaults[attr]
      self.settings.set_new_value(attr, val)
      entry.set_value(val)

  def clear(self):
    """Reset all Entry's to the existing setting values.
    """
    #reset all Entries to our values:
    for attr in self.settings.settings_to_save:
      if not attr in self.settings.categories[self.category]:
        continue
      self.__entries[attr].set_value(getattr(self.settings, attr))
  
  def apply(self, app):
    """Apply all changes, only if they are all valid.  
    @param app:  an instance of Application that the settings are being applied to 
    @type  app:  Application
    @return:          True on success, False on failure."""
    doApply = True
    somethingChanged = False
    #check if everything will apply cleanly:
    try:
      for attr, entry in self.__entries.iteritems():
        if not attr in self.settings.categories[self.category]:
          continue
        newVal = entry.get_value()
        oldVal = getattr(self.settings, attr)
        entry.errorLabel.hide()
        if newVal != oldVal:
          somethingChanged = True
          self.settings.set_new_value(attr, newVal)
    except Exception, error:
      doApply = False
      log_msg(repr(error), 3)
      entry.errorLabel.set_markup("<span color='red'>%s</span>" % (str(error)))
      entry.errorLabel.show()
    if not doApply:
      return False
    #if everything checked out, apply the changes:
    for attr, entry in self.__entries.iteritems():
      if not attr in self.settings.categories[self.category]:
        continue
      self.settings.set_new_value(attr, entry.get_value())
    if somethingChanged:
      if not self.settings.on_apply(app, self.category):
        log_msg("Failed to properly apply, not saving settings.")
    return True
    