#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Represents settings that apply to all applications"""

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from Applications import Settings

_instance = None
def get():
  return _instance
  
def start():
  global _instance
  if not _instance:
    _instance = CoreSettings()

class CoreApplication:
  def __init__(self):
    self.name = "CoreSettings"
    
  def get_settings_name(self):
    return self.settings.settingsName

class CoreSettings(Settings.Settings):
  #: name of the xml settings file 
  defaultFile = "commonSettings.ini"
  #: Name in settings dialog
  DISPLAY_NAME = "Global"
  
  def __init__(self):
    self.app = CoreApplication()
    self.app.settings = self
    self.settingsName = self.DISPLAY_NAME
    self.usePsyco = self.add_attribute("usePsyco", False, "bool",  "Use optimizations?", "Uses the python-psyco package to try making BitBlinder faster.  Might be unstable or cause memory leaks.")
    self.askedAboutBugReports = self.add_attribute("askedAboutBugReports", False, "bool",  "Have you been asked about bug reporting?", "", isVisible=False)
    self.askAboutRelay = self.add_attribute("askAboutRelay", True, "bool",  "Do you want us to keep asking you about setting up a relay?", "", isVisible=False)
    self.sendBugReports = self.add_attribute("sendBugReports", True, "bool",  "Whether to submit bug reports or not", "Please keep this checked so that we can automatically learn about any errors that you run in to!  We have anonymized the reports, so no worries.")
    return
    
