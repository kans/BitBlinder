#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base class for application support for any application that someone would like to anonymize"""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from common import Globals
from common.utils import Basic
from core.tor import TorCtl
from core.tor import Circuit
from core.tor import ClientPaymentHandler
from core.network import dht
from Applications import Application

#DOC:  update this docstring
class SocksApplication(Application.Application):
  def __init__(self, name, settingsClass, description, torApp=None, bankApp=None):
    """Create an application.  All subclasses must call this function.
    @param name:           name of the application
    @type name:            str
    @param settingsClass:  used for storing application settings
    @type settingsClass:   Settings
    @param description:    short description of the application
    @type description:     str
    """
    Application.Application.__init__(self, name, settingsClass, description)
    #: the interface to Tor:
    self.torApp = torApp
    #: the interface to the bank:
    self.bankApp = bankApp
    #: whether everything is paused
    self.paused = False
    #: tracks which ports the app has accessed, so we can guess which one to build a circuit to pre-emptively
    self.portHistory = {}
    #have to copy this out of settings:
    self.pathLength = self.settings.pathLength 
    #listen for a bunch of events:
    self.catch_event("tor_ready")
    self.catch_event("tor_done")
    self.catch_event("no_credits")
    self.catch_event("some_credits")
    #: used to pause while Tor restarts from a crash
    self.pausedBecauseTorStopped = False
      
  def pause(self):
    if not self.paused:
      self.paused = True
      self.on_pause()
      
  def unpause(self):
    if self.paused:
      self.paused = False
      self.on_unpause()
        
  def on_pause(self):
    return
      
  def on_unpause(self):
    return
    
  def start(self):
    if self.bankApp.creditStatus != "EMPTY":
      self.unpause()
    else:
      self.pause()
    return Application.Application.start(self)
    
  def on_no_credits(self):
    """Called when all credits have been used up.  Will stop the application if it is currently supposed to be anonymous"""
    self.pause()
    
  def on_some_credits(self):
    self.unpause()
    
  def on_tor_done(self):
    """Called when Tor is disconnected."""
    Application.Application.on_tor_done(self)
    if self.is_running() and not self.paused:
      self.pause()
      self.pausedBecauseTorStopped = True
      
  def on_tor_ready(self):
    """Called when Tor has started and finished bootstrapping"""
    if self.is_running() and self.pausedBecauseTorStopped and self.paused:
      self.pausedBecauseTorStopped = False
      self.unpause()
      
  def is_tor_ready(self):
    """Return True iff we have a valid Tor control connection"""
    if self.torApp and self.torApp.is_ready():
      return True
    return False
    
  def close_connections(self):
    self.portHistory = {}
    return Application.Application.close_connections(self)
    
  def set_exit_country(self, code):
    """Set the country code to force circuits to exit from.
    @param code:  the country code (2 letters)
    @type id:   str"""
    self.exitCountry = code
    
  def launch_initial_circuits(self):
    """Override to launch some circuits when the Application starts"""
    return
    
  def handle_stream(self, stream):
    """Attach a Stream to an appropriate Circuit.  Builds a new Circuit if necessary.
    @param stream:  the stream to attach
    @type stream:  Stream
    @return:  True on success, False otherwise.  Will close the stream if False is returned."""
    stream.handleAttempts += 1
    if stream.handleAttempts > 2:
      #7 = END_STREAM_REASON_TIMEOUT     (failed to connect in a reasonable amount of time)
      stream.close(7)
      log_msg("Tried to attach stream too many times, stopping.", 2, "stream")
      return False
    host = stream.targetHost
    port = stream.targetPort
    #record in our port history:
    if port not in self.portHistory:
      self.portHistory[port] = 0
    self.portHistory[port] += 1
    #find the best circuit, or failing that, build one:
    best = self.find_or_build_best_circuit(host, port, stream.ignoreCircuits)
    #if there is no such circuit:
    if not best:
      #3 = END_STREAM_REASON_CONNECTREFUSED     (we couldnt figure out where to connect)
      stream.close(3)
      return False
    #actually attach the stream to the circuit
    if not best.attach(stream):
      #1 -- REASON_MISC           (catch-all for unlisted reasons)
      stream.close(1)
      log_msg("Stream=%d failed to attach to Circuit=%d" % (stream.id, best.id), 1, "stream")
      return False
    #if the circuit is not yet open, put a 15 second timeout on it:
    if not best.status in ("LAUNCHED", "PRELAUNCH"):
      def circuit_timeout(circ):
        if circ.status in ("LAUNCHED", "PRELAUNCH") and circ.is_open():
          circ.close()
      Scheduler.schedule_once(15.0, circuit_timeout, best)
    return True
  
  def find_or_build_best_circuit(self, host="", port=0, ignoreList=None, force=False, protocol="TCP"):
    """Find the best Circuit to exit to host:port (or if none exists, build one).
    @param host:  the circuit must be able to exit to this host
    @type host:   hostname or IP address
    @param port:  the circuit must be able to exit to this port
    @type port:   int
    @param ignoreList:  a list of Circuits to ignore
    @type ignoreList:   list
    @param force:  NOT IMPLEMENTED
    @param protocol:  NOT IMPLEMENTED
    @return:  the Circuit, or None if it is not possible."""
    assert protocol == "TCP"
    assert force == False
    if not ignoreList:
      ignoreList = []
    #find, or failing that, create, a circuit that can exit to host:port
    possible_circuits = []
    #filter out circuits that exit from the wrong country, if we care about that sort of thing:
    allowableCircuits = self.liveCircuits.copy()
    if self.exitCountry:
      allowableCircuits = [c for c in allowableCircuits if c.get_exit().desc.country == self.exitCountry]
    #check if there are any circuits that can exit to here
    for circ in allowableCircuits:
      if circ.is_ready() and circ.will_accept_connection(host, port) and circ not in ignoreList:
        possible_circuits.append(circ)
    #try reusing circuits currently being built here
    if len(possible_circuits) <= 0:
      for circ in allowableCircuits:
        if circ.is_launching() and circ.will_accept_connection(host, port) and circ not in ignoreList:
          possible_circuits.append(circ)
    #if there are still no possible circuits, open a new one:
    if len(possible_circuits) <= 0:
      circ = self.build_circuit(host, port, isFast=True)
      if circ:
        possible_circuits.append(circ)
      else:
        return None
    #pick the best of the available circuits:
    best = possible_circuits[0]
    for i in range(1, len(possible_circuits)):
      best = self._compare_circuits(possible_circuits[i], best)
    log_msg("%d looks like the best circuit for %s:%d" % (best.id, Basic.clean(host), port), 4, "stream")
    return best
    
  def _compare_circuits(self, circ1, circ2):
    """Used to rank which Circuit is the best to accept a new stream.
    @returns:  whichever circuit is better"""
    #prefer dirty circuits
    if circ2.dirtiedAt and not circ1.dirtiedAt:
      return circ2
    elif circ1.dirtiedAt and not circ2.dirtiedAt:
      return circ1
    #otherwise prefer circuits that are open and ready:
    if circ2.is_ready() and not circ1.is_ready():
      return circ2
    elif circ1.is_ready() and not circ2.is_ready():
      return circ1
    #otherwise prefer older circuits:
    if circ1.createdAt < circ2.createdAt:
      return circ1
    return circ2
    
  def on_update(self):
    Application.Application.on_update(self)
    #if there are no clean circuits, launch a new one for some port that we've frequently used
    for circ in self.liveCircuits:
      if not circ.dirtiedAt:
        return
    #ok, figure out the most common port and launch a circ for that port:
    highestFreq = 0
    bestPort = None
    for port, freq in self.portHistory.iteritems():
      if freq > highestFreq:
        highestFreq = freq
        bestPort = port
    if bestPort != None:
      circ = self.build_circuit("", bestPort)
  
  def register_new_stream(self, stream, proto):
    """Make a note that this stream belongs to this Application.
    @param stream:  the stream
    @type stream:   Stream
    @param proto:   the Protocol that this Stream is an instance of.  Could be application level, or SOCKSv5Outgoing if proxied
    @type proto:    twisted.protocol.Protocol"""
    #set the properties of the stream:
    stream.app = self
    stream.proto = proto
    stream.detachHandler = self.handle_stream
    #add stream to the list
    self.streams[stream.id] = stream
    if proto:
      proto.set_stream(stream)
    
  def on_new_stream(self, stream, proto):
    """Called when a new stream is detected from this Application.
    @param stream:  the stream
    @type stream:   Stream
    @param proto:   the Protocol that this Stream is an instance of.  Could be application level, or SOCKSv5Outgoing if proxied
    @type proto:    twisted.protocol.Protocol"""
    self.register_new_stream(stream, proto)
    #close streams immediately if the app is not ready
    if not self.is_ready():
      stream.close()
      return
    #attach this stream to a suitable circuit, or, if one does not exist,
    #build a new one.  This method can fail (if no suitable exit routers exist,
    #for eaxmple).
    self.handle_stream(stream)

  def create_circuit(self, path, ignoreLogin=False):
    """Create a new Circuit for this Application that will travel over path.
    @param path:  the path that the circuit will follow when fully constructed
    @type path:   a list of Routers
    @return:  the newly created circuit, or None if we cannot create a Circuit right now."""
    #can only create circuits if we are logged in:
    if not self.bankApp.is_ready() and not ignoreLogin:
      log_msg("Not creating the circuit because we arent logged in yet!", 1, "circuit")
      return None
    if not self.torApp.is_running() or not self.torApp.conn or self.torApp.conn._closed:
      log_msg("Not creating the circuit because Tor is not ready", 0, "circuit")
      return None
    #create the new circuit
    ids = []
    circ = None
    for relay in path:
      ids.append(relay.desc.idhex)
    circ = Circuit.Circuit(None, self, -1, path)
    #add to list of circuits
    self.circuits.add(circ)
    #add to list of live circuits:
    self.liveCircuits.add(circ)
    #tell tor to make the circuit
    torDeferred = self.torApp.conn.extend_circuit(0, ids)
    torDeferred.addCallback(self._on_circuit_creation_success, circ)
    torDeferred.addErrback(self._on_circuit_creation_failure, circ)
    return circ
    
  def _on_circuit_creation_success(self, circId, circ):
    #will return False if the circuit was closed while we were waiting for its ID
    if not circ.on_learned_id(circId):
      return False
      
    log_msg("Successfully created new circuit=%d" % (circ.id), 4, "circuit")
    
    parClient = ClientPaymentHandler.ClientPaymentHandler(self.bankApp, circ.baseCirc, circ)
    circ.set_par_client(parClient)
    
    dhtClient = dht.Proxy.RemoteDHTRequest(circ.baseCirc, circ)
    circ.set_dht_client(dhtClient)
    
    return True
    
  def _on_circuit_creation_failure(self, failure, circ):
    log_ex(failure, "circuit creation failed", [TorCtl.ErrorReply])
    #make sure it is no longer in our collections of circuits:
    if circ in self.circuits:
      self.circuits.remove(circ)
    if circ in self.liveCircuits:
      self.liveCircuits.remove(circ)
    
  def get_number_of_hops(self):
    return self.pathLength
    
  def build_circuit(self, host, port, isFast=True, force=False, ignoreExits=None, protocol="TCP"):
    """Builds a circuit to exit to host:port with the given parameters.
    @param host:  the circuit must be able to exit to this host
    @type host:   hostname or IP address
    @param port:  the circuit must be able to exit to this port
    @type port:   int
    @param isFast:  whether the Circuit should be over routers with the Fast flag or not
    @type isFast:   bool
    @param force:  whether the Circuit should be built regardless of limits on the maximum number of circuits
    @type force:   bool
    @param ignoreExits:  Routers that should definitely not be used as the exit Router
    @type ignoreExits:   a list of Routers
    @param protocol:  What type of traffic will be sent from the exit
    @type protocol:   string (either TCP or DHT for now)
    @return: the constructed Circuit.  If the circuits cannot be built, returns None"""
    #Make sure that this wont open too many circuits:
    if not force and len(self.liveCircuits) >= Globals.MAX_OPEN_CIRCUITS:
      log_msg("Too many circuits (%s), not opening any more unless forced!" % (len(self.liveCircuits)), 4, "circuit")
      return None
      
    if not self.is_tor_ready():
      log_msg("Tor is not ready to create circuits", 0, "circuit")
      return None
      
    if self.paused:
      log_msg("Not creating new circuits because the app is paused", 4, "circuit")
      return None
    
    length = self.get_number_of_hops()
      
    #ignore exits that we're already using:
    if ignoreExits == None:
      ignoreExits = []
    ignoreExits += [c.get_exit() for c in self.liveCircuits]
    
    path = self.torApp.make_path(length, host, port, self.exitCountry, ignoreExits, protocol)
    if not path:
      return None

    #build the actual circuit
    circ = self.create_circuit(path)
    #return the new circuit
    return circ
      
    
