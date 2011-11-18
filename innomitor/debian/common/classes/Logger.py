#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A common logging utility class"""

import sys
import os
import shutil
import threading
import types
import inspect
import traceback
import time
from cStringIO import StringIO

from common import Globals

#: Use to specify a function for printing to the screen (just using print nukes the curses gui).  If None, uses print
PRINT_FUNCTION = None

class Logger:
  #: Pick a different place for errors to go if you want
  ERROR_LOG_NAME = "errors"
  def __init__(self, cutoff=5):
    #: what level of debugging to default to.
    self.DEFAULT_LOG_CUTOFF = cutoff
    #: the possible log levels:
    self.LOG_LEVELS = ("err", "warn", "notice", "info", "debug")
    #: to make the logs threadsafe.  Just ensure that log_msg doesnt ever call log_msg...
    self.semaphore = threading.BoundedSemaphore()
    #: The name of the log to write by default
    self.defaultLogName = None
    #: Whether the logs have been opened yet or not
    self.openedLogs = False
    #: file names for our various logs
    self.logFiles = {}
    #: record messages to go to the logs once they're opened (they are not opened immediately)
    self.tempLogs = {}
    #: the debug level for each event type that is logged
    self.loggingEventLevels = {}
    #set us as the logging object
    assert Globals.logger is None, "Only make one logging object!"
    Globals.logger = self
    
  def _get_file_name(self, logName):
    return logName + ".out"

  def start_logs(self, logFileNameList, defaultLogName, logFolderName=None):
    """Open up the log files that we use for errors, etc.
    Just pass it the list of names for the files (will be logged to name.out)"""
    if logFolderName != None:
      Globals.LOG_FOLDER = logFolderName
    if not os.path.exists(Globals.LOG_FOLDER):
      os.mkdir(Globals.LOG_FOLDER)
    for logName in logFileNameList:
      assert type(logName) == types.StringType, \
        "Log names must be strings, %s was a %s" % (logName, type(logName))
      fileName = self._get_file_name(logName)
      self.logFiles[logName] = open(os.path.join(Globals.LOG_FOLDER, fileName), 'wb')
      if logName in self.tempLogs:
        self.logFiles[logName].write(self.tempLogs[logName])
        self.loggingEventLevels[logName] = self.DEFAULT_LOG_CUTOFF
        self.tempLogs[logName] = ""
    if None in self.tempLogs:
      self.logFiles[defaultLogName].write(self.tempLogs[None])
    self.defaultLogName = defaultLogName
    self.openedLogs = True
    
  def set_event_logging_levels(self, loggingEventLevels):
    """Specify the debug level for each type of message that is printed.
    @param loggingEventLevels:  a mapping from message type name to debug level (0-5)
    @type  loggingEventLevels:  Dictionary"""
    #and set the events to listen to:
    for logName, level in loggingEventLevels.iteritems():
      self.loggingEventLevels[logName] = level

  def log_msg(self, msg, debugval=0, log=None, popLevels=0):
    """logs a message (msg) to both the console and a file (determined by log) if
    debugval is greater than the current logging level.  Is thread safe."""
    eventName = ""
    currentLevel = self.DEFAULT_LOG_CUTOFF
    if self.loggingEventLevels.has_key(log):
      currentLevel = self.loggingEventLevels[log]
    if not log:
      log = self.defaultLogName
    else:
      #user specified a log, but it's not a file, and not one of the events we care about, so just exit
      if not self.logFiles.has_key(log) and log.lower() != self.ERROR_LOG_NAME:
        if log in self.loggingEventLevels and self.loggingEventLevels[log] == None:
          return
        eventName = log.upper() + " "
        log = "main"
    if currentLevel >= debugval:
      #TODO:  this is a pretty sketchy way of getting this information...  will probably cause compatibility problems at some point  :(
      #figure out the filename and line number that this function was called from
      fileName = "None"
      num = "None"
      try:
        cFrame = sys._getframe().f_back
        while popLevels > 0:
          popLevels -= 1
          cFrame = cFrame.f_back
        line = str(cFrame.f_code)
        fileName = line.split('"')[1].split("\\")[-1].replace(".py", "")
        num = line.split(',')[-1].split(" ")[-1].replace(">", "")
      except:
        self._print_text("OH NOES FAILED TO GET STACK LOCATION FOR LOG_MSG\n\n\n")
      #make sure we are the only function printing:
      self.semaphore.acquire()
      try:
        #figure out what file to print to
        if not log or not self.logFiles.has_key(log):
          outputFile = None
        else:
          outputFile = self.logFiles[log]
        #format the message and print it:
        if str(log) == "automated":
          msg = "AUTOLOG:  %s %s" % (time.time(), msg)
        else:
          timeString = self._get_time_string()[11:]
          msg = "%s [%s] %s%s::%s:  %s" % (timeString, self.LOG_LEVELS[debugval], eventName, fileName, num, msg)
        if str(log) not in ("tor_conn", "pysocks", self.ERROR_LOG_NAME):
          self._print_text(msg)
          #sys.stdout.flush()
        if outputFile:
          outputFile.write(msg + "\n")
          #always flush everything now so we can be sure the messages are up to date while debugging
          outputFile.flush()
        else:
          if log not in self.tempLogs:
            self.tempLogs[log] = ""
          self.tempLogs[log] += msg + "\n"
      except:
        traceback.print_exception(*sys.exc_info())
        #try to print to the error file at least, since we cant call log_msg again (it would be called by log_ex)
        if self.logFiles.has_key(self.ERROR_LOG_NAME):
          data = StringIO()
          traceback.print_exc(file = data)
          self.logFiles[self.ERROR_LOG_NAME].write(data.getvalue())
      finally:
        self.semaphore.release()
        
  def _get_time_string(self, curr_time=None):
    """Return a formatted string for the time (defaults to current gmtime)
    Pass this a time in the tuple format"""
    if not curr_time:
      curr_time = time.localtime()
    return "%04d-%02d-%02d %02d:%02d:%02d" % curr_time[0:6]
        
  def _print_text(self, text):
    """Either prints, or does something with a curses based method to display text
    this should be used everywhere instead of the builtin print function"""
    if callable(PRINT_FUNCTION):
      PRINT_FUNCTION(text)
    else:
      print(text)
      
  def _make_failure(self, exctyp=None, excvalue=None, excTraceback=None):
    """
    Print the usual traceback information, followed by a listing of all the
    local variables in each frame.
    Adapted from http://code.activestate.com/recipes/52215/
    """
    if None in (exctyp, excvalue):
      (exctyp, excvalue, excTraceback) = sys.exc_info()
    SEP = '\n'
    MAX_LEN = 4096
    
    #first print the outer frame, just in case that's necessary:
    outerFrameMsg = ""
    outerFrames = []
    try:
      outerFrames = inspect.getouterframes(inspect.currentframe())
      outerFrames.reverse()
      for frameTuple in outerFrames:
        if len(frameTuple) > 0:
          frame = frameTuple[0]
          outerFrameMsg += "Frame %s in %s at line %s" % (frame.f_code.co_name,
                                               frame.f_code.co_filename,
                                               frame.f_lineno) + SEP
    except Exception, error:
      outerFrameMsg += "Failed to print outer frame because %s" % (str(error))
    finally:
      del outerFrames
    outerFrameMsg += "(log_ex)" + SEP
    
    msg = " ".join(traceback.format_exception(exctyp, excvalue, excTraceback)) + SEP
    stack = []
    while excTraceback:
      stack.append(excTraceback.tb_frame)
      excTraceback = excTraceback.tb_next
    shortMsg = msg
    msg += "Locals by frame, innermost last" + SEP
    for frame in stack:
      msg += SEP
      msg += "Frame %s in %s at line %s" % (frame.f_code.co_name,
                                           frame.f_code.co_filename,
                                           frame.f_lineno) + SEP
      for key, value in frame.f_locals.items():
        msg += "\t%20s = " % (key)
        #We have to be careful not to cause a new error in our error
        #printer! Calling str() on an unknown object could cause an
        #error we don't want.
        #Josh:  Actually, we want repr here I think, printing binary is annoying.
        #Kans: hows it going?
        try:                   
          valueStr = repr(value)
          if len(valueStr) > MAX_LEN:
            valueStr = valueStr[:MAX_LEN] + "..."
        except Exception:
          valueStr = "<ERROR WHILE PRINTING VALUE>"
        msg += valueStr + SEP
    return shortMsg, outerFrameMsg + msg
      
  #TODO:  rearrange this function to use exception_is_a, and have a better name.  Requires re-arranging imports so that we use Logging and can import from Basic
  def _create_error_string(self, reason, errors=None):
    """Make an error string out of reason, given the expected error types in errors.
    @returns:  String or None (if reason was an Exception or Failure that we did not expect)"""
    #check if this is a Twisted Failure without having to import that class (Django wont let us import Twisted because of Zope)
    if hasattr(reason, "value") and issubclass(type(reason.value), Exception):
      reason = reason.value
    if issubclass(type(reason), Exception) and errors:
      for error in errors:
        if issubclass(type(reason), error):
          return str(reason)
    if reason is type(""):
      return reason
    return None

  #TODO:  seems kind of pointless to pass excType
  def log_ex(self, reason, title, exceptions=None, reasonTraceback=None, excType=None):
    """Used to log any unexpected exceptions with a full stack trace and local variable output
    @param reason:  the current error
    @type  reason:  Exception, Failure, or String.
    @param title:  A message to display for this failure
    @type  title:  String
    @param exceptions:  the expected Exception types.  Failures of this type will NOT generate text in the error log, just warnings
    @type  exceptions:  List (of Exception types)
    @param reasonTraceback:  the stack for reason
    @type  reasonTraceback:  a traceback object
    @param excType:  the type for the current failure (of reason)
    @type  excType:  Exception type"""
    
    failureString = self._create_error_string(reason, exceptions)
    if failureString == None:
      #this is an unexpected error, either write it to the error log
      if title:
        #make an exception out of it if necessary:
        if type(reason) in (type(""), type(None)):
          try:
            raise Exception(str(reason))
          except Exception, error:
            reason = error
        #check if this is a Twisted Failure without having to import that class:
        if hasattr(reason, "value") and issubclass(type(reason.value), Exception):
          failureString = str(reason)
          reason = reason.value
        shortMsg = failureString
        #make sure that we have an Exception:
        if not issubclass(type(reason), Exception):
          try:
            raise Exception("'%s' is not an Exception, Failure or String!" % (reason))
          except Exception, error:
            reason = error
        #ok, make a debug string out of the exception (unless it was a Failure, in which case we're set)
        if not failureString:
          shortMsg, failureString = self._make_failure(excType, reason, reasonTraceback)
        #and finally, log it to our error log:
        self.log_msg("%s:  %s" % (title, failureString), 0, self.ERROR_LOG_NAME, popLevels=1)
        self.log_msg("%s:  %s" % (title, shortMsg), 0, popLevels=1)
      #or re-raise it
      else:
        if not issubclass(type(reason), Exception):
          reason = Exception(str(reason))
        raise reason
    else:
      #this error was expected, just log_msg it:
      self.log_msg("%s:  %s" % (title, failureString), 1, popLevels=1)
        
