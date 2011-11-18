#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Defines ListenerMixin"""

import copy

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class ListenerMixin:
  """A mixin for any class that wishes to listen to events from GeneratorMixins"""
  
  def __init__(self):
    #NOTE:  event tuples (name, sourceObject, handler) used to be stored in a simple 
    #class, but I stopped that, because it made multiple Event objects look different 
    #when we wanted them to be the same (should not be able to add the same combination 
    #of sourceObject, event, and handler more than once to the set, that's why it's a set.)
    #: the set of events we are listening for
    self._eventSet = set()
  
  def _start_listening_for_event(self, eventName, eventObj, handler):
    """register yourself for an event"""
    self._eventSet.add((eventName, eventObj, handler))
    eventObj.add_event_handler(eventName, handler)
    
  def _stop_listening_for_event(self, eventName, eventObj):
    """unregister yourself for an event"""
    #find all of the handlers for eventName on eventObj
    toRemove = set()
    for event in self._eventSet:
      if event[0] == eventName and event[1] == eventObj:
        toRemove.add(event)
    #actually remove the handlers
    for event in toRemove:
      self._eventSet.remove(event)
      #tell the object that we don't care about that event anymore
      event[1].remove_event_handler(event[0], event[2])
  
  def _cleanup(self):
    """unregister yourself from any events you are listening for"""
    toRemove = copy.copy(self._eventSet)
    for event in toRemove:
      event[1].remove_event_handler(event[0], event[2])
    self._eventSet = set()
    
