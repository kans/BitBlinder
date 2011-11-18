#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Application class for BitTorrent (our custom version of BitTornado)"""

import random
import urllib
from cgi import parse_qs
import threading
import time
import shutil
import re
import warnings
try:
  import _winreg
except:
  pass
import os
import sys
from hashlib import sha1 

from BitTorrent.bencode import bencode, bdecode
from binascii import b2a_hex as tohex, a2b_hex as unhex
#TODO: go change calls to sha to hashlib instead
warnings.filterwarnings('ignore', category=DeprecationWarning)
from BitTorrent.launchmanycore import LaunchMany
from BitTorrent.download_bt1 import defaults
from BitTorrent.parsedir import read_torrent
from twisted.internet import defer
from BitTorrent.bencode import bencode, bdecode
warnings.resetwarnings()

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common.system import System
from common.Errors import DependencyError
from common.events import GlobalEvents 
from common.events import GeneratorMixin
from common.classes import SerialProcessLauncher
from common.classes import Scheduler
from common import Globals
from core.bank import Bank
from core import ClientUtil
from core import StartupServer
from core import ProgramState
from Applications import Application
from Applications import BitBlinder
from Applications import ApplicationSettings
if ProgramState.USE_GTK:
  from gui.gtk.dialog import RegistryDialog
else:
  RegistryDialog = None
from gui import GUIController

_instance = None
def get():
  return _instance
  
def start(torApp):
  global _instance
  if not _instance:
    _instance = BitTorrentClient(torApp)

#: these are from BitTornado.  This is how they store their settings.  I didnt feel like yanking all their code apart, so we just format our settings using their method.
defaults.extend( [
  ( 'parse_dir_interval', 0,
    "how often to rescan the torrent directory, in seconds.  0 means dont scan." ),
  ( 'saveas_style', 2,
    "How to name torrent downloads (1 = rename to torrent name, " +
    "2 = save under name in torrent, 3 = save in directory under torrent name)" ),
  ( 'display_path', 1,
    "whether to display the full path or the torrent contents for each torrent" ),
  ( 'torrent_dir', Globals.TORRENT_FOLDER,
    "Where to store torrents by default" ),
  ( 'max_announce_retry_interval', 1800,
    "maximum time to wait between retrying announces if they keep failing"),
  ( 'use_socks', 0,
    "Whether to tunnel all connections through Tor" ),
  ( 'max_initiate_per_second', 1,
    "Maximum number of new connections to open each second" ),
  ( 'max_half_open', 10,
    "Maximum number of incomplete connections" ),
  ( 'max_inactive_time', 300,
    "Number of seconds before a peer connection is closed from inactivity" ),
  #TODO:  move to IOCP reactor for windows and EPoll for linux, then we wont need to limit connections so much
  ( 'global_connection_limit', 800,
    "No more than this many connections to peers may be opened ever, regardless of how many torrents there are" )
] )

#How many peer connections to put on a single circuit by default.
#More than this might be added if we hit our max circuits per application limit
PREFERRED_STREAMS_PER_CIRCUIT = 3

class BitTorrentClientSettings(ApplicationSettings.ApplicationSettings):
  """Saves/loads/sets settings for BitTorrent client"""
  DISPLAY_NAME = "BitTorrent"
  def __init__(self):
    ApplicationSettings.ApplicationSettings.__init__(self)
    #: for modifying the registry
    self.torrentHandlerDeferred = None
    #: Windows registry key name:
    self.KEY_NAME = "BitBlinder"
    #normal settings attributes
    self.add_attribute("useTor", True, "bool", "Be Anonymous?", "Only uncheck this if you want the program to connect directly to the Internet.  This option is mostly for trouble-shooting.")
#    self.add_attribute("showedOutOfMoneyHint", False, "bool",  "Have you been told that the x button just closes the window?", "", isVisible=False)
    self.add_attribute("toldAboutStatusIcon", False, "bool",  "Have you been told that the x button just closes the window?", "", isVisible=False)
    self.add_attribute("askAboutRegistry", True, "bool", "Check Registry on Startup", "Check if BitBlinder is the default handler for .torrent files whenever BitBlinder starts up.", isVisible=System.IS_WINDOWS)
    self.add_attribute("beDefaultTorrentProgram", True, "bool", "Use BitBlinder as the default .torrent program", "Whether double-clicking on a .torrent file should launch BitBlinder.", isVisible=System.IS_WINDOWS)
    self.add_attribute("port", 6951, Globals.PORT_RANGE, "Port", "Which port to use for incoming BitTorrent connections.  Set to 0 to use a random port.")
    self.add_attribute("torrentFolder", Globals.TORRENT_FOLDER, "folder", "Default folder", "Location to store downloads by default.")
    self.add_attribute("scanFolder", Globals.TORRENT_FOLDER, "folder", "Auto-Add folder", "BitBlinder will automatically start downloading any torrents saved in this folder.")
    self.add_attribute("waitForTrackerShutdownAnnounce", False, "bool", "Wait for tracker shutdown announce?", "Should BitBlinder wait until it successfully sends an announce to trackers when anonymity levels change or when it is closed?  This may take a while, so if you aren't using a private tracker, you probably don't care.")
    for mode in ("Normal", "Anonymous"):
      if mode == "Anonymous":
        modeStr = "_anon"
        multiplier = 1
      else:
        modeStr = ""
        multiplier = 2
      self.add_attribute("max_download_rate"+modeStr, 500*multiplier, "KBps", "Max Download Speed", "Maximum download speed for BitTorrent downloads (0 means no limit).", category=mode)
      self.add_attribute("max_upload_rate"+modeStr, 500*multiplier, "KBps", "Max Upload Speed", "Maximum upload speed for BitTorrent downloads (0 means no limit).", category=mode)
      self.add_attribute("max_initiate_per_second"+modeStr, 1, (1,6), "Connections Per Second", "Maximum new connections to make per second.", category=mode)
      self.add_attribute("max_half_open"+modeStr, 20*multiplier, (1,100), "Max Half-Open Connections", "Maximum number of peers to try connecting to at once.", category=mode)
      self.add_attribute("min_peers"+modeStr, 30*multiplier, (1,300), "Min Peers", "If we have at least this many peers, dont bother pinging the tracker.", category=mode)
      self.add_attribute("max_initiate"+modeStr, 40*multiplier, (1,300), "Max Peers", "If we are connected to at least this many peers, stop making more outgoing connections.", category=mode)
      self.add_attribute("min_uploads"+modeStr, 3*multiplier, (1,30), "Min Upload Slots", "Upload to at least this many peers at once.", category=mode)
      self.add_attribute("max_uploads"+modeStr, Globals.MAX_OPEN_CIRCUITS*multiplier, (1,30), "Max Upload Slots", "Upload to at most this many peers at once.", category=mode)    
    
  #: see parent
  def on_apply(self, app, category):
    if category == "Normal":
      if not self.useTor and app.is_running():
        app.restart()
    elif category == "Anonymous":
      if self.useTor and app.is_running():
        app.restart()
    else:
      #this handles the anonymity settings (number of hops, etc)
      ApplicationSettings.ApplicationSettings.on_apply(self, app, category)
      self.register_file_handler(self.beDefaultTorrentProgram)
      if not os.path.exists(self.torrentFolder):
        os.makedirs(self.torrentFolder)
      if not os.path.exists(self.scanFolder):
        os.makedirs(self.scanFolder)
      #if the listening port was changed
      if app.btInstance and app.btInstance.listen_port != self.port and self.port != 0:
        #have to restart BitTorrent:
        app.restart()
    return True
    
  def apply_anon_mode(self, app):
    """Toggle which anonymity mode (how many hops) we are currently using, restart applications as necessary."""      
    if self.useTor != app.useTor or self.pathLength != app.pathLength:
      app.useTor = self.useTor
      app.pathLength = self.pathLength
      if app.is_ready():
        app.restart()
      self.save()
      if self.useTor:
        BitBlinder.get().start()
      GlobalEvents.throw_event("settings_changed")
      
  def query_file_handler(self):
    """Check if BitBlinder is the default file handler for .torrent files on windows
    @return:  bool"""
    if not System.IS_WINDOWS:
      return True
    try:
      #check the global association:
      torrentKey = _winreg.OpenKey(_winreg.HKEY_CLASSES_ROOT,".torrent", 0, _winreg.KEY_READ)
      vals = _winreg.QueryValueEx(torrentKey, "")
      assert vals, "registry key does not exist:  HKEY_CLASSES_ROOT/.torrent"
      assert vals[0] == self.KEY_NAME, "bad key name for registry entry (%s instead of %s)" % (vals[0], self.KEY_NAME)
      _winreg.CloseKey(torrentKey)
      #check the user association:
      torrentKey = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, "Software\\Classes\\.torrent", 0, _winreg.KEY_READ)
      vals = _winreg.QueryValueEx(torrentKey, "")
      assert vals, "registry key does not exist:  HKEY_CURRENT_USER/Software/Classes/.torrent"
      assert vals[0] == self.KEY_NAME, "bad key name for registry entry (%s instead of %s)" % (vals[0], self.KEY_NAME)
      _winreg.CloseKey(torrentKey)
      #check the explorer association:
      torrentKey = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\.torrent", 0, _winreg.KEY_READ)
      vals = _winreg.QueryValueEx(torrentKey, "Progid")
      assert vals, "registry key does not exist:  HKEY_CURRENT_USER/Software/Microsoft/Windows/CurrentVersion/Explorer/FileExts/.torrent"
      assert vals[0] == self.KEY_NAME, "bad key name for registry entry (%s instead of %s)" % (vals[0], self.KEY_NAME)
      _winreg.CloseKey(torrentKey)
      return True
    except (AssertionError, OSError), e:
      log_msg("Did not detect registry keys:  %s" % (e))
      return False
  
  def register_file_handler(self, newVal):
    """Associate BitBlinder with .torrent files in the Windows registry.
    @param newVal:  whether we should be the default handler or not
    @type  newVal:  bool
    """
    if not System.IS_WINDOWS:
      return
    if self.query_file_handler() == newVal:
      if self.torrentHandlerDeferred:
        log_msg("Failed to become default .torrent handler, already editing the registry!", 0)
      return
    if self.torrentHandlerDeferred:
      return
    def uac_done(result):
      self.torrentHandlerDeferred = None
      if result != True:
        log_ex(result, "Bad result while running BitBlinderSettingsUpdate.exe")
    #launch the program:
    if newVal:
      args = " --add-torrent=" + ClientUtil.get_launch_command()
    else:
      args = " --remove-torrent"
    encodedBin = System.encode_for_filesystem(Globals.WINDOWS_BIN)
    self.torrentHandlerDeferred = SerialProcessLauncher.get().run_app(os.path.join(encodedBin, "BitBlinderSettingsUpdate.exe /S" + args))
    self.torrentHandlerDeferred.addCallback(uac_done)
    self.torrentHandlerDeferred.addErrback(uac_done)
    
  def generate_config(self):
    """Generate the config in BitTornado format"""
    #create the new config:
    config = {}
    #copy the defaults
    for entry in defaults:
      config[entry[0]] = entry[1]
    #NOTE:  this is a little bit meta.  Different settings are used depending on if you are anonymous or not
    if self.useTor:
      config['use_socks'] = 1
      modifier = "_anon"
    else:
      config['use_socks'] = 0
      modifier = ""
    for var in ('max_download_rate', 'max_upload_rate', 'max_initiate_per_second', 'max_half_open', 'min_peers', 'max_initiate', 'max_uploads', 'min_uploads'):
      config[var] = getattr(self, var+modifier)    
    config['max_connections'] = getattr(self, "max_initiate"+modifier)
    #where to save local dht data:
    config['dht_file_name'] = os.path.join(Globals.USER_DATA_DIR, "local_dht.table")
    #if the port is 0, it means pick a random one
    if self.port == 0:
      config['minport'] = 10000
      config['maxport'] = 65535
      config['random_port'] = 1
    else:
      config['random_port'] = 0
      config['minport'] = self.port
      config['maxport'] = self.port
    #because 20 seconds is just too long to aggregate bw data:
    config['max_rate_period'] = 5.0
    config['http_timeout'] = 30.0
    config['spew'] = 1
    return config
      
#TODO:  merge LaunchMany with this
class BitTorrentClient(BitBlinder.BitBlinderApplication, GeneratorMixin.GeneratorMixin):
  """Application wrapper class for BitTorrent.  Use this to start/stop/etc"""
  def __init__(self, torApp):
    BitBlinder.BitBlinderApplication.__init__(self, "BitTorrent", BitTorrentClientSettings, "A BitTorrent client!", torApp, Bank.get())
    #: whether to proxy our communications or not
    self.useTor = self.settings.useTor
    #: our GTK display, if we have one
    self.display = None
    #because it's always installed...
    self.appBasePath = ""
    self.isInstalled = True
    #: the BitTornado object that represents the "application" when this is running
    self.btInstance = None
    #: maps from hash -> details about the downloads that are waiting for Tor before they can start up
    self.pendingDownloads = {}
    #: simple cache of .torrent data (keys are the infohashes)
    self.TorrentDataBuffer = {}
    try:
      #a bunch of locations to store info about current torrents.  Taken from BitTornado
      self.dir_datacache = os.path.join(Globals.USER_DATA_DIR, ".dataCache")
      if not os.path.exists(self.dir_datacache):
        os.mkdir(self.dir_datacache)
      self.dir_piececache = os.path.join(Globals.USER_DATA_DIR, ".pieceCache")
      if not os.path.exists(self.dir_piececache):
        os.mkdir(self.dir_piececache)
      self.dir_torrentcache = os.path.join(Globals.USER_DATA_DIR, ".torrentCache")
      if not os.path.exists(self.dir_torrentcache):
        os.mkdir(self.dir_torrentcache)
      #and some of our own folders:
      if not os.path.exists(self.settings.torrentFolder):
        os.makedirs(self.settings.torrentFolder)
      if not os.path.exists(self.settings.scanFolder):
        os.makedirs(self.settings.scanFolder)
    except (OSError), e:
      GUIController.get().show_msgbox("Cannot access folder:  %s\nPlease make the folder accessible!" % (e))
    #queue any torrents that were running
    self.resume_torrents()
    #: start scanning for any torrent files:
    self.scan_event = Scheduler.schedule_repeat(30.0, self.scan_folder)
    log_msg("Started scan folder event", 0)
    #: whether everything is paused
    self.paused = False
    #: whether BitTorrent has been started yet during this run
    self.startedOnce = False
    #: set a status message for all torrents
    self.forcedStatus = ""
    #: torrents that are paused
    self.previouslyPaused = {}
    #need to handle startup arguments:
    self.catch_event("new_args")
    self.catch_event("settings_changed")
    #add us to the list of known applications:
    BitBlinder.KNOWN_APPLICATIONS.append(self.name)
    
  def set_display(self, display):
    self.display = display
    
  def get_status(self):
    statusString = Application.Application.get_status(self)
    if self.btInstance:
      statusString += " numTorrents=%s" % (len(self.btInstance.downloads))
    return statusString
    
  def on_settings_changed(self):
    if self.useTor:
      #check that we ARE an app in BB:
      if self.name not in BitBlinder.get().applications:
        BitBlinder.get().add_application(self)
    else:
      #check that we are NOT an app in BB:
      if self.name in BitBlinder.get().applications:
        BitBlinder.get().remove_application(self)
        
  def on_pause(self):
    if not self.is_ready():
      return
    #pause each of our torrents.
    self.previouslyPaused = {}
    for hash, download in self.btInstance.downloads.iteritems():
      if download.unpauseflag.isSet():
        download.Pause()
      else:
        self.previouslyPaused[hash] = True
    #set a status message for all torrents
    self.forcedStatus = "Waiting For More Credits..."
    #TODO:  need a global view of credits
      
  def on_unpause(self):
    if not self.is_ready():
      return
    #unpause each of our torrents.f
    for download in self.btInstance.downloads.values():
      #if the torrent is not running
      if not download.unpauseflag.isSet():
        #and it WAS running before
        if not self.previouslyPaused.has_key(hash):
          download.Unpause()
    self.previouslyPaused = {}
    #set a status message for all torrents
    self.forcedStatus = ""

  def on_new_args(self, startingDir, options, args):
    #if we're shutting down, ignore any incoming arguments:
    if self.is_stopping():
      return
    file = options.torrent
    #if there is a file, we definitely have to start:
    if file:
      options.launch_bt = True
    #this means we're supposed to start at startup:
    if options.launch_bt:
      self.start()
    #is there a torrent to handle?
    if not file:
      return
    #make sure the argument file path is absolute
    if not os.path.isabs(file):
      file = os.path.join(startingDir, file)
    #add the torrent:
    self.load_torrent(file)
    
  def scan_folder(self):
    """Called periodically.  Scans the scanFolder to look for any .torrent files that are not currently being downloaded."""
    if not self.is_ready():
      return True
    log_msg("Scanning %s" % (self.settings.scanFolder), 4)
    regex = re.compile("^.*\\.torrent$")
    try:
      if self.settings.scanFolder and os.path.exists(self.settings.scanFolder):
        for root, dirs, files in os.walk(self.settings.scanFolder):
          for name in files:
            if regex.match(name):
              #check if we are downloading this exact torrent:
              ignoreFile = False
              for download in self.btInstance.downloads.values():
                if os.path.abspath(download.rawTorrentData['path']) == os.path.abspath(os.path.join(self.settings.scanFolder, name)):
                  ignoreFile = True
                  break
              if ignoreFile:
                continue
              #check if it is the same torrent (by reading and hashing the torrent file)
              data, hash = read_torrent(os.path.join(root, name))
              i = data['metainfo']['info']
              if self.btInstance and self.btInstance.downloads.has_key(hash):
                continue
              numFiles = 1
              if i.has_key('length'):
                pass
              elif i.has_key('files'):
                numFiles = len(i['files'])
              saveAsFile = os.path.join(self.settings.torrentFolder, i['name'])
              self.add_torrent(hash, data, saveAsFile, ",".join(["1"]*numFiles))
          #because we dont need to be loading torrents from in subfolders
          break
    except Exception, e:
      log_ex(e, "Scan folder ran into an error")
    return True
    
  #TODO:  should really separate the circuit building policy stuff for single IP vs throughput
  def on_update(self):
    Application.Application.on_update(self)

  #BitTorrent circuit building policy is roughly to evenly distribute Streams amongst Circuits
  def find_or_build_best_circuit(self, host="", port=0, ignoreList=None, force=False, protocol="TCP"):
    """Find the best Circuit to exit to host:port (or if none exists, build one).
    BitTorrent circuit building policy is roughly to evenly distribute Streams amongst Circuits.
    @param host:  the circuit must be able to exit to this host
    @type host:   hostname or IP address
    @param port:  the circuit must be able to exit to this port
    @type port:   int
    @param ignoreList:  a list of Circuits to ignore
    @type ignoreList:   list
    @param force:  True if you don't care about violating MAX_OPEN_CIRCUITS.  Might return None anyway for other reasons (paused, Tor dead, out of credits, no exits
    @type force:   bool
    @param protocol:  the type of traffic to be sent from the exit.
    @type protocol:  string (TCP or DHT)
    @return:  the Circuit, or None if it is not possible."""
    if not ignoreList:
      ignoreList = []
    #get all possible circuits:
    allowableCircuits = []
    for c in self.liveCircuits:
      #these are the things that determine whether a circuit is useful right now or not:
      circuitReady = c.is_ready() or c.is_launching()
      shouldIgnore = c in ignoreList
      willAllowExit = c.will_accept_connection(host, port, protocol)
      #is this a candidate circuit?
      if willAllowExit and circuitReady and not shouldIgnore:
        allowableCircuits.append(c)
    #filter out circuits that exit from the wrong country, if we care about that sort of thing:
    if self.exitCountry:
      allowableCircuits = [c for c in allowableCircuits if c.get_exit().desc.country == self.exitCountry]
    #how many circuits are we in the process of opening?
    numOpeningCircs = 0
    for c in self.liveCircuits:
      if c.is_launching():
        numOpeningCircs += 1
    #how many circuits are at capacity already?
    numCircsWithExtraCapacity = 0
    for c in allowableCircuits:
      if c.num_active_streams() < PREFERRED_STREAMS_PER_CIRCUIT:
        numCircsWithExtraCapacity += 1
    #some circuits have space yet, no need for more
    openingTooManyCircs = numOpeningCircs >= 2
    isSpareCapacity = numCircsWithExtraCapacity > 0
    if not isSpareCapacity and not openingTooManyCircs:
      circ = self.build_circuit(host, port, isFast=True, force=force, protocol=protocol)
      if circ:
        allowableCircuits = [circ]
    #if there are no possible circuits, open a new one:
    if len(allowableCircuits) <= 0:
      circ = self.build_circuit(host, port, isFast=True, force=force, protocol=protocol)
      if circ:
        allowableCircuits = [circ]
      else:
        return None
    #pick the best of the available circuits:
    best = allowableCircuits[0]
    for i in range(1,len(allowableCircuits)):
      best = self._compare_circuits(allowableCircuits[i], best)
    log_msg("%d looks like the best circuit for %s:%d" % (best.id, Basic.clean(host), port), 4, "stream")
    return best
    
  def _compare_circuits(self, circ1, circ2):
    """Used to rank which Circuit is the best to accept a new stream.
    @returns:  whichever circuit is better"""
    if circ1.is_ready() and not circ2.is_ready():
      return circ1
    if circ2.is_ready() and not circ1.is_ready():
      return circ2
    if circ1.num_active_streams() < circ2.num_active_streams():
      return circ1
    return circ2
    
  def registry_dialog_cb(self, response, alwaysPrompt):
    """Handle response from the dialog asking about preferences for .torrent file handling
    @param response:  yes or no
    @type  response:  str
    @param alwaysPrompt:  whether to always check .torrent handling status
    @type  alwaysPrompt:  bool"""
    log_msg("registry dialog:  %s, %s" % (response, alwaysPrompt), 3, "gui")
    self.settings.beDefaultTorrentProgram = response == "yes"
    self.settings.askAboutRegistry = alwaysPrompt
    #change the registry if necessary:
    self.settings.register_file_handler(self.settings.beDefaultTorrentProgram)
    self.settings.save()
    
  def launch_initial_circuits(self):
    if self.useTor:
      circ = self.find_or_build_best_circuit(port=6969)
      circ = self.find_or_build_best_circuit(port=80)

  def is_ready(self):
    if self.is_starting() or self.is_stopping():
      return False
    if self.btInstance:
      return True
    return False
    
  def exit(self):
    """kills btInstance one way or the other- 
    if the user wants to wait for tracker shutdown, we try to do that first
    otherwise, we just force kill it"""
    #if the user wants to wait on shutdown announce...
    if self.settings.waitForTrackerShutdownAnnounce:
      shutdownDeferredList = self.btInstance.quit(force=False)
      if self.display:
        self.display.show_tracker_shutdown_prompt()
      return shutdownDeferredList
    shutdownDeferredList = self.btInstance.quit(force=True)
    return shutdownDeferredList
    
  def force_stop(self):
    """Just trigger all of the tracker stop events so that we dont wait for them.
    Will still be waiting for UPnP unbind or whatever."""
    #if we've already finished stopping, just return
    if not self.btInstance:
      return
    #make sure we're actually stopping
    if not self.is_stopping():
      self.stop()
    #then stop worrying about tracker events
    if self.btInstance:
      self.btInstance.quit(force=True)
        
  def stop_done(self):
    Application.Application.stop_done(self)
    if self.display: 
      self.display.hide_tracker_shutdown_prompt()
    del self.btInstance
    self.btInstance = None
    self.stop_gui()
    
  def launch_dependencies(self):
    if self.display:
      self.display.freeze()
    if self.useTor:
      return defer.DeferredList([BitBlinder.get().start(), Bank.get().start()])
    else:
      return defer.succeed(True)
  
  def launch(self):
    #build some initial Circuits
    if len(self.liveCircuits) <= 0 and self.useTor:
      self.launch_initial_circuits()
    #enqueue any torrents that were running
    self.resume_torrents()
    #make the base configuration:
    config = self.settings.generate_config()
    #start the BT engine:
    self.btInstance = LaunchMany(config, self.display, self.settings.useTor)
    #start any torrents that were queued:
    for hash, data in self.pendingDownloads.iteritems():
      self.add_torrent(hash, *data)
    self.pendingDownloads = {}
    self.start_gui()
    if not self.startedOnce:
      self.startedOnce = True
      #see if we should register ourselves to handle .torrent files
      if not self.settings.query_file_handler():
        #dont show on the first run because it's a duplicate question
        if self.settings.askAboutRegistry and RegistryDialog:
          self.dialog = RegistryDialog.RegistryDialog(self.name, self.display, ".torrent", self.registry_dialog_cb)
        elif self.settings.beDefaultTorrentProgram:
          self.settings.register_file_handler(True)
    return defer.succeed([])
    
  def start_gui(self):
    if self.display:
      self.display.start()
      self.display.unfreeze()
      
  def stop_gui(self):
    if self.display:
      self.display.freeze()
      #keep the gui around if we are restarting (ie, changing path length)
      if not self.isRestarting:
        self.display.stop()
  
  def load_torrent(self, file):
    """Given a torrent file, validate that it exists, etc, then prompt the user for where to save it, etc
    @param file:  the file to load
    @type  file:  filename"""
    ignoreError = False
    try:
      if not os.path.exists(file):
        ignoreError = True
        raise Exception("File doesnt exist!")
      if not re.compile("^.*\.torrent$").match(file):
        ignoreError = True
        raise Exception("File is not a .torrent file?")
      data, hash = read_torrent(file)
    except Exception, e:
      if not ignoreError:
        log_ex(e, "Failed to load torrent")
      GUIController.get().show_msgbox("Could not load torrent: %s" % (repr(e)))
      return
    if self.display:
      self.display.do_priority_prompt(hash, data)
    else:
      self.add_torrent(hash, data, os.path.join(self.settings.torrentFolder, data['metainfo']['info']['name']), "")
    
  def add_torrent(self, hash, torrentData, saveAsFile, priority):
    """Start downloading a .torrent right now.
    @param hash:  the torrent infohash
    @type  hash:  str (infohash)
    @param torrentData:  all information from the torrent file (unbencoded), plus metadata
    @type  torrentData:  dictionary
    @param saveAsFile:  where to save the data for the torrent
    @type  saveAsFile:  filename
    @param priority:  how to prioritize the pieces of the .torrent
    @type  priority:  str (comma delineated list of priorities (ints -1 thorugh 2))"""
    #if the app isnt running yet, add to the list of pending downloads
    if not self.btInstance:
      self.pendingDownloads[hash] = [torrentData, saveAsFile, priority]
      return
    #make sure the folder exists:
    pathName, fileName = os.path.split(saveAsFile)
    try:
      if not os.path.exists(pathName):
        os.makedirs(pathName)
    except Exception, e:
      GUIController.get().show_msgbox("Failed to create folders for torrent:  %s" % (e))
      return
    #actually add the torrent to the engine
    d = self.btInstance.add(hash, torrentData)
    #will not return the download unless it was newly added.
    if not d:
      #In that case, all set, just return
      return
    d.config['priority'] = priority
    d.config['saveas'] = saveAsFile
    torrentData['priority'] = priority
    torrentData['saveas'] = saveAsFile
    d.rawTorrentData = torrentData
    d.start()
    #make a priority interface for it:
    if ProgramState.USE_GTK:
      d.priorityInterface, d.peerInterface = self.display.make_torrent_displays(d, torrentData, priority)
    #save it to disk:
    self.save_torrent_data(torrentData)
    if self.paused:
      #pause the torrent by default, since we are globally paused
      d.Pause()
      
  #save it to disk:
  def save_torrent_data(self, torrentData):
    hash = sha1(bencode(torrentData['metainfo']['info'])).digest()
    t = tohex(hash)
    f = open(os.path.join(self.dir_torrentcache,t),'wb')
    f.write(bencode(torrentData))
    f.close()
    
  def remove_download(self, hash, removeTorrent, removeData):
    """Stop downloading a torrent
    @param hash:  which torrent to stop
    @type  hash:  infohash
    @param removeTorrent:  whether to delete the .torrent file associated with this download
    @type  removeTorrent:  bool
    @param removeData:  whether to delete the data associated with this download
    @type  removeData:  bool"""
    error = None
    try:
      if not self.btInstance.downloads.has_key(hash):
        error = "The download was already deleted?"
      elif not self.is_ready():
        error = "The app is not ready."
      else:
        download = self.btInstance.downloads[hash]
        dataFileName = download.getFilename()
        #remove from BitTorrent
        self.btInstance.remove(hash)
        #remove from the folder that stores our current downloads
        self.deleteCachedTorrent(hash)
        if not dataFileName:
          error = "The download was never started?"
        else:
          torrentFileName = download.rawTorrentData['path']
#          log_msg("%s:  %s" % (torrentFileName, dataFileName))
          #remove any data downloaded so far, if requested:
          if removeData:
            self.deleteTorrentData(hash)
            if os.path.isfile(dataFileName):
              os.remove(dataFileName)
            else:
              shutil.rmtree(dataFileName, False)
          #remove the original torrent file, if requested:
          if removeTorrent:
            if os.path.isfile(torrentFileName):
              os.remove(torrentFileName)
          #make sure the priority interface is gone if necessary:
          if self.display:
            if self.display.curDownload == download:
                self.display.set_priority_box(None)
                self.display.set_peer_box(None)
    except (OSError), e:
      error = repr(e)
    if error:
      GUIController.get().show_msgbox("Failed to delete torrent:  %s" % (error))
        
  def getTorrentData(self, torrent):
    """Called to get the .torrent file contents.  Retrieves from our own cache of the data.
    @param torrent:  which torrent to get data for
    @type  torrent:  infohash
    @return:  None or the .torrent data dictionary"""
    if torrent in self.TorrentDataBuffer:
      return self.TorrentDataBuffer[torrent]
    torrent = os.path.join(self.dir_datacache, tohex(torrent))
    if not os.path.exists(torrent):
      return None
    try:
      file = open(torrent,'rb')
      torrentData = bdecode(file.read())
    except:
      torrentData = None
    try:
      file.close()
    except:
      pass
    self.TorrentDataBuffer[torrent] = torrentData
    return torrentData

  def writeTorrentData(self, torrent, data):
    """Insert torrent data into our cache by hexencoding the infohash and using that for the filename
    @param torrent:  which torrent to insert
    @type  torrent:  infohash
    @param data:  the torrent data
    @type  data:  dictionary"""
    self.TorrentDataBuffer[torrent] = data
    try:
      f = open(os.path.join(self.dir_datacache, tohex(torrent)),'wb')
      f.write(bencode(data))
      success = True
    except:
      success = False
    try:
      f.close()
    except:
      pass
    if not success:
      self.deleteTorrentData(torrent)
    return success
  
  def deleteCachedTorrent(self, torrent):
    """Remove a torrent from our torrent cache
    @param torrent:  which torrent to delete
    @type  torrent:  infohash"""
    try:
      os.remove(os.path.join(self.dir_torrentcache,tohex(torrent)))
    except:
      pass

  def deleteTorrentData(self, torrent):
    """Remove a torrent from our data cache
    @param torrent:  which torrent to delete
    @type  torrent:  infohash"""
    try:
      os.remove(os.path.join(self.dir_datacache,tohex(torrent)))
    except:
      pass

  def getPieceDir(self, torrent):
    """Get the directory to store piece files for a given torrent.
    @param torrent:  which torrent to delete
    @type  torrent:  infohash
    @return:  foldername"""
    return os.path.join(self.dir_piececache,tohex(torrent))
        
  def send_tracker_request(self, query, timeout, successCB, failureCB):
    """Send a request to a tracker through BitBlinder.  Handles anonymization of the request.
    @param query:  the the tracker to connect to
    @type  query:  str (URL)
    @param timeout:  how long to wait for a response before assuming that it failed
    @type  timeout:  float (seconds) or None
    @param successCB:  will be called if the tracker request succeeds
    @type  successCB:  function
    @param failureCB:  will be called if the tracker request succeeds
    @type  failureCB:  function
    @returns:  the HTTPDownload instance for this request"""
    #if we can send the request out directly:
    if not self.useTor:
      download = BitBlinder.http_download(query, None, successCB, failureCB, timeout=timeout)
    #otherwise we have to proxy the traffic
    else:
      #figure out the host and destination that we'll need to exit to:
      m = re.compile("^https?://(.+?)/.*$").match(query)
      if not m:
        failureCB("Could not determine host and port for tracker:  %s" % (query))
        return
      exitHost = m.group(1)
      exitPort = 80
      if ":" in exitHost:
        exitPort = int(exitHost.split(":")[1])
        exitHost = exitHost.split(":")[0]
      circ = self.find_or_build_best_circuit(exitHost, exitPort, force=True)
      if not circ:
        failureCB("Could not create a circuit to connect to the tracker (%s), failing..." % (query))
        return
      #currently, the exit relay takes no incoming request, so set a random high lvl port so that the exit relay
      #looks like a newb- also adds plausible deniability for the relays personal, non-forwarded torrenting
      port = 1024 + random.randint(0, 65535 - 1024)
      newQuery = alter_query(query, None, port)
      download = BitBlinder.http_download(newQuery, circ, successCB, failureCB, timeout=timeout)
    return download
         
  def resume_torrents(self):
    """Begin downloading all the torrents that we were downloading when BitTorrent was last run"""
    for file in os.listdir(self.dir_torrentcache):
      fileName = os.path.join(self.dir_torrentcache, file)
      hash = unhex(file)
      f = open(fileName, "rb")
      data = bdecode(f.read())
      f.close()
      saveAsFile = unicode(data['saveas'])
      priority = data['priority']
      self.add_torrent(hash, data, saveAsFile, priority)

def alter_query(query, ip, port):
  """Change a tracker request query string to filter out our IP address and port and replace it with those specified
  @param query:  the the tracker URL to connect to
  @type  query:  str (URL)
  @param ip:  use this instead of the IP in the query
  @type  ip:  str (IP address)
  @param port:  use this instead of the port in the query
  @type  port:  int"""
  #change the request args appropriately:
  if "?" not in query:
    return query
  tracker, query = query.split("?", 1)
  args = parse_qs(query)
  #remove any IP address that could be getting sent to the tracker, so we dont reveal our identity
  if args.has_key("ip"):
    if ip != None:
      args["ip"] = [ip]
    else:
      del args["ip"]
  #insert the port that they have forwarded on our behalf:
  if args.has_key("port"):
    args["port"] = [str(port)]
  #NOTE:  we were doing this before, and it actually found other clients sometimes.  I wonder what other clients made the same mistake...
  #query = "&".join(urllib.urlencode({key : val[0]}) for key, val in args.iteritems())
  query = "&".join(key + "=" + urllib.quote(val[0]) for key, val in args.iteritems())
  return tracker + "?" + query

