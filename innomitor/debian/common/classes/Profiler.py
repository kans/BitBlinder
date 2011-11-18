#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Application class wrapper for Tor"""

import cProfile

from common.events import GeneratorMixin

_instance = None
def get():
  return _instance
  
def start():
  global _instance
  if not _instance:
    _instance = Profiler()
    
class Profiler(cProfile.Profile, GeneratorMixin.GeneratorMixin):
  def __init__(self, fileName="temp.stats"):
    cProfile.Profile.__init__(self)
    GeneratorMixin.GeneratorMixin.__init__(self)
    self.isProfiling = False
    self.fileName = fileName
    self._add_events("started", "stopped")
    
  def start(self):
    if not self.isProfiling:
      self.isProfiling = True
      self.clear()
      self.enable()
      self._trigger_event("started")
    
  def stop(self):
    if self.isProfiling:
      self.isProfiling = False
      self.disable()
      self.dump_stats(self.fileName)
      self._trigger_event("stopped")
