#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Defines ListenerMixin"""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

#: our classes that are listening for our custom events
GLOBAL_EVENT_LISTENERS = {}

def throw_event(eventName, *args, **kwargs):
  """Custom event handling.  Inform all interested listeners about the event.
  @param eventName:  the event that just occurred
  @type  eventName:  str"""
  if GLOBAL_EVENT_LISTENERS.has_key(eventName):
    for x in GLOBAL_EVENT_LISTENERS[eventName]:
      try:
        func = getattr(x, "on_" + eventName)
        if func:
          func(*args, **kwargs)
      except Exception, e:
        log_ex(e, "%s failed while handling %s event" % (x, eventName))
        
class GlobalEventMixin:
  """An interface to handle general events from BitBlinder"""
  def catch_event(self, eventName):
    """Register this object as a listener for the event
    @param eventName:  what event to listen for
    @type  eventName:  str"""
    if not GLOBAL_EVENT_LISTENERS.has_key(eventName):
      GLOBAL_EVENT_LISTENERS[eventName] = set()
    GLOBAL_EVENT_LISTENERS[eventName].add(self)