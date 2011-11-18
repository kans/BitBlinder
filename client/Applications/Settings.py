#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Settings/preferences for each Application class.  Handles saving, loading, and validating."""

import os

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import SettingsFile

class Settings(SettingsFile.PickledSettings):
  """A very basic class for setting/getting program-wide settings.  Hopefully we
  can replace Globals with it."""
  def __init__(self):
    SettingsFile.PickledSettings.__init__(self)
    self.fileName = None

  def save(self, fileName=None):
    """Save all settings to the appropriate file.
    @param fileName:  what file to save to.  If None, save to the last file that we loaded/saved from
    @type  fileName:  file or None"""
    if not fileName:
      fileName = self.fileName
    assert fileName != None, "Must set the Settings object filename before calling save, or pass it a file!"
    SettingsFile.pickle(self, fileName)
  
  def load(self, fileName):
    """Create a Settings object by loading a file.
    @param fileName:  what file to load the settings from.
    @type  fileName:  file
    @returns:  True if file loaded properly, False otherwise"""
    #check that the file exists
    if not os.path.exists(fileName) or not os.path.isfile(fileName):
      log_msg("Could not load settings file because it does not exist:  %s" % (fileName), 1)
      return False
    SettingsFile.unpickle(self, fileName)
    return True
    
  def reset_defaults(self):
    """Reset all settings to their default values.
    """
    for attr, val in self.defaults.iteritems():
      self.set_new_value(attr, val)
      
  def set_new_value(self, attr, newVal):
    """Set the new value for an attribute.
    @param attr:   the Settings attribute corresponding to be set
    @type  attr:   str
    @param newVal: the new value to use
    """
    #see what type the setting was before:
    val = getattr(self, attr)
    #ie, if this is a non-None type
    isNormalType = type(val) != type(None) and type(newVal) != type(None)
    #are the new and old types different?
    typeIsChanging = type(val) != type(newVal)
    #if the type is changing, and neither is a None
    if isNormalType and typeIsChanging:
      #also ignore strings changing from Unicode and back
      if not isinstance(val, basestring) or not isinstance(newVal, basestring):
        raise Exception("%s is not a %s." % (newVal, type(val)))
    setattr(self, attr, newVal)
  
  def on_loaded(self):
    """Called when this object is loaded from a file for initialization, rather
    than going through __init__"""
    pass
  
  def on_apply(self, app, category):
    """Must be overridden by subclasses to validate their own settings and apply them
    @param app:  an instance of Application that the settings are being applied to 
    @type  app:  Application
    @param category:  the category to apply
    @type  category:  str
    @return:          True on success, False on failure."""
    return True
