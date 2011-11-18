#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Application class for FirefoxPortable.  Starts and stops the application, integrates with BitBlinder"""

import re
import sys
import time
try:
  import win32process
except:
  pass

from twisted.internet import threads

from Applications import BitBlinder
import Application
import ApplicationSettings
from gui import GUIController
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.system import System
from common.Errors import DependencyError
from common.classes import Scheduler
from common.system import LaunchProcess
from common.system import Process
from core.bank import Bank

_instance = None
def get():
  return _instance
  
def start(torApp):
  global _instance
  if not _instance:
    _instance = FirefoxPortable(torApp)

class FirefoxPortableSettings(ApplicationSettings.ApplicationSettings):
  DISPLAY_NAME = "Web Browser"
  def __init__(self):
    ApplicationSettings.ApplicationSettings.__init__(self)
    #self.add_attribute("showedWarning", False, "bool",  "Have you been told to close Firefox when you're done with it?", "", isVisible=False)

class FirefoxPortable(BitBlinder.BitBlinderApplication):
  """Wrapper for FirefoxPortable, handles launching, stopping, circuit build policies, etc"""
  def __init__(self, torApp):
    BitBlinder.BitBlinderApplication.__init__(self, "FirefoxPortable", FirefoxPortableSettings, "Browse the Internet.", torApp, Bank.get())
    #It's also weird because our resolver is terrible, it isnt resolving my IP as american
    #TODO:  get a better method for resolving which country a router is in.  Perhaps when they sign up...
    #self.exitCountry = "us"
    #: the process id of polipo.exe in windows.  Necessary to handle the case of the first launch of firefox
    self.polipoProc = None
    #: used to track portable FF when it restarts on us
    self.checkFFEvent = None
    #: if not provided another launch page, this one will be used.  Default is our Torcheck page
    self.startPage = "http://login.bitblinder.com:81/check/"
    #add us to the list of known applications:
    BitBlinder.KNOWN_APPLICATIONS.append(self.name)
    if System.IS_WINDOWS:
      self.isInstalled = True
    else:
      self.isInstalled = False
    #need to handle startup arguments:
    self.catch_event("new_args")
  
  def open_page(self, url):
    """(Re)Start firefox, opening the given page
    @param url:  the page to open
    @type  url:  str (URL)"""
    self.startPage = url
    if self.is_running():
      self.restart()
    else:
      self.start()
      
  def make_new_identity(self):
    circ = self.find_or_build_best_circuit("", 80)
    if circ:
      circ.close()
      circ = self.find_or_build_best_circuit("", 80)
    if not circ:
      log_msg("Couldnt make any circuit to exit to port 80  :(", 0)
      return False
    return True

  def on_new_args(self, startingDir, options, args):
    """Launch FF if --launch-ff was specified to this instance or communicated to use via another"""
    #if we're shutting down, ignore any incoming arguments:
    if self.is_stopping():
      return
    #does this mean we're supposed to start at startup:
    if options.launch_ff:
      #launch the program
      self.start()

  def launch_initial_circuits(self):
    circ = self.build_circuit("", 80)
    circ = self.build_circuit("", 443)
    
  def stop(self):
    if self.checkFFEvent and self.checkFFEvent.active():
      self.checkFFEvent.cancel()
    return Application.Application.stop(self)
    
  def _subprocess_finished(self, result, p):
    if result == True:
      self.remove_process(p)
      if p == self.polipoProc:
        self.polipoProc = None
        self.stop()
      else:
        if len(self.processes) == 1 and self.polipoProc:
          #lets check if any firefoxes start up in the next few seconds, in case this is the reboot:
          if not self.checkFFEvent:
            self.checkFFEvent = Scheduler.schedule_once(2.0, self._check_for_firefoxes)
      if len(self.processes) <= 0:
        self._all_subprocesses_done()
    elif result != False:
      log_ex(result, "Failed while waiting for subprocess")
    
  def _check_for_firefoxes(self):
    self.checkFFEvent = None
    existingFFPIDs = System.get_process_ids_by_exe_path(re.compile("^.*apps\\\\firefoxportable.*\\\\firefox(portable)*.exe$", re.IGNORECASE))
    #if it is NOT running
    if len(existingFFPIDs) <= 0:
      log_msg("Waited long enough.  This is probably shutdown time.", 4)
      self.stop()
      return
    #if firefox is running now, lets just update our process list:
    for pid in existingFFPIDs:
      self.add_process(Process.Process(pid))
      
  #Start up the app
  def launch(self):
    #if not self.settings.showedWarning:
    #  self.settings.showedWarning = True
    #  self.settings.save()
    #  GUIController.get().show_msgbox("IMPORTANT:  DO NOT leave Firefox open if you are not using it!  Some website might keep sending traffic and cause you to lose tokens over time.")
    return threads.deferToThread(self._launch_thread)
    
  def _launch_thread(self):
    processes = []
    if len(self.liveCircuits) <= 0:
      #build some initial Circuits
      self.launch_initial_circuits()
    if System.IS_WINDOWS:
      #we determine which processes should live and die based on their exe path.
      FF_PROC_REGEX = re.compile("^.*\\\\apps\\\\firefoxportable.*\\\\(firefoxportable.exe|firefox.exe)$", re.IGNORECASE)
      #kill any leftover processes from last time:
      existingFFPIDs = System.get_process_ids_by_exe_path(FF_PROC_REGEX)
      for pid in existingFFPIDs:
        kill_process(pid)
      #launch polipo:
      path = "%s\\%s\\" % (self.appBasePath, self.name)
      p = LaunchProcess.LaunchProcess([path+"polipo.exe", "-c", path+"polipo.conf"], creationflags=win32process.CREATE_NO_WINDOW)
      self.polipoProc = Process.Process(p.pid)
      #launch firefox:
      p = LaunchProcess.LaunchProcess([path+"FirefoxPortable.exe", self.startPage])
      #have to wait for both processes to launch properly:
      children = System.get_process_ids_by_exe_path(FF_PROC_REGEX)
      startTime = time.time()
      #dont wait any more than 15 seconds for everything to be started
      while len(children) < 2 and time.time() < startTime + 15:
        time.sleep(0.2)
        children = System.get_process_ids_by_exe_path(FF_PROC_REGEX)
      #if some of the processes are STILL missing:
      if len(children) < 2:
        #kill what we have:
        for child in children:
          kill_process(child)
        #and inform the user:
        raise DependencyError("Failed to launch Firefox.  Try again?")
      #create entries for FirefoxPortable.exe, Firefox.exe and polipo.exe:
      for pid in children:
        processes.append(Process.Process(pid))
      processes.append(self.polipoProc)
    elif System.IS_LINUX:
      raise DependencyError("Anonymous browsing is not yet supported for Linux.  Support is coming soon!")
    else:
      raise Exception("This platform is not supported:  %s" % (sys.platform))
    return processes
