#!/usr/bin/python
# Copyright 2008-2009 Innominet
import time

from twisted.internet import reactor, threads

import BankUtil
from serverCommon import EventLogging

class BankEventLogger():
  """Used to aggregate very frequent events per user, then flush them to disk periodically"""
  def __init__(self, eventTypes, logName):
    #: mapping from events to their event classes:
    self._eventTypes = eventTypes
    #: used to track events, so they can be logged hourly, for better anonymity and performance
    self._reset_events()
    #open the logs:
    EventLogging.open_logs(logName)
    #schedule a flush of the logs for the end of the hour:
    self._schedule_next_flush()
    
  def _reset_events(self):
    """Just clear all events from memory"""
    self._events = {}
    for eventName in self._eventTypes.keys():
      self._events[eventName] = {}
                   
  def _schedule_next_flush(self):
    """Figure out when the next flush should happen, and schedule the event with the reactor"""
    #time until the hour rolls over:
    vals = time.localtime()
    timeLeft = 60*(60-vals[4]) - vals[5]
    timeLeft += 30
    ##DEBUG:
    #timeLeft = 30
    self._next_flush_event = reactor.callLater(timeLeft, self._flush_event_logs)

  def aggregate_event(self, collectionName, key, amount):
    """Updates statistics in memory.  They get pushed to disk periodically"""
    collection = self._events.get(collectionName)
    val = collection.get(key)
    if not val:
      val = 0
    val += amount
    collection[key] = val
    
  def on_shutdown(self):
    """Should be called when the program wants to shut down, so that we can flush any existing events
    NOTE:  this is synchronous because there is not necessarily a reactor anymore"""
    #cancel any existing update event:
    if self._next_flush_event and self._next_flush_event.active():
      self._next_flush_event.cancel()
    #and do a final flush:
    self._flush_thread(self._events)
  
  def _flush_thread(self, recentEvents):
    """Log an event for each message type and user, essentially"""
    for collectionName, events in recentEvents.iteritems():
      eventType = self._eventTypes.get(collectionName)
      for key, value in events.iteritems():
        EventLogging.save_event(eventType(source=key, amount=value))

  def _flush_event_logs(self):
    """Save all aggregated events to the disk"""
    #reset the current logs so the program can continue without us
    recentEvents = self._events
    self._reset_events()
    #in a separate thread, push each of the events to disk:
    d = threads.deferToThread(self._flush_thread, recentEvents)
    d.addErrback(BankUtil.err)
    #and schedule this thread to run again in the future:
    self._schedule_next_flush()
    
