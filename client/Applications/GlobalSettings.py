#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Represents settings that apply to all users"""

import os

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from core import ProgramState
from Applications import Settings

_instance = None
def get():
  return _instance
    
def load():
  global _instance
  #load a global config that said whether to store the last user that logged in (and his password)
  settingsFile = os.path.join(Globals.USER_DATA_DIR, "globals.ini")
  if _instance is None:
    _instance = GlobalSettings()
  _instance.load(settingsFile)
  _instance.fileName = settingsFile
  return _instance

class GlobalApplication:
  def __init__(self):
    self.name = "GlobalSettings"
    
  def get_settings_name(self):
    return self.settings.settingsName
    
class GlobalSettings(Settings.Settings):
  DISPLAY_NAME = "General"
  """Some settings that apply to all users"""
  def __init__(self):
    """Set the default values of all your settings."""
    self.app = GlobalApplication()
    self.app.settings = self
    self.settingsName = self.DISPLAY_NAME
    self.username = self.add_attribute("username", "", "", "User Name", "Your username, registered on %s/" % (ProgramState.Conf.BASE_HTTP))
    self.password = self.add_attribute("password", "", "", "Password", "Your password, registered on %s/" % (ProgramState.Conf.BASE_HTTP))
    self.save_password = self.add_attribute("save_password", False, "bool", "Save Password?", "Whether to store your password on the hard drive.\nWARNING!  This is not safe if other people have access to your computer!")
    self.promptAboutQuit = self.add_attribute("promptAboutQuit", True, "bool", "Prompt before exiting?", "", isVisible=False)
    
