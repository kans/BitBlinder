#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Wrappers for scheduling events on the reactor"""

from common import Globals

class RecurringEvent():
  """Class to make a nice event class for recurring events, so they can be cancelled in the correct way"""
  def __init__(self):
    self.call = None
    
  def active(self):
    return self.call.active()
  
  def cancel(self):
    return self.call.cancel()

def schedule_once(time, fn, *args, **kwargs):
  """Call the function (with arguments) at some time in the future (given by time)"""
  return Globals.reactor.callLater(time, fn, *args, **kwargs)
    
def schedule_repeat(time, fn, *args, **kwargs):
  """Repeatedly call the function every (time) seconds, until it doesnt return True
  At that point, stop rescheduling it."""
  args = list(args)
  def newFunc(time, fn, event, *args, **kwargs):
    args = list(args)
    if fn(*args, **kwargs):
      args.insert(0, event)
      args.insert(0, fn)
      args.insert(0, time)
      event.call = Globals.reactor.callLater(time, newFunc, *args, **kwargs)
  event = RecurringEvent()
  args.insert(0, event)
  args.insert(0, fn)
  args.insert(0, time)
  event.call = Globals.reactor.callLater(time, newFunc, *args, **kwargs)
  return event
 
