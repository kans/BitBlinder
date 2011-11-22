#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""For writing events to log files.  Handles timestamps, rollover, etc"""
#TODO:  deletes are not done quite correctly, since we also stuck the pid in there.

import time
import os
import shutil
import threading
import logging
import logging.handlers
import string
import glob
try:
  import codecs
except ImportError:
  codecs = None

import Events
from DBUtil import get_current_gmtime

#: whether the module is ready for calls to log_event
_IS_READY = False
#: the logging.logger to use for actually logging the events
EVENT_LOGGER = None
#: so that multiple threads can use the same log:
LOG_SEM = threading.BoundedSemaphore()
#: how many days worth of logs to retain before deleting anything
NUM_BACKUP_DAYS = 7

def open_logs(fileName):
  """Log files must be opened before any events can be saved"""
  global _IS_READY, EVENT_LOGGER
  if _IS_READY:
    return
  _IS_READY = True
  pathName, file = os.path.split(fileName)
  #DEBUG_user = os.getuid()
  if pathName and not os.path.exists(pathName):
    #try to make the folders:
    os.makedirs(pathName)
  EVENT_LOGGER = logging.getLogger('events')
  handler = TimeStampFileHandler(fileName, 'H', 1)
  formatter = logging.Formatter('%(message)s')
  handler.setFormatter(formatter)
  EVENT_LOGGER.addHandler(handler)
  EVENT_LOGGER.setLevel(logging.DEBUG)
  
def close_logs():
  """Close logs when shutting down to ensure everything gets flushed to disk cleanly"""
  global _IS_READY, EVENT_LOGGER
  if not _IS_READY:
    return
  LOG_SEM.acquire()
  try:
    _IS_READY = False
    EVENT_LOGGER = None
    logging.shutdown()
  finally:
    LOG_SEM.release()

def save_event(event):
  """Save an event to the log file"""
  assert _IS_READY
  assert isinstance(event, Events.ServerEvent)
  event = event.save()
  LOG_SEM.acquire()
  try:
    EVENT_LOGGER.info(event)
  finally:
    LOG_SEM.release()
  
def load_event(data):
  """Load an event from some data that came from a log file"""
  eventName, data = data.replace("\n", "").split(" ", 1)
  event = eval("Events.%s()" % (eventName))
  event.load(data)
  return event
  
def parse_events(cur, fileName, numLines=0):
  earliestTime = None
  lineNum = 0
  #for each line in the file
  f = open(fileName, "rb")
  while True:
    line = f.readline()
    lineNum += 1
    #end of the file
    if not line:
      break
    #not a complete file
    if not "\n" in line:
      break
    #already parsed this line before
    if not lineNum > numLines:
      continue
    #load the event
    event = load_event(line)
    #is this the earliest event that we've learned of?
    if earliestTime is None:
      earliestTime = event.get_time()
    #and stick it in the database
    event.insert(cur)
  f.close()
  if earliestTime is None:
    earliestTime = get_current_gmtime()
  return earliestTime, lineNum-1
  
class TimeStampFileHandler(logging.handlers.TimedRotatingFileHandler):
  """
  Handler for logging to a file, rotating the log file at certain timed
  intervals.

  If backupCount is > 0, when rollover is done, no more than backupCount
  files are kept - the oldest ones are deleted.
  """
  def __init__(self, filename, when='h', interval=1, encoding=None):
    self.when = string.upper(when)
    # Calculate the real rollover interval, which is just the number of
    # seconds between rollovers.  Also set the filename suffix used when
    # a rollover occurs.  Current 'when' events supported:
    # S - Seconds
    # M - Minutes
    # H - Hours
    # D - Days
    # midnight - roll over at midnight
    # W{0-6} - roll over on a certain day; 0 - Monday
    #
    # Case of the 'when' specifier is not important; lower or upper case
    # will work.
    currentTime = int(time.time())
    if self.when == 'S':
      self.interval = 1 # one second
      self.suffix = "%Y-%m-%d_%H-%M-%S"
    elif self.when == 'M':
      self.interval = 60 # one minute
      self.suffix = "%Y-%m-%d_%H-%M"
    elif self.when == 'H':
      self.interval = 60 * 60 # one hour
      self.suffix = "%Y-%m-%d_%H"
    elif self.when == 'D' or self.when == 'MIDNIGHT':
      self.interval = 60 * 60 * 24 # one day
      self.suffix = "%Y-%m-%d"
    elif self.when.startswith('W'):
      self.interval = 60 * 60 * 24 * 7 # one week
      if len(self.when) != 2:
        raise ValueError("You must specify a day for weekly rollover from 0 to 6 (0 is Monday): %s" % self.when)
      if self.when[1] < '0' or self.when[1] > '6':
        raise ValueError("Invalid day specified for weekly rollover: %s" % self.when)
      self.dayOfWeek = int(self.when[1])
      self.suffix = "%Y-%m-%d"
    else:
      raise ValueError("Invalid rollover interval specified: %s" % self.when)

    self.interval = self.interval * interval # multiply by units requested
    self.rolloverAt = currentTime + self.interval

    # If we are rolling over at midnight or weekly, then the interval is already known.
    # What we need to figure out is WHEN the next interval is.  In other words,
    # if you are rolling over at midnight, then your base interval is 1 day,
    # but you want to start that one day clock at midnight, not now.  So, we
    # have to fudge the rolloverAt value in order to trigger the first rollover
    # at the right time.  After that, the regular interval will take care of
    # the rest.  Note that this code doesn't care about leap seconds. :)
    if self.when == 'MIDNIGHT' or self.when.startswith('W'):
      # This could be done with less code, but I wanted it to be clear
      t = time.localtime(currentTime)
      currentHour = t[3]
      currentMinute = t[4]
      currentSecond = t[5]
      # r is the number of seconds left between now and midnight
      r = logging.handlers._MIDNIGHT - ((currentHour * 60 + currentMinute) * 60 + currentSecond)
      self.rolloverAt = currentTime + r
      # If we are rolling over on a certain day, add in the number of days until
      # the next rollover, but offset by 1 since we just calculated the time
      # until the next day starts.  There are three cases:
      # Case 1) The day to rollover is today; in this case, do nothing
      # Case 2) The day to rollover is further in the interval (i.e., today is
      #         day 2 (Wednesday) and rollover is on day 6 (Sunday).  Days to
      #         next rollover is simply 6 - 2 - 1, or 3.
      # Case 3) The day to rollover is behind us in the interval (i.e., today
      #         is day 5 (Saturday) and rollover is on day 3 (Thursday).
      #         Days to rollover is 6 - 5 + 3, or 4.  In this case, it's the
      #         number of days left in the current week (1) plus the number
      #         of days in the next week until the rollover day (3).
      # The calculations described in 2) and 3) above need to have a day added.
      # This is because the above time calculation takes us to midnight on this
      # day, i.e. the start of the next day.
      if when.startswith('W'):
        day = t[6] # 0 is Monday
        if day != self.dayOfWeek:
          if day < self.dayOfWeek:
            daysToWait = self.dayOfWeek - day
          else:
            daysToWait = 6 - day + self.dayOfWeek + 1
          self.rolloverAt = self.rolloverAt + (daysToWait * (60 * 60 * 24))
    self.baseFilename = filename
    logging.handlers.BaseRotatingHandler.__init__(self, self._get_file_name(), 'a', encoding)
    self.baseFilename = filename
    self.delete_old_logs()

    #print "Will rollover at %d, %d seconds from now" % (self.rolloverAt, self.rolloverAt - currentTime)
      
  def _get_file_name(self):
    t = self.rolloverAt - self.interval
    # get the time that this sequence started at and make it a TimeTuple
    timeTuple = time.localtime(t)
    dfn = self.baseFilename + "." + str(os.getpid()) + "." + time.strftime(self.suffix, timeTuple)
    return dfn
    
  def delete_old_logs(self):
    try:
      #delete all of our log files older than cutoffTime
      fileNames = glob.glob(self.baseFilename + ".*")
      cutoffTime = time.time() - (NUM_BACKUP_DAYS * 60.0 * 60.0 * 24.0)
      for fileName in fileNames:
        if os.path.getmtime(fileName) < cutoffTime:
          os.remove(fileName)
    #NOTE:  this is because multiple processes might do this at the same time...
    except:
      pass
    
  def doRollover(self):
    """
    do a rollover; in this case, a date/time stamp is appended to the filename
    when the rollover happens.  However, you want the file to be named for the
    start of the interval, not the current time.  If there is a backup count,
    then we have to get a list of matching filenames, sort them and remove
    the one with the oldest suffix.
    """
    self.stream.close()
    self.delete_old_logs()
    #print "%s -> %s" % (self.baseFilename, dfn)
    t = int(time.time())
    while self.rolloverAt <= t:
      self.rolloverAt += self.interval
    dfn = self._get_file_name()
    if self.encoding:
      self.stream = codecs.open(dfn, 'w', self.encoding)
    else:
      self.stream = open(dfn, 'w')
    
