#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Application class to track streams/circuits launched by BitBlinder"""

import sys
import os
try:
  import _winreg
except:
  pass
from twisted.internet import defer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common.utils import Format
from common.system import System
from common.system import Process
from common.Errors import DependencyError
from common.classes import SerialProcessLauncher
from common import Globals
from core.network import InstanceFactory
from core.network.socks import Client
from core.tor import Stream
from core import ClientUtil
from core import HTTPClient
from Applications import SocksApp
from Applications import Application
from Applications import ApplicationSettings
  
_instance = None
def get():
  return _instance
  
def start(torApp, bankApp):
  global _instance
  if not _instance:
    _instance = BitBlinder(torApp, bankApp)
    
def stop():
  if _instance:
    d = _instance.stop()
    return d
  return defer.succeed(True)
  
def http_download(url, circ, successCB, failureCB=None, progressCB=None, fileName=None, timeout=None):
  download = HTTPClient.HTTPDownload(_instance, url, circ, successCB, failureCB, progressCB, fileName, timeout)
  return download
  
#: a list of the applications that we bundle with BitBlinder
KNOWN_APPLICATIONS = []

class BitBlinderSettings(ApplicationSettings.ApplicationSettings):
  #: name of the xml settings file 
  defaultFile = "BitBlinderSettings.ini"
  #: Name in settings dialog
  DISPLAY_NAME = "Advanced"
  #: the registry key name
  KEY_NAME = "BitBlinder"
  def __init__(self):
    ApplicationSettings.ApplicationSettings.__init__(self)
    #because we only want to call this once...
    self.appliedHalfOpenCorrection = False
    if System.IS_WINDOWS:
      winInfo = sys.getwindowsversion()
      #if this is win7 or vista SP2 or higher, we're all set:
      if winInfo[0] == 7 or (winInfo[0] == 6 and winInfo[4] not in ('', 'Service Pack 1')):
        halfOpenHelp = "There is no need to enable this option--your platform has a working half-open connection limit."
        halfOpenDefault = False
      else:
        halfOpenDefault = True
        if winInfo[0] == 6:
          halfOpenHelp = "UPGRADE TO VISTA SERVICE PACK 2.  Otherwise, you MUST enable this (unless you have fixed the half open connection limit in TCPIP.sys yourself)"
        else:
          halfOpenHelp = "You MUST enable this (unless you have fixed the half open connection limit in TCPIP.sys yourself)"
        halfOpenHelp += "  TCPZ will safely increase the limit to 220 in memory.  Restarting your computer will undo the change."
    else:
      halfOpenHelp = "There is no need to enable this option--your platform has a working half-open connection limit."
      halfOpenDefault = False
    self.add_attribute("halfOpenConnections", halfOpenDefault, "bool",  "Fix half-open connection limit?", halfOpenHelp, isVisible=System.IS_WINDOWS)
    self.add_attribute("startBitBlinderOnBoot", False, "bool",  "Start BitBlinder on startup", "Should BitBlinder launch when your computer starts?  Currently only works for Windows.", isVisible=System.IS_WINDOWS)
    self.add_attribute("toldAboutStatusIcon", False, "bool",  "Have you been told that the x button just closes the window?", "", isVisible=False)
    self.add_attribute("alwaysShowPovertyDialog", True, "bool",  "Whether to show the 'out of credits' dialog when you run out of credits", "", isVisible=False)
    #: so that it only runs once at a time
    self.startOnBootDeferred = None
    return
  
  def on_apply(self, app, category):
    try:
      self.set_start_on_boot(self.startBitBlinderOnBoot)
      self.set_half_open_conns(app, self.halfOpenConnections)
#      #TEMP:  re-enable this
#      self.apply_anon_mode()
    except Exception, e:
      log_ex(e, "Failed to apply settings:")
      return False
    return True
  
  def check_start_on_boot(self):
    """Check for the registry key for auto launching BitBlinder at startup on windows, does nothing on *nix
    @return:  True if the registry key exists, False otherwise"""
    if not System.IS_WINDOWS:
      return False
    #all values in the registry for the handle e
    vals = []
    i = 0
    try:
      handle = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "Software\\Microsoft\\Windows\\CurrentVersion\\run", 0, _winreg.KEY_READ)
    except WindowsError, e:
      return False
    try:
      while 1:
        name, value, type = _winreg.EnumValue(handle, i)
        vals.append(name)
        i += 1
    except WindowsError, e:
      log_msg("Finished looking for our key in startup reg entries:  %s" % (e), 4)
      #finally, close the key:
      _winreg.CloseKey(handle)
    #return whether the key exists
    return self.KEY_NAME in vals
    
  def set_start_on_boot(self, newVal):
    """Change the registry key (if necessary) for auto launching BitBlinder at startup on windows, does nothing on *nix.
    Ends up calling a function made with NSIS that will get the necessary permissions to do the modification
    @param newVal:  whether to start on boot or not
    @type  newVal:  bool"""
    if not System.IS_WINDOWS:
      return
    #No need to change if the value is already correct?
    if self.check_start_on_boot() == newVal:
      if self.startOnBootDeferred:
        log_msg("Failed to modify 'start at bootup' value, already editing the registry!", 0)
      return
    if self.startOnBootDeferred:
      return
    def uac_done(result):
      self.startOnBootDeferred = None
      if result != True:
        log_ex(result, "Bad result while running BitBlinderSettingsUpdate.exe")
    #launch the program:
    if newVal:
      args = " --add-startup=" + ClientUtil.get_launch_command()
    else:
      args = " --remove-startup"
      
    encodedExe = System.encode_for_filesystem(os.path.join(Globals.WINDOWS_BIN, "BitBlinderSettingsUpdate.exe"))
    self.startOnBootDeferred = SerialProcessLauncher.get().run_app(encodedExe + "  /S" + args)
    self.startOnBootDeferred.addCallback(uac_done)
    self.startOnBootDeferred.addErrback(uac_done)
    
  def set_half_open_conns(self, app, halfOpenConnections):
    """uses tcpz to change the number of half open connections to 218"""
    try:
      #this is a windows specific fix:
      if not System.IS_WINDOWS:
        return
      #also, this is only necessary if we are acting as a Tor server:
      if not app.torApp.settings.beRelay:
        return
      winInfo = sys.getwindowsversion()
      #not sure if this exists, but just in case :)
      if winInfo [0] > 6:
        return
      #if this is win7, we're all set:
      if winInfo[0] == 6 and winInfo[1] >= 1:
        return
      #if this is vista, check the service pack level:
      if winInfo[0] == 6 and winInfo[1] == 0:
        #default and SP1 need fixing:
        if winInfo[4] not in ('', 'Service Pack 1'):
          return
      if halfOpenConnections:
        #if we already did this, also return:
        if self.appliedHalfOpenCorrection:
          return
        self.appliedHalfOpenCorrection = True
        #we should only ever run one tcp-z, no going back etiher
        ids = System.get_process_ids()
        for id in ids:
          if id[0] == 'tcpz.exe':
            return
        #create the vbs script file to do what we need:
        encodedScriptFile = System.encode_for_filesystem(os.path.join(Globals.USER_DATA_DIR, "tcpz.vbs"))
        encodedExe = System.encode_for_filesystem(os.path.join(Globals.WINDOWS_BIN,'tcpz.exe'))
        cmd = """Set oShell = WScript.CreateObject("WSCript.shell")\r\ncall oShell.run("cmd /c ""%s"" -limit:220 -autoexit", 0, false)\r\n""" % (encodedExe)
        f = open(encodedScriptFile, "wb")
        f.write(cmd)
        f.close()
        #and execute the script:
        SerialProcessLauncher.get().run_app('cscript.exe "%s" //B //Nologo' % (encodedScriptFile))
        return
    except Exception, e:
      log_ex(e, "Failed to launch tcpz.exe")
      
class BitBlinderApplication(SocksApp.SocksApplication):
  def __init__(self, name, settingsClass, description, torApp, bankApp):
    SocksApp.SocksApplication.__init__(self, name, settingsClass, description, torApp, bankApp)
    
  def launch_dependencies(self):
    return defer.DeferredList([get().start(), self.bankApp.start()])
    
  def add_process(self, p):
    if p not in self.processes:
      self.processes.append(p)
      get().applicationMapping[p.pid] = self
      p.d.addCallback(self._subprocess_finished, p)
      p.d.addErrback(self._subprocess_finished, p)
    
  def remove_process(self, p):
    if p in self.processes:
      self.processes.remove(p)
    if p.pid in get().applicationMapping:
      del get().applicationMapping[p.pid]
        
class BitBlinder(SocksApp.SocksApplication):
  """Represents BitBlinder (the whole application)"""
  def __init__(self, torApp, bankApp):
    #: creates the application class for Tor
    self.torApp = torApp
    #parent constructor
    SocksApp.SocksApplication.__init__(self, "BitBlinder", BitBlinderSettings, "Tracks streams launched internally.", self.torApp, bankApp)
    #maps from "host:port" -> list of [lists of the form: [handle_launch (func ptr), handle_stream (func ptr)] ]
    self.pendingStreams = {}
    #: set here because this Application creates circuits
    self.pathLength = 1
    #: if BitBlinder is running and ready or not:
    self.isReady = False
    #in case this was the first run:
    settingsFile = os.path.join(Globals.USER_DATA_DIR, torApp.settings.defaultFile)
    self.torApp.settings.fileName = settingsFile
    #list of all applications:
    self.applications = {}
    #mapping from process IDs to application:
    self.applicationMapping = {}
    #need to handle startup arguments:
    self.catch_event("new_args")
    self.catch_event("startup")
      
  def on_startup(self):
    #if they want us to change the half open conn limit:
    if not self.isFirstRun:
      if self.settings.halfOpenConnections:
        self.settings.set_half_open_conns(self, self.settings.halfOpenConnections)
    
  def get_app_by_pid(self, originalPID):
    """Return the application that controls originalPID"""
    app = None
    #if this process is unknown:
    if not self.applicationMapping.has_key(originalPID):
      ids = System.get_process_ids()
      appName = "Unknown"
      for id in ids:
        if id[1] == originalPID:
          appName = id[0]
          break
      #make sure there is an app for it:
      if appName not in self.applications:
        app = BitBlinderApplication(appName, ApplicationSettings.ApplicationSettings, "", self.torApp, self.bankApp)
        self.add_application(app)
      else:
        app = self.applications[appName]
      #and finally, add the process to the app:
      p = Process.Process(originalPID)
      app.add_process(p)
    app = self.applicationMapping[originalPID]
    return app

  def insert_app_pid(self, app, pid):
    """Note that pid is controlled by app"""
    self.applicationMapping[pid] = app
    
  def add_application(self, app):
    self.applications[app.name] = app
    
  def remove_application(self, app):
    if app.name in self.applications:
      del self.applications[app.name]
      
  def is_firefox_running(self):
    if "FirefoxPortable" in self.applications and self.applications["FirefoxPortable"].is_running():
      return True
    return False

  def get_circuit(self, id):
    """Return the Circuit corresponding to the id, or None if there is no such Circuit"""
    val = Application.Application.get_circuit(self, id)
    if val:
      return val
    for app in self.applications.values() + [self.torApp]:
      val = app.get_circuit(id)
      if val:
        return val
    return None

  def get_stream(self, id):
    """Return the Stream corresponding to the id, or None if there is no such Stream"""
    val = Application.Application.get_stream(self, id)
    if val:
      return val
    for app in self.applications.values() + [self.torApp]:
      val = app.get_stream(id)
      if val:
        return val
    return None
    
  def get_app_info(self):
    appInfos = []
    #for all socks applications:
    for app in self.applications.values():
      #ignore those that are not running
      if not app.is_running():
        continue
      #collect the necessary data
      down, up = app.get_instant_bw()
      uprate = Format.bytes_per_second(up)
      dnrate = Format.bytes_per_second(down)
      numHops = app.pathLength
      numCoins = app.coinsSpent
      appInfos.append((app.name, numHops, dnrate, uprate, numCoins))
    return appInfos
    
  def start(self):
    self.unpause()
    if self.is_ready():
      return defer.succeed(True)
    #TODO:  possibly make it auto-restart?
    if self.is_stopping():
      raise Exception("Cannot try to start BitBlinder while it is shutting down.  Please wait for shutdown to complete.")
    if not self.is_starting():
      self.insert_app_pid(self, os.getpid())
      self.startupDeferred = defer.DeferredList([self.torApp.start(), self.bankApp.start()])
      self._trigger_event("launched")
      self.startupDeferred.addCallback(self._startup_success)
      if self.startupDeferred:
        self.startupDeferred.addErrback(self._startup_failure)
      if not self.startupDeferred:
        return defer.succeed(True)
    return self.startupDeferred
      
  def _startup_success(self, result):
    self.startupDeferred = None
    self.isReady = True
    result = Basic.validate_result(result, "BitBlinder startup")
    if not result:
      self.stop()
    self._trigger_event("started")
    return result
    
  def _startup_failure(self, reason):
    self.startupDeferred = None
    log_ex(reason, "BitBlinder failed to start up!")
    return reason
  
  def is_ready(self):
    return self.isReady
    
  #NOTE:  BitBlinder can be both 'ready' and 'stopping' simultaneously
  #this is the case while waiting for applications to shutdown, some 
  #of which actually need bitblinder to be working to properly stop
  def stop(self):
    """Called when the user wants to quit the application"""
    if not self.is_running():
      return defer.succeed(True)
    if self.shutdownDeferred:
      return self.shutdownDeferred
    deferreds = []
    try:
      #actually, just close BT and FF if they're running:
      for appName in KNOWN_APPLICATIONS:
        if appName in self.applications:
          deferreds.append(self.applications[appName].stop())
    except Exception, e:
      log_ex(e, "Unhandled exception in quit")
    #wait for all of the shutdown tasks to finish, or for the timeout (in case they fail or take too long)
    log_msg("Waiting for applications to shut down...", 3)
    if deferreds:
      self.shutdownDeferred = defer.DeferredList(deferreds)
      self.shutdownDeferred.addCallback(self._on_applications_stopped)
      self.shutdownDeferred.addErrback(self._on_applications_stopped)
    else:
      self.shutdownDeferred = self._on_applications_stopped(True)
    self.shutdownDeferred.addCallback(self._on_stopped)
    if self.shutdownDeferred:
      return self.shutdownDeferred
    #in case the shutdown all happened immediately
    return defer.succeed(True)
    
  def _on_applications_stopped(self, result):
    Basic.validate_result(result, "applications_stopped")
    self.isReady = False
    HTTPClient.stop_all()
    #now stop the bank:
    log_msg("Waiting for the bank to shut down...", 3)
    d = None
    if self.bankApp:
      d = self.bankApp.stop()
    if not d:
      d = self._on_bank_stopped(True)
    else:
      d.addCallback(self._on_bank_stopped)
      d.addErrback(self._on_bank_stopped)
    return d
    
  def _on_bank_stopped(self, result):
    Basic.validate_result(result, "bank_stopped")
    #now stop tor:
    log_msg("Waiting for Tor to shut down...", 3)
    d = None
    if self.torApp:
      d = self.torApp.stop()
    if not d:
      d = self._on_tor_stopped(True)
    else:
      d.addCallback(self._on_tor_stopped)
      d.addErrback(self._on_tor_stopped)
    return d
    
  def _on_tor_stopped(self, result):
    Basic.validate_result(result, "tor_stopped")
    log_msg("BitBlinder finished.", 3)
    #finally done shutting down
    return defer.succeed(True)
      
  def _on_stopped(self, result):
    self.applications = {}
    self.applicationMapping = {}
    self.shutdownDeferred = None
    self._trigger_event("finished")
    return result
    
  def on_new_args(self, startingDir, options, args):
    #if we're shutting down, ignore any incoming arguments:
    if self.is_stopping():
      return
    if options.launch_bb:
      self.start()

  def launch_external_protocol(self, remoteHost, remotePort, protocol, streamCB, failureCB=None, id="InnomiNet External Connection"):
    """A wrapper for launch_external_factory.
    Additional parameter:
    @param failureCB:  a function to call if this protocol fails to connect
    @type  failureCB:  function
    @return:  a Deferred that will be triggered when the connection is complete"""
    f = InstanceFactory.InstanceFactory(Globals.reactor, protocol, failureCB)
    launchDefer = self.launch_external_factory(remoteHost, remotePort, f, streamCB, id)
    launchDefer.addErrback(failureCB)
    return launchDefer
  
  def launch_external_factory(self, remoteHost, remotePort, factory, cb, id="InnomiNet External Connection"):
    """Launch an outgoing TCP connection through Tor through Tor's SOCKS proxy.
    @param remoteHost:  remote host to connect to
    @type  remoteHost:  hostname or IP address
    @param remotePort:  remote port to connect to
    @type  remotePort:  int
    @param factory:  determines what Protocol will be used for the connection
    @type  factory:  ClientFactory
    @param cb:  a function to call if this protocol succeeds
    @type  cb:  function
    @param id:  used to identify the connection in error messages
    @type  id:  str
    @return:  a Deferred that will be triggered when the connection is complete"""
    if not self.is_ready():
      raise DependencyError("Cannot launch external connections, BitBlinder not ready")
    d = defer.Deferred()
    Globals.reactor.connectWith(Client.ClientConnector,
                           host=remoteHost,
                           port=remotePort,
                           sockshost="127.0.0.1",
                           socksport=self.torApp.settings.socksPort,
                          otherFactory=factory,
                          readableID=id,
                          deferred=d)
    def connect_cb(socksProtocol):
      self.handle_socks(socksProtocol, cb, failure_cb)
    def failure_cb(reason):
      log_ex(reason, "External connection failed to connect to SOCKS proxy")
    d.addCallback(connect_cb)
    d.addErrback(failure_cb)
    return d
    
  def handle_socks(self, socksProtocol, cb, failure_cb):
    """Called when a SOCKS connection is made.  Maintains the mapping between streams and original Protocols.
    @param socksProtocol:  the protocol making the socks connection
    @param cb:  called if this connection succeeds
    @type  cb:  function
    @param failure_cb:  called if this connection fails for any reason
    @type  failure_cb:  function"""
    localPort = socksProtocol.transport.getHost().port
    if self.pendingStreams.has_key(localPort):
      stream = self.pendingStreams[localPort]
      try:
        cb(stream, socksProtocol)
      except Exception, e:
        failure_cb(e)
      finally:
        del self.pendingStreams[localPort]
    else:
      self.pendingStreams[localPort] = [cb, socksProtocol, failure_cb]
      
  def on_new_stream(self, event):
    #will automatically register itself with it's application
    stream = Stream.Stream(event)
    #figure out who should handle the stream next:
    if stream.isInternal and Stream.OBSERVE_INTERNAL:
      stream.app = self.torApp
      stream.app.on_new_stream(stream)
    else:
      try:
        #first check if this was launched internally, directly through Tor:
        #TODO:  this is a little weird, multiple failure conditions:
        if self.waiting_for_stream(stream):
          self.handle_stream_creation(stream)
          return
        port = int(event.source_addr.split(":")[1])
        #need to figure out the original application that started this:
        assert port, "port must be defined to map a Stream to an Application"
        pid = System.get_pid_from_port(port)
        assert pid != 0, "pid must be non-zero in order to map from a Stream to Application"
        originalApp = self.get_app_by_pid(pid)
        originalApp.on_new_stream(stream, None)
      except Exception, e:
        log_ex(e, "No app for stream=%d?" % (stream.id))
    
  def handle_stream_creation(self, stream):
    """Called when a new Stream is created from a Tor control event.
    @param stream:  the stream that was just created
    @type  stream:  Stream
    """
    localPort = int(stream.sourceAddr.split(":")[1])
    if self.pendingStreams.has_key(localPort):
      cb, socksProtocol, failure_cb = self.pendingStreams[localPort]
      try:
        cb(stream, socksProtocol)
      except Exception, e:
        failure_cb(e)
      finally:
        del self.pendingStreams[localPort]
    else:
      self.pendingStreams[localPort] = stream
      
  def handle_stream(self, stream):
    """Should never be called.  Another Application should be handling the stream instead.  General purpose streams use Circuit.handle_stream instead."""
    raise Exception("BitBlinder should not be handling streams directly.  Have a circuit handle them or something.")
    
  def waiting_for_stream(self, stream):
    """Determine if we know of a socks protocol that is waiting for a new stream event.
    @param stream:  the new stream
    @type  stream:  Stream
    @return:  True if we know what socks protocol is waiting for stream, False otherwise."""
    key = int(stream.sourceAddr.split(":")[1])
    ##check if there are any pending internal requests:
    #key = "%s:%d" % (host, port)
    if self.pendingStreams.has_key(key):
      return True
    else:
      return False
  
