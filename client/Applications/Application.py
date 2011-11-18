#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Base class for application support for any application that someone would like to anonymize"""

import time
import os
import copy

from twisted.internet import defer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Scheduler
from common.system import System
from common.Errors import DependencyError
from common.events import GlobalEvents
from common.events import GeneratorMixin
from common.utils import Basic
from core import BWHistory
from core import ClientUtil
from gui import GUIController

#DOC:  update this docstring
class Application(BWHistory.BWHistory, GlobalEvents.GlobalEventMixin, GeneratorMixin.GeneratorMixin):
  def __init__(self, name, settingsClass, description):
    """Create an application.  All subclasses must call this function.
    @param name:           name of the application
    @type name:            str
    @param settingsClass:  used for storing application settings
    @type settingsClass:   Settings
    @param description:    short description of the application
    @type description:     str
    """
    GeneratorMixin.GeneratorMixin.__init__(self)
    BWHistory.BWHistory.__init__(self)
    self._add_events("launched", "started", "stopped", "finished")
    #: applications are stored in a single folder, by default under this folder:
    self.appBasePath = "apps"
    #: the name of the application
    self.name = name
    #: a short description of the application
    self.desc = description
    #load the settings file:
    if not hasattr(settingsClass, "defaultFile"):
      fileName = "%sSettings.ini" % (name)
    else:
      fileName = settingsClass.defaultFile
    fileName = os.path.join(Globals.USER_DATA_DIR, fileName)
    #: the Settings class instance
    self.settings = settingsClass()
    if not self.settings.load(fileName):
      self.isFirstRun = True
    else:
      self.isFirstRun = False
    #store for later loading the file
    self.settings.fileName = fileName
    #: list of process that are this application:
    self.processes = []
    #: this indicates that the program is in the process of shutting down:
    self.shutdownDeferred = None
    #: set when the process is starting up and we're waiting for it to finish
    self.startupDeferred = None
    #: set when starting or stopping and we need to restart:
    self.restartDeferred = None
    #: flag set when restarting:
    self.isRestarting = None
    #: dictionary mapping from id -> obj for all Circuits
    self.circuits = set()
    #: as above, but closed/failed circuits are never in this dictionary
    self.liveCircuits = set()
    #: dictionary mapping from id -> obj for all Streams
    self.streams = {}
    #: the 2-letter country code of the country to exit from, or None if this setting should be ignored
    self.exitCountry = None
    #: how many coins this application has spent so far
    self.coinsSpent = 0
    #: amount of time in seconds after which we stop trying to shutdown cleanly and give up
    self.shutdownTimeoutLength = 10
    #listen for a bunch of events:
    self.catch_event("shutdown")
    self.catch_event("tor_done")
    ClientUtil.add_updater(self)
    
  def get_settings_name(self):
    """returns the name of the application to be displayed in the settings dialogs"""
    #: name displayed for this applications settings in the settings dialog
    settingsName = getattr(self.settings, "DISPLAY_NAME", self.name)
    return settingsName
    
  def get_status(self):
    state = "DONE"
    if self.is_ready():
      state = "READY"
    elif self.is_stopping():
      state = "STOPPING"
    elif self.is_starting():
      state = "STARTING"
    statusString = "%s: %s isFirstRun=%s" % (self.name, state, self.isFirstRun)
    return statusString
    
  def restart(self):
    """Stop the application, and when that is complete, start it up again"""
    #set restarting flag
    self.isRestarting = True
    if not self.is_running():
      return self.start()
    def cb(result):
      return self.start()
    stopDeferred = self.stop()
    stopDeferred.addCallback(cb)
    return stopDeferred
    
  def is_starting(self):
    if self.startupDeferred:
      return True
    return False
    
  def is_stopping(self):
    if self.shutdownDeferred:
      return True
    return False
    
  def is_running(self):
    if self.startupDeferred or self.shutdownDeferred or self.is_ready():
      return True
    return False
    
  def start(self):
    """Start up the app"""
    #if we're already running, immediately succeed for any callback
    #flip restart flag if need be
    if self.isRestarting == True:
      self.isRestarting = False
    if self.is_ready():
      return defer.succeed(True)
    if self.is_starting():
      return self.startupDeferred
    if self.is_stopping():
      if self.restartDeferred:
        return self.restartDeferred
      self.restartDeferred = defer.Deferred()
      self.shutdownDeferred.addCallback(self._start, self.restartDeferred)
      return self.restartDeferred
    return self._start()

  def _start(self, startupDeferred=None):
    if not startupDeferred:
      startupDeferred = defer.Deferred()
    self.restartDeferred = None
    self.startupDeferred = startupDeferred
    dependenciesDeferred = self.launch_dependencies()
    dependenciesDeferred.addCallback(self.dependencies_done)
    dependenciesDeferred.addErrback(self.launch_failed)
    self._trigger_event("launched")
    return self.startupDeferred
      
  def dependencies_done(self, result):
    launchDeferred = self.launch()
    launchDeferred.addCallback(self.launch_finished)
    launchDeferred.addErrback(self.launch_failed)
  
  def launch_finished(self, result):
    tempDeferred = self.startupDeferred
    self.startupDeferred = None
    self.processes = []
    for p in result:
      self.add_process(p)
    tempDeferred.callback(True)
    self._trigger_event("started")
    
  #child classes can override this to try restarting as appropriate
  def launch_failed(self, reason):
    log_ex(reason, "Failed to launch application:  %s" % (self.name), [DependencyError])
    GUIController.get().show_msgbox("Failed to launch %s:  %s" % (self.name, reason), title="Error", makeSafe=True)
    if self.startupDeferred:
      tempDeferred = self.startupDeferred
      self.startupDeferred = None
      tempDeferred.callback(False)
    
  def _subprocess_finished(self, result, p):
    if result == True:
      self.remove_process(p)
      if len(self.processes) <= 0:
        self._all_subprocesses_done()
    elif result != False:
      log_ex(result, "Failed while waiting for subprocess")
      
  def launch(self):
    """This should launch the processes, and must return the launched process objects.
    @return:  a list of the process objects that represent this Application.  May be empty."""
    raise NotImplementedError()
  
  def on_shutdown(self):
    """called right before the our program exits"""
    return

  def is_ready(self):
    """Is the application running?
    @returns:  True if it is running, False otherwise."""
    if self.shutdownDeferred or self.startupDeferred:
      return False
    if len(self.processes) <= 0:
      return False
    return True
    
  def _stop_when_started(self, result, cancelDeferred):
    Basic.validate_result(result, "_stop_when_started")
    self.stop().chainDeferred(cancelDeferred)

  def stop(self):
    """Shut down the app and do any necessary cleanup.  
    @return:  a deferred that is triggered when the application is done shutting down."""
    #return any existing shutdown deferred if we're in the process of shutting down:
    if self.shutdownDeferred:
      return self.shutdownDeferred
    if self.is_starting():
      #cancel the startup:
      cancelDeferred = defer.Deferred()
      self.startupDeferred.addCallback(self._stop_when_started, cancelDeferred)
      self.startupDeferred.addErrback(self._stop_when_started, cancelDeferred)
      return cancelDeferred
    #if we're not running, succeed immediately:
    if not self.is_ready():
      return defer.succeed(True)
    #this is the deferred that will be triggered when we finish shutting down:
    self.shutdownDeferred = self.exit()
    self._trigger_event("stopped")
    self.shutdownDeferred.addCallback(self.stop_success)
    #this happens if self.exit returns succeed as well
    if not self.shutdownDeferred:
      return defer.succeed(True)
    self.shutdownDeferred.addErrback(self.stop_failure)
    #return our deferred, so other people can respond appropriately
    return self.shutdownDeferred
    
  def exit(self):
    shutdownDeferred = defer.Deferred()
    try:
      #for every process that did not yet exit, kill it
      for processObj in self.processes:
        #TODO:  change to this once kill_recursive runs on linux:
        #kill_recursive(p.pid)
        System.kill_process(processObj.pid)
    except Exception, error:
      log_ex(error, "Failed to kill Application process:")
    return shutdownDeferred
    
  def _all_subprocesses_done(self):
    if self.shutdownDeferred:
      self.shutdownDeferred.callback(True)
    
  def stop_done(self):
    self.shutdownDeferred = None
    self.close_connections()
    self._trigger_event("finished")
    
  def stop_failure(self, reason):
    log_ex(reason, "%s failed to stop cleanly" % (self.name))
    self.stop_done()
    
  def stop_success(self, result):
    self.stop_done()
    return result
    
  def _get_port(self, name):
    if hasattr(self, name):
      portObj = getattr(self, name)
      return portObj
    return None
      
  def stop_forwarded_port(self, name):
    portObj = self._get_port(name)
    if not portObj:
      return
    d = portObj.stop()
    setattr(self, name, None)
    return d
    
  def start_forwarded_port(self, newPortObj):
    name = newPortObj.get_name()
    oldPortObj = self._get_port(name)
    
    #if there's an old port object on the same port, don't bother with the new one:
    alreadyRunningOnPort = oldPortObj and oldPortObj.get_port() == newPortObj.get_port()
    if alreadyRunningOnPort:
      return
    
    #otherwise, stop the old port
    if oldPortObj:
      self.stop_forwarded_port(name)
    
    #and start the new port
    setattr(self, name, newPortObj)
    newPortObj.start()
    
  def on_tor_done(self):
    """Called when Tor is disconnected."""
    #clear data:
    for circ in copy.copy(self.liveCircuits):
      circ.on_done()
    self.circuits = set()
    self.liveCircuits = set()
    self.streams = {}
      
  def close_connections(self):
    """Close all circuits and streams"""
    #close all of our circuits:
    for circ in copy.copy(self.liveCircuits):
      #9 = END_CIRC_REASON_FINISHED, since we're done with it
      circ.close(9)
    #and close all of our streams:
    for stream in self.streams.values():
      if not stream.is_done():
        #6 = END_STREAM_REASON_DONE
        stream.close(6)

  def on_update(self):
    """Called every INTERVAL_BETWEEN_UPDATES to update the various information"""
    if not self.is_running():
      return
    #TODO:  this is a really arbitrary way of keeping things up to date...
    #keep the list of circuits and streams reasonable:
    #if there are more than 30 streams/circuits, we remove those that have been done for a minute::
    toDelete = []
    if len(self.streams) > 30:
      for streamId, obj in self.streams.iteritems():
        if obj.is_done():
          age = time.time() - obj.endedAt
          if age > 60:
            toDelete.append(streamId)
            log_msg("Removing stream=%d from the list because it is old and closed" % (streamId), 4, "circuit")
    for streamId in toDelete:
      del self.streams[streamId]
    toDelete = []
    if len(self.circuits) > 30:
      for obj in self.circuits:
        if obj.is_done():
          age = time.time() - obj.endedAt
          if age > 60:
            toDelete.append(obj)
            log_msg("Removing circuit=%d from the list because it is old and closed" % (obj.id), 4, "stream")
    for circ in toDelete:
      self.circuits.remove(circ)
  
  def get_circuit(self, circId):
    """Get a circuit from this Application
    @param circId:  the circuit ID to find
    @type circId:   int
    @return:    the Circuit corresponding to the ID, or None if it does not exist"""
    for circ in self.circuits:
      if circ.id == circId:
        return circ
    return None
  
  def get_stream(self, streamId):
    """Get a stream from this Application
    @param streamId:  the stream ID to find
    @type streamId:   int
    @return:    the Stream corresponding to the ID, or None if it does not exist"""
    stream = None
    if self.streams.has_key(streamId):
      stream = self.streams[streamId]
    return stream
    
  def on_new_circuit(self, circ):
    """Called when a new Circuit is created for this Application.
    @param circ:  the Circuit
    @type circ:   Circuit"""
    #add to list of circuits
    self.circuits.add(circ)
    #if it is live, add to list of live circuits:
    if circ.is_open():
      self.liveCircuits.add(circ)

  def on_stream_done(self, stream):
    """Called when a stream becomes CLOSED
    @param stream:  the Circuit
    @type stream:   Circuit"""
    return
    
  #called when a circuit becomes CLOSED or FAILED
  def on_circuit_done(self, circuit):
    """Called when a circuit becomes CLOSED or FAILED
    @param circuit:  the Circuit
    @type circuit:   Circuit"""
    #remove us from the list of active circuits
    if circuit in self.liveCircuits:
      self.liveCircuits.remove(circuit)
    return
