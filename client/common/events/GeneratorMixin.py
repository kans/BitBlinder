#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Defines GeneratorMixin"""

import types

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class GeneratorMixin:
  """A mixin to add the ability to generate events that other classes can listen to"""
  def __init__(self):
    #: a mapping to the list of handlers for each event
    self._eventListenerMapping = {}
    #: a set of event names that are acceptable.  Prevents name conflicts from inherited classes
    self._knownEventNames = set()
    
  def _add_events(self, *args):
    """Define all events that this class will ever generate.  Can be called
    multiple times (presumably by parent and child classes.)
    Do not pass a list, simply pass all event names as strings."""
    for eventName in args:
      assert eventName not in self._knownEventNames, \
        "Tried to add %s, but it was already being handled!" % (eventName)
      assert type(eventName) is types.StringType, \
        "Event names must be strings, not %s" % (type(eventName))
      self._knownEventNames.add(eventName)
      
  def _trigger_event(self, eventName, *args, **kwargs):
    """deal with an event--call all handlers"""
    assert eventName in self._knownEventNames, \
      "Tried to trigger an unknown event (%s)" % (eventName)
    if eventName not in self._eventListenerMapping:
      return
    handlers = self._eventListenerMapping[eventName]
    for handler in handlers:
      try:
        handler(self, *args, **kwargs)
      except Exception, error:
        log_ex(error, "Failure while handling event %s on %s" % (eventName, self))
  
  def add_event_handler(self, eventName, handler):
    """register a new handler for an event"""
    assert eventName in self._knownEventNames, \
      "Tried to listen for an unknown event (%s) with handler %s" % (eventName, handler)
    if eventName not in self._eventListenerMapping:
      self._eventListenerMapping[eventName] = set()
    self._eventListenerMapping[eventName].add(handler)
    
  def remove_event_handler(self, eventName, handler):
    """unregister a handler"""
    assert eventName in self._knownEventNames, \
      "Tried to remove handler %s for unknown event %s" % (handler, eventName)
    assert eventName in self._eventListenerMapping, \
      "Tried to remove handler %s for event %s on %s, but there were no handlers at all" % (handler, eventName, self)
    assert handler in self._eventListenerMapping[eventName], \
      "Tried to remove handler %s for event %s on %s, but it was not registered" % (handler, eventName, self)
    self._eventListenerMapping[eventName].remove(handler)
  