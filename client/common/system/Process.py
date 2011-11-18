#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Provides an abstraction for operating system processes."""

import os   
import time

from twisted.internet import threads
from twisted.internet import defer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common.system import System

#TODO:  allow us to pass a flag about whether this is definitely a child 
#process or not, so we can use waitpid appropriately?  meh, I'm afraid of defunct 
#processes holding us up like they did that one time though...  (threads in 
#twisted need to shutdown before the reactor can stop)
#val = os.waitpid(self.pid, 0)
class Process:
  """NOTE:  linux cannot wait on non-child processes!
  A class to allow us to pretend that all running processes are Popen
  objects, even if they aren't."""
  def __init__(self, pid):
    """Requires the pid of the process to watch."""
    self.pid = pid
    self.returnCode = None
    self.done = False
    self.d = threads.deferToThread(self._wait)
    self.d.addCallback(self._on_process_done)
    self.d.addErrback(self._on_process_done)
    
  def _wait(self):
    """Runs in a Twisted thread, just waiting for the process to finish"""
    if System.IS_WINDOWS:
      self.returnCode = System.wait_for_pid(self.pid)
      return True
    else:
      done = False
      while not done:
        #this is necessary because defunct processes in linux never count as exiting with this method
        #which means that this thread never ends, which means that we hang while shutting down
        if System.SHUTDOWN:
          return False
        try:
          #debug
          if type(self.pid) is not int:
            log_msg('self.pid is not int: %s' % (self.pid), 0)
          os.kill(self.pid, 0)
        except OSError:
          done = True
        time.sleep(0.5)
      return True
  
  def _on_process_done(self, result):
    """Used as both a callback and errback for when the _wait thread finishes or fails"""
    self.done = True
    if type(result) == type(True):
      return result
    log_ex(result, "Failure in PseudoProcess")
    return False
    
  def get_deferred(self):
    """@returns:  a Deferred for when the process is done"""
    if not self.done:
      return self.d
    return defer.succeed(True)
    
  def poll(self):
    """See if this process still exists.  Returns the fake returncode 0 if the
    process finished, None if it is still running."""
    if not self.done:
      return None
    return 0