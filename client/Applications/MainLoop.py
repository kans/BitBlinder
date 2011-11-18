#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The master application, contains main loop.  Controls and coordinates all applications."""

import signal
import webbrowser
import warnings
import sys
import os
import threading
import time

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Twisted
from common.utils import TorUtils
from common.utils import Basic
from common.system import System
from common.system import Files
if System.IS_WINDOWS:
  from common.system import Win32HiddenWindowHack
from common.events import GlobalEvents
from common.classes import Scheduler
from common.classes import Profiler
from common.classes import PrivateKey
from gui import GUIController
from core import ClientUtil
from core import StartupServer
from core import Updater
from core import BWHistory
from core import Startup
from core import ProgramState
from core import ErrorReporting
from core.bank import Bank
from core.network import NetworkState
from Applications import BitBlinder
from Applications import FirefoxPortable
from BitTorrent import BitTorrentClient
from Applications import GlobalSettings
from Applications import CoreSettings
from Applications import Tor

if ProgramState.USE_GTK:
  import gtk
  
#NOTE:  DO NOT USE--STRICTLY FOR DEBUGGING (and error reports)
_instance = None
def get():
  global _instance
  return _instance
  
class MainLoop(GlobalEvents.GlobalEventMixin):
  """The class that coordinates all other Application classes and contains the main loop."""
  def __init__(self):
    global _instance
    _instance = self
    #: BitBlinder application (for providing SOCKS transport to others)
    self.bbApp = None
    #: BitTorrent application:
    self.btApp = None
    #: Firefox application (windows only):
    self.ffApp = None
    #: Tor application:
    self.torApp = None
    #: Bank application:
    self.bankApp = None
    #: the main GUI, whether it's GTK, curses, or just the console
    self.gui = None
    #: our settings that apply to all apps:
    self.coreSettings = None
    #: our setting that apply to login and usernames:
    self.globalSettings = None
    #: the regularly occuring update event
    self.updateEvent = None
    #: for tracking the status of Tor, BitBlinder, etc.  This class should be moved out of here into the various subclasses probably?
    self.statusTracker = None
    #the global events that we listen for:
    self.catch_event("open_web_page_signal")
    self.catch_event("quit_signal")

  def _setup_environment(self):
    """Finish misc startup tasks like starting logging, zipping any crash logs 
    from the last run, installing signal handlers, startup argument handler, etc"""
    
    #apply the necessary hacks:
    Twisted.apply_dns_hack()
    Twisted.apply_dns_hack2()
    if System.IS_WINDOWS:
      Win32HiddenWindowHack.apply()
    
    #start listening for connections from any other instances of BitBlinder
    StartupServer.start()
    
    Profiler.start()
    
    #Make sure we log ALL exceptions
    Twisted.install_exception_handlers(self.on_quit_signal)
    
    #Set the signal handler for exiting
    def sig_handler(signum, frame):
      self.on_quit_signal()
    signal.signal(signal.SIGTERM, sig_handler)
    
    #make the gui:
    GUIController.start()
    self.gui = GUIController.get()
    
    #do some tests to see how this user's network is configured:
    NetworkState.test_network_state()
    
    #TODO: figure out what needs to change in the wrapper and submit a fix
    warnings.filterwarnings('ignore', module=".*TwistedProtocolWrapper.*", lineno=447)
    
  def _load_settings(self):
    """Load global and core settings files.  Deals with old format for storing settings"""
    
    #load a global config that said whether to store the last user that logged in (and his password)
    self.globalSettings = GlobalSettings.load()
    #always save, so the user can more easily edit the file for starting up from the console
    self.globalSettings.save()
    
    #does a settings file already exist?
    settingsFile = os.path.join(Globals.USER_DATA_DIR, CoreSettings.CoreSettings.defaultFile)
    if not Files.file_exists(settingsFile):
      #if not, make the folder
      if not Files.file_exists(Globals.USER_DATA_DIR):
        os.makedirs(Globals.USER_DATA_DIR)
      #and check that this isnt an old installation (we used to store settings on a 
      #per username basis, which turned out to be a stupid idea).  If that data exists,
      #copy it to the new location.
      if len(self.globalSettings.username) > 0:
        oldSettingsFilePath = os.path.join(Globals.USER_DATA_DIR, self.globalSettings.username, CoreSettings.CoreSettings.defaultFile)
        if os.path.exists(oldSettingsFilePath):
          oldFolder = os.path.join(Globals.USER_DATA_DIR, self.globalSettings.username)
          newFolder = Globals.USER_DATA_DIR
          Files.recursive_copy_folder(oldFolder, newFolder)
        
    #load the core settings:
    CoreSettings.start()
    self.coreSettings = CoreSettings.get()
    self.coreSettings.load(settingsFile)
    self.coreSettings.fileName = settingsFile
    
  def _load_data(self):
    """Load the public key and any other misc data needed by the program"""
    self._load_country_data()
    #load (and generate if necessary) the Tor public key
    self._load_private_key()
    
  def _load_country_data(self):
    """Load the mapping from 2-letter country codes to proper country names"""
    countryMappingFile = open(os.path.join(Globals.DATA_DIR, "country_codes.csv"), "rb")
    data = countryMappingFile.read()
    countryMappingFile.close()
    lines = data.split("\r\n")
    Globals.COUNTRY_NAMES = {None:  "unknown", 'None': "unknown"}
    for line in lines:
      if line == "":
        continue
      vals = line.split(",")
      Globals.COUNTRY_NAMES[vals[0]] = vals[1]
    
  def _load_private_key(self):
    """Load (and generate if necessary) the Tor public and private keys"""
    log_msg("Loading private key...", 3)
    try:
      torKey = os.path.join(Globals.USER_DATA_DIR, "tor_data", "keys", "secret_id_key")
      if not Files.file_exists(torKey):
        #have to create it ourselves.  First make the folders if necessary:
        keyFolder = os.path.join(Globals.USER_DATA_DIR, "tor_data", "keys")
        if not Files.file_exists(keyFolder):
          os.makedirs(keyFolder)
        #then generate the key
        Globals.PRIVATE_KEY = PrivateKey.PrivateKey(1024)
        #and save it in the appropriate format
        if not Globals.PRIVATE_KEY.key.save_key(torKey, cipher=None):
          raise Exception("Failed to save key as PEM!")
      else:
        Globals.PRIVATE_KEY = PrivateKey.PrivateKey(torKey)
      Globals.PUBLIC_KEY = Globals.PRIVATE_KEY.publickey()
      Globals.FINGERPRINT = TorUtils.fingerprint(Globals.PRIVATE_KEY.n, Globals.PRIVATE_KEY.e)
      log_msg("Globals.FINGERPRINT = %s" % (Globals.FINGERPRINT), 3)
    except Exception, error:
      log_ex(error, "Failed while loading private key data")
      
  def _create_applications(self):
    """Creates all application classes that the MainLoop coordinates.  This does NOT start them-
    that's done later.
    WARNING: the gui assumes the apps exist!
    """
    #create the Bank application:
    Bank.start()
    self.bankApp = Bank.get()
    #create the Tor application:
    Tor.start()
    self.torApp = Tor.get()
    
    #create the pseudo applications for InnomiNet
    BitBlinder.start(self.torApp, self.bankApp)
    self.bbApp = BitBlinder.get()
    #create the applications:
    BitTorrentClient.start(self.torApp)
    self.btApp = BitTorrentClient.get()
    self.bbApp.add_application(self.btApp)
    if System.IS_WINDOWS:
      FirefoxPortable.start(self.torApp)
      self.ffApp = FirefoxPortable.get()
      self.bbApp.add_application(self.ffApp)
    
    self.gui.on_applications_created(self.bankApp, self.torApp, self.bbApp, self.btApp, self.ffApp)
      
  def _start_psyco(self):
    """Enable psyco if the setting tells us to"""
    if self.coreSettings.usePsyco and Globals.USE_PSYCO:
      try:
        import psyco
        from gui.gtk.display import PriorityDisplay
        psyco.bind(PriorityDisplay.PriorityDisplay.update_completion)
        from BitTorrent.BT1 import PiecePicker, Downloader
        psyco.bind(PiecePicker.PiecePicker.next)
        psyco.bind(PiecePicker.PiecePicker.got_have)
        psyco.bind(Downloader.DownloadPeer.got_have_bitfield)
      except Exception, error:
        log_ex(error, "Failed to bind psyco optimizations!")

  #maybe convert shutdown and quit_all to global signals that we handle as an application?
  def start(self):
    """Do the rest of the setup before turning control over to the reactor"""
    
    self._setup_environment()
    self._load_settings()
    self._load_data()
    self._create_applications()
    
    #in case this was the first run:
    self.bbApp.settings.fileName = os.path.join(Globals.USER_DATA_DIR, BitBlinder.BitBlinderSettings.defaultFile)
    GlobalEvents.throw_event("settings_changed")
    
    #must be done after settings are loaded
    self._start_psyco()
 
    #check for updates for the program:
    Updater.get().start()
    
    #start the bank
    bankStartupDeferred = self.bankApp.start()
    bankStartupDeferred.addCallback(self._on_bank_ready)
    bankStartupDeferred.addErrback(log_ex, "Bank failed to start!")
    
    #the rest of the startup code needs to run after the reactor has started:
    Scheduler.schedule_once(0.0, self._on_reactor_started)
    
  def _on_reactor_started(self):
    self._start_logging()
    #start Tor early if we're going to need it:
    if self._will_need_tor():
      self.bbApp.start()
      
  def _will_need_tor(self):
    """Return True if we are launching/running any apps that require anonymity.
    Ideally we'd check the startup arguments here too, but meh"""
    if self.btApp.settings.useTor:
      return True
    return False
    
  def _start_logging(self):
    #before we open the logs, make sure any previous errors get zipped up
    ErrorReporting.check_previous_logs()
    #delete the old log files and open the new ones
    Globals.logger.start()
    ErrorReporting.create_marker_file()
    
    #submit a bugreport if there is one from the last run:  (only do it if this is a release copy)
    #(now that we know the user's name)
    if ErrorReporting.has_report_to_send():
      ErrorReporting.prompt_about_bug_report()
         
  def _on_bank_ready(self, result):
    """Called when the bank has finished starting.  Alerts the applications to any
    startup arguments that were passed in, which will likely cause them to actually start."""
    if result != True:
      log_msg("Bank failed to start correctly!", 0)
      return result
      
    #handle the starting arguments:
    Startup.handle_args(ProgramState.STARTING_DIR, sys.argv[1:])
    GlobalEvents.throw_event("startup")
    
    #if this is the first run, save all the settings files:
    if self.bbApp.isFirstRun:
      for app in [self.bbApp, self.btApp, self.torApp, self.ffApp]:
        if app:
          app.settings.save()
    self.coreSettings.save()
     
    #schedule update function:
    def do_update():
      BWHistory.update_all()
      return True
    ProgramState.DO_UPDATES = True
    self.updateEvent = Scheduler.schedule_repeat(Globals.INTERVAL_BETWEEN_UPDATES, do_update)
    return result
    
  def get_status(self):
    statusString = ""
    #get the status of all the individual components:
    for app in (self.bankApp, self.torApp, self.bbApp, self.btApp, self.ffApp):
      if app:
        statusString += app.get_status() + "\n"
    #network status
    statusString += NetworkState.get_status()
    return statusString

  def main(self):
    """MAIN LOOP"""
    while not ProgramState.DONE:
      #make sure that the main loop keeps running in spite of errors:
      try:
        if ProgramState.USE_GTK:
          gtk.main()
        else:
          #Globals.reactor.run()
          Globals.reactor.run(installSignalHandlers=False)
      #just print exceptions and try to continue with the main loop:
      except Exception, error:
        log_ex(error, "Unhandled exception in main loop:")
        
  def cleanup(self):
    """Make sure the reactor, threads, etc have been stopped.  Also removes
    the file that indicates we shutdown cleanly."""
    
    #shutdown Twisted
    if ProgramState.USE_GTK:
      Globals.reactor.stop()
      Globals.reactor.runUntilCurrent()
      
    #ensure that all threads have closed:
    remainingThreads = threading.enumerate()
    for thread in remainingThreads:
      if threading._MainThread != type(thread):
        log_msg("Thread has not finished by the end of the program: %s" % (thread), 1)

    #start the update if necessary:
    if Updater.get().APPLY_UPDATE:
      ClientUtil.apply_update()
      
    #NOTE:  we intentionally leave the log files open so that errors can get written to them...
    log_msg("Thanks for using BitBlinder", 2)
    ErrorReporting.destroy_marker_file()
    
    #NOTE:  this is here so that threads can finish properly.  I was getting errors from leftover threads without it.
    #However, I'm pretty sure that it was just from the IDE
    time.sleep(0.2)

  def on_open_web_page_signal(self, url, openDirectly=True):
    """Either use our Firefox application to open the web page (if openDirectly 
    is False and we actually have a Firefox application), or just use their 
    default browser."""
    if not self.ffApp or openDirectly:
      try:
        webbrowser.open(url)
      except Exception, error:
        GUIController.get().show_msgbox("Could not open website:  %s" % (error))
    else:
      self.ffApp.open_page(url)

  def on_quit_signal(self):
    """Close all applications, then call shutdown."""
    if not ProgramState.DONE:
      ProgramState.DONE = True
      if self.btApp and self.btApp.is_stopping():
        self.btApp.force_stop()
      System.SHUTDOWN = True
      shutdownDeferred = BitBlinder.stop()
      shutdownDeferred.addCallback(self._shutdown)
      shutdownDeferred.addErrback(self._shutdown)
      
  def _shutdown(self, result):
    """Stop the main loop and cause the program to exit.
    This should ONLY be called after all Applications are shut down cleanly."""
    Basic.validate_result(result, "MainLoop::_shutdown")
    #close the server that listens for new versions of the app to start up:
    StartupServer.stop()
    #remove scheduled events:
    if self.updateEvent and self.updateEvent.active():
      self.updateEvent.cancel()
    ProgramState.DO_UPDATES = False
    self.updateEvent = None
    GlobalEvents.throw_event("shutdown")
    log_msg("Done with shutdown deferreds", 4)
    #close the main loop
    if ProgramState.USE_GTK:
      try:
        gtk.main_quit()
      except Exception, error:
        log_ex(error, "Couldn't kill the gtk main loop")
    else:
      try:
        Globals.reactor.stop()
      except Exception, error:
        log_ex(error, "Couldn't stop the reactor")
