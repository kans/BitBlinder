#!/usr/bin/python

"""
IMPORTANT NOTE:  uses eval(), DO NOT USE for any data you dont trust completely.
"""
import re
import types
import os

from common.contrib import configobj
import twisted
from twisted.internet.abstract import isIPAddress

from gui import GUIController
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class PickledSettings(object):
  def add_attribute(self, name, value, range=None, displayName=None, help=None, category="", isVisible=True):
    #TODO: remove this and move to the format in Tor.py
    setattr(self, name, value)
    if not hasattr(self, "settings_to_save"):
      self.settings_to_save = set()
      self.ranges = {}
      self.helpStrings = {}
      self.displayNames = {}
      self.defaults = {}
      self.categories = {}
      self.isVisible = {}
    if not name in self.settings_to_save:
      if displayName and range != None:
        self.settings_to_save.add(name)
        self.defaults[name] = value
        self.isVisible[name] = isVisible
        if not self.categories.has_key(category):
          self.categories[category] = set()
        self.categories[category].add(name)
      else:
        #loading an old attribute that is no longer in the object:
        return
    if range != None:
      self.ranges[name] = range
    if help != None:
      self.helpStrings[name] = help
    if displayName:
      self.displayNames[name] = displayName
    return getattr(self, name)

_isCallable = lambda o: hasattr(o, "__call__")

#pickling 
def pickle(obj, fileName):    
  config = configobj.ConfigObj()
  config.filename = fileName
  config.encoding = 'utf-8'

  for name in obj.settings_to_save: 
    val = getattr(obj, name)
    #do not pickle member functions
    if _isCallable(val): continue
    config[name] = val
  config.write()

#unpickling 
def unpickle(obj, fileName):
  """main unpickle function"""
  config = configobj.ConfigObj(fileName, encoding='utf-8')
  
  #generate the config spec:  
  for name in config.keys():
    #dont load settings that no longer exist
    if not obj.ranges.has_key(name):
      continue
    range = obj.ranges[name]
    defaultVal = obj.defaults[name]
    loadedVal = config[name]
    try:
      if type(range) == types.TupleType and type(range[0]) != types.StringType:
        if type(range[0]) == types.FloatType:
          loadedVal = float(loadedVal)
          assert loadedVal <= range[1], "%s not in range %s" % (loadedVal, range)
          assert loadedVal >= range[0], "%s not in range %s" % (loadedVal, range)
        elif type(range[0]) == types.IntType:
          loadedVal = int(loadedVal)
          assert loadedVal <= range[1], "%s not in range %s" % (loadedVal, range)
          assert loadedVal >= range[0], "%s not in range %s" % (loadedVal, range)
        else:
          raise Exception("Weird type for range: %s" % (range))
      elif type(range) == types.TupleType and type(range[0]) == types.StringType:
        assert loadedVal in range, "%s not in range %s" % (loadedVal, range)
      elif type(defaultVal) == types.BooleanType:
        if loadedVal.lower() in ("1", "true", "t", "y", "yes", "on"):
          loadedVal = True
        else:
          loadedVal = False
      #default to text entry for special types that need validation
      elif type(range) == types.StringType:
        if range == "folder":
          assert os.path.isdir(loadedVal), "%s is not a valid directory" % (loadedVal)
        elif range == "ip":
          if loadedVal:
            assert isIPAddress(loadedVal), "%s is not a valid ip address" % (loadedVal)
        elif range in ("GB", "KBps"):
          loadedVal = int(loadedVal)
        elif range == "password":
          pass
        elif range == "scheduler":
          pass
        elif range == "anonymity level":
          loadedVal = int(loadedVal)
          assert loadedVal in (1,2,3), "anonymity value not in range (1,3)"
        else:
          regex = re.compile(range)
          assert regex.match(loadedVal), "settings string (%s) does not match expression (%s)" % (loadedVal, range)
      else:
        raise Exception("Unknown range/value combination (%s, %s)" % (range, defaultVal))
    except Exception, e:
      log_msg("Bad option value (%s) for option %s" % (e, name), 0)
      GUIController.get().show_msgbox("Bad option value (%s) for option %s" % (e, name))
    setattr(obj, name, loadedVal)
    
