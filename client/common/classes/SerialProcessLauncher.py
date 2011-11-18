#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Simple class to launch programs one after another."""

from twisted.internet import defer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from common.system import LaunchProcess
from common.system import Process

_instance = None
def get():
  global _instance
  if not _instance:
    _instance = SerialProcessLauncher()
  return _instance

class SerialProcessLauncher:
  def __init__(self):
    #: we can only run a single exe at a time that requires UAC in vista, otherwise the prompt is hidden and everything fails
    self.currentApp = None
    #: this is a list of programs requiring UAC that are to be launched one after another (after each finishes, launch the next)
    self.launchList = []
    #: the event representing when we will check if we should launch another UAC program again
    self.programCheckEvent = None
      
  def run_app(self, cmd):
    appDeferred = defer.Deferred()
    self.launchList.append([cmd, appDeferred])
    self._check_apps()
    return appDeferred
    
  def _check_apps(self):
    if not self.programCheckEvent:
      self.programCheckEvent = Scheduler.schedule_repeat(1.0, self._check_apps)
    #program still running?
    if self.currentApp and self.currentApp.poll() == None:
      log_msg("Waiting for UAC app to finish...", 1)
      return True
    #are there any more to launch?
    if len(self.launchList) > 0:
      #launch the next one:
      cmd, nextDeferred = self.launchList.pop(0)
      log_msg("Launching next UAC app:  %s" % (cmd), 1)
      self.currentApp = LaunchProcess.LaunchProcess(cmd)
      process = Process.Process(self.currentApp.pid)
      process.d.chainDeferred(nextDeferred)
      return True
    #nothing else to launch:
    else:
      log_msg("No more UAC apps to launch.", 1)
      self.programCheckEvent = None
      return False
    
