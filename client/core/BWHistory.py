#!/usr/bin/python

"""Parent class for all classes that measure instantaneous bandwidth"""

import time

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

#: Total number of past values to store.  (thus we're storing bw info from the past minute)
MAX_VALUES = 60
#: a list of all BWHistory objects:
BW_UPDATERS = set()
#: number of intervals to average over to get the instantaneous bandwidth
INSTANT_BW_SMOOTH = 5

def update_all():
  """Update all BWHistory objects at once (once per interval.)"""
  try:
    toRemove = []
    for i in BW_UPDATERS:
      if not i.update_bw_stats():
        i._noUpdateTicks += 1
      #if the whole history has been zeroed out, we can stop updating every tick:
      if i._noUpdateTicks > MAX_VALUES:
        toRemove.append(i)
    #because we cant modify the set while iterating
    for i in toRemove:
      BW_UPDATERS.remove(i)
  except Exception, error:
    log_ex(error, "Error while updating bandwidths")
  return True

class BWHistory:
  """Represents the bw values over the past few intervals.  All the
  implementing class has to do is call handle_bw_event whenever a bandwidth
  event occurs (in EventHandler).  This class takes care of the automatic
  updating of values every INTERVAL (currently one second)"""
  
  def __init__(self):
    """Initialize the history with a bunch of zeroes, this way we can always
    assume that there are exactly MAX_VALUES values in the values list."""
    #: data read during each second.  [0]
    self.bytesRead = [0] * MAX_VALUES
    #: data written during each second
    self.bytesWritten = [0] * MAX_VALUES
    #: total data read over the lifetime of the object
    self.totalRead = 0
    #: total written read over the lifetime of the object
    self.totalWritten = 0
    #: time at which the object was created (useful for calculating lifetime bw)
    self.createdAt = time.time()
    #: time at which the object was closed.  Call on_bw_transfer_done to set it
    self.endedAt = None
    #: how long since there has been an update.  An optimization to prevent updating all listeners all the time.
    self._noUpdateTicks = 0
    
  def update_bw_stats(self):
    """Called once per interval, pop the oldest value, push a new zero.
    @return:  True if nothing was read or written in the interval that was just dropped"""
    lastRead = self.bytesRead[-1]
    lastWrite = self.bytesWritten[-1]
    self.bytesRead.pop(0)
    self.bytesRead.append(0)
    self.bytesWritten.pop(0)
    self.bytesWritten.append(0)
    return (lastRead + lastWrite) > 0
    
  def handle_bw_event(self, dataRead, dataWritten):
    """Update with information from a bw event."""
    if dataRead < 0 or dataWritten < 0:
      temp = 4
    self.bytesRead[MAX_VALUES-1] += dataRead
    self.bytesWritten[MAX_VALUES-1] += dataWritten
    self.totalRead += dataRead
    self.totalWritten += dataWritten
    BW_UPDATERS.add(self)
    self._noUpdateTicks = 0
    
  def get_instant_bw(self):
    """Average over the past few values to get the instantaneous bandwidth."""
    if self.endedAt:
      return 0, 0
    totalRead = 0.0
    totalWritten = 0.0
    #smooth over the past few intervals:
    for i in range(INSTANT_BW_SMOOTH):
      totalRead += float(self.bytesRead[MAX_VALUES-(1+i)])
      totalWritten += float(self.bytesWritten[MAX_VALUES-(1+i)])
    totalRead /= INSTANT_BW_SMOOTH
    totalWritten /= INSTANT_BW_SMOOTH
    #so that values represent bytes per second:  (since INTERVAL_BETWEEN_UPDATES is in seconds)
    totalRead /= (Globals.INTERVAL_BETWEEN_UPDATES)
    totalWritten /= (Globals.INTERVAL_BETWEEN_UPDATES)
    return totalRead, totalWritten
  
  def on_bw_transfer_done(self):
    """Called whenever the child object is DEFINITELY done transferring data
    for example, it is called by Circuits and Streams when they become 'CLOSED'
    this influences get_total_bw (below) so that it can give an estimated
    bandwidth over the active lifetime of the object."""
    self.endedAt = time.time()
    BW_UPDATERS.add(self)
    
  def get_total_bw(self):
    """Return the total bytes read / time since the Stream was created, (or the
    time that the object spent transmitting if it has already ended and called
    on_bw_transfer_done)"""
    endTime = self.endedAt
    if not endTime:
      endTime = time.time()
    totalTime = endTime - self.createdAt
    if totalTime < 1:
      #we're on a system with a shitty system clock and the circuit succeeded in less than a second.  Should basically never happen
      totalTime = 1
    return float(self.totalRead) / float(totalTime), float(self.totalWritten) / float(totalTime)
    
#: track the bandwidth locally
localBandwidth = BWHistory()
remoteBandwidth = BWHistory()