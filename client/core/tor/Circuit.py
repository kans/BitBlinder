#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Base Circuit class to represent circuits in Tor."""

import time
import copy

from twisted.internet import defer
from twisted.python import failure

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common.utils import TorUtils
from core import BWHistory
from core.tor import TorMessages
from core.tor import TorCtl

#: Whether or not we should create Circuit objects for circuits that were created by Tor or another program:
OBSERVE_INTERNAL = True
#: how often (at a minimum) to query Tor's payments
CHECK_PAYMENT_INTERVAL = 1.0

class Circuit(BWHistory.BWHistory):
  """Represents actual circuits in Tor."""
  def __init__(self, event, app, id, finalPath=None):
    """Create a new Circuit based on an event from the Tor control interface.
    @param event:  The TorCtrl event
    @param app:  The application that this circuit belongs to.
    @param id:  The Circuit id (will be referenced by future TorCtl events)
    @param finalPath:  The sequence of relays that the circuit will go through when finished being built
    NOTE:  internal Circuits might not have been initialized starting from the "LAUNCHED"
    state because they may have been started before the controller.  Thus, no
    logic about state/status changes should depend on something having happened
    in response to a previous event, because that event may not have ever
    happened."""
    #call parent constructor:
    self.__class__.__bases__[0].__init__(self)
    #: the application that owns this circuit:
    self.app = app
    #: a list of all tor circuit status events that happened for this circuit
    self.events = []
    #: this is the current path (routers that have been successfully extended to)
    self.currentPath = []
    #: this is the path that this circuit will hopefully extend to.  Not necessarily defined unless isBitBlinderCircuit is True
    #: (note that this is NOT the routers that have already been extended to)
    self.finalPath = None
    #: whether the stream is already FAILED/CLOSED
    self.done = False
    #: whether to send payments for this circuit or not:
    self.sendPayments = True
    #: the way to pay to for our traffic (sort of weird, this will eventually be part of the circuit itself)
    self.parClient = None
    #: whether we're ready for refill_payments calls or not (need to get our global circ id first):
    self.readyForPayments = False
    #: how many relay data cells we've payed for:
    self.payedReadBytes = 0
    self.payedWriteBytes = 0
    #: how many circuit tokens there were at the last update (used to calculate bandwidth)
    self.lastPayedReads = 0
    self.lastPayedWrites = 0
    #: set our id:
    self.id = id
    #: whether this circuit successfully made it to BUILT status or not:
    self.succeeded = None
    #This indicates that the Circuit was not created by us:
    if event:
      #the circuit event handler will not be called for this first event, so
      #do everything here in the constructor:
      self.events.append(event)
      #indicates that this was NOT created by us:
      self.isBitBlinderCircuit = False
      #: current status of the circuit
      self.status = event.status
      self.reason = event.reason
      self.remoteReason = event.remote_reason
      #set the current path, the representation of the currently EXTENDED path
      #right now:
      for fullRouterName in event.path:
        hexId = TorUtils.get_hex_id(fullRouterName)
        r = self.app.torApp.get_relay(hexId)
        if r:
          self.currentPath.append(r)
        else:
          log_msg("circ init event has bad router name:  %s"%(hexId), 0)
      #set the final path, the path that attached streams would (have) use(d):
      if self.status in ("CLOSED", "FAILED", "BUILT"):
        self.finalPath = []
        for fullRouterName in event.path:
          hexId = TorUtils.get_hex_id(fullRouterName)
          self.finalPath.append(self.app.torApp.get_relay(hexId))
        #also pretend that the stream ended now
        #NOTE:  in this way, endedAt and createdAt might be the same
        #so be careful not to subtract and divide without checking for zero
        if self.status in ("CLOSED", "FAILED"):
          self.endedAt = time.time()
          self.done = True
    #in this case, we are the ones who launched the circuit
    else:
      if not finalPath:
        raise Exception("Must provide a path if you dont provide an event!")
      self.finalPath = copy.copy(finalPath)
      self.isBitBlinderCircuit = True
      self.status = "PRELAUNCH"
      self.reason = None
      self.remoteReason = None
    #: any streams waiting for this Circuit to gain a "BUILT" status?
    self.pendingStreams = set()
    #: all the streams actually using the Circuit
    self.streams = set()
    #: a pointer to the row in the display
    self.treeRow = None
    #: when the first stream was attached
    self.dirtiedAt = None
    #: inform the app that there has been a new circuit so it can update its list of circuits
    self.app.on_new_circuit(self)
    #: when the next payment event is scheduled for
    self.checkPaymentEvent = None
    #: whether some Tor control message is in progress that will tell us about the number of payment cells
    self.paymentCheckInProgress = False
    #: remote DHT requests that are waiting for the circuit to be built
    self.queuedDHTRequests = []
    #: the RemoteDHTRequest object for getting peers remotely via DHT
    self.dhtClient = None
    #: this will be set to True after ADDTOKENS has completed once.  Used to prevent premature PAR payments.
    self.initialTokensAdded = False
    #: will be triggered when the circuit is ready for streams
    self.builtDeferred = defer.Deferred()
    
  def get_built_deferred(self):
    #if par is ready...
    if self.succeeded == True:
      return defer.succeed(True)
    elif self.succeeded == False:
      return defer.fail(failure.Failure(Exception("Circuit failed to build or is closed.")))
    return self.builtDeferred
    
  def on_learned_id(self, circId):
    self.id = circId
    if self.done:
      log_msg("Oops, circuit=%d was closed while being created" % (self.id), 1, "circuit")
      self.done = False
      self.close()
      return False
    self.baseCirc = TorMessages.BaseCircuit(self.app.torApp, None, self.finalPath[0].desc.idhex, 0, self.id)
    return True
    
  def set_par_client(self, parClient):
    self.parClient = parClient
    self.baseCirc.add_handler(self.parClient)

  def set_dht_client(self, dhtClient):
    self.dhtClient = dhtClient
    self.baseCirc.add_handler(self.dhtClient)
    
  def circ_status_event(self, event):
    """Handle circuit_status events.  Note that previous events may not have
    occurred if isBitBlinderCircuit is False
    NOTE:  path and other events referring to routers now use the long names:
    hex(~|=)name
    @param event: a circuit status event that just arrived over the Tor control connection
    @type  event:  Event"""
    #update data from event:
    self.events.append(event)
    self.status = event.status
    self.reason = event.reason
    self.remoteReason = event.remote_reason
    #this is the current path (routers that have been successfully extended to)
    self.currentPath = []
    for fullRouterName in event.path:
      hexId = TorUtils.get_hex_id(fullRouterName)
      r = self.app.torApp.get_relay(hexId)
      if r:
        self.currentPath.append(r)
      else:
        log_msg("circ status event has bad router name:  %s"%(hexId), 0)

    #circuit has just been created
    if event.status == "LAUNCHED":
      return
    
    #if circuit just got (effectively) closed (FAILED always goes to CLOSED)
    if event.status in ("CLOSED", "FAILED"):
      self.on_done(event.reason, event.remote_reason)
    
    #circuit has been close, no streams can be attached
    if event.status == "CLOSED":
      return
    
    #circuit failed
    if event.status == "FAILED":
      if not event.reason:
        event.reason = "None"
      if not event.remote_reason:
        event.remote_reason = "None"
      log_msg(str(self.id)+" failed: REASON="+event.reason+" REMOTE_REASON="+event.remote_reason, 3, "circuit")
      return
    
    #circuit was successfully extended to the next hop in the path
    if event.status == "EXTENDED":
      return
        
    #finished a new circuit.  now have to do par setup:
    if event.status == "BUILT":
      #do we have a final path defined yet?
      if not self.finalPath:
        self.finalPath = []
        for fullRouterName in event.path:
          hexId = TorUtils.get_hex_id(fullRouterName)
          self.finalPath.append(self.app.torApp.get_relay(hexId))
      if self.isBitBlinderCircuit and self.sendPayments:
        #make sure we dont try to attach to a closed circuit
        if not self.is_ready():
          raise Exception("Circuit %d is not ready for message test" % (self.id))
        self.status = "PAR_SETUP"
        #REFACTOR:  move all of the parClient stuff into its own separate class
        def error(failure):
          if not self.is_done():
            if Basic.exception_is_a(failure, [TorCtl.TorCtlClosed, TorCtl.ErrorReply]):
              log_msg("Failed to create PAR client, closing", 1, "circuit")
            else:
              log_ex(failure, "Unexpected failure while starting circuit")
            self.on_done()
        def response(result):
          self.readyForPayments = True
          self.parClient.send_setup_message()
        d = self.parClient.start()
        d.addCallback(response)
        d.addErrback(error)
      else:
        #for Tor and internal circuits that we dont make payments for yet
        self.on_par_ready()
      return
    raise Exception("UNHANDLED CIRCUIT STATUS:  " + event.status)
    
  #Ready for streams to be attached
  def on_par_ready(self):
    """Called either:
    1.  When PAR has successfully sent setup and any initial payment
    2.  If this circuit is not to have any payments (Tor circuits?), it is called immediately"""
    self.status = "BUILT"
    self.succeeded = True
    #is anyone waiting on this circuit?
    for stream in self.pendingStreams:
      self.attach(stream)
    self.pendingStreams.clear()
    #were we waiting for some DHT requests?
    for msg, callback in self.queuedDHTRequests:
      self.send_dht_request(msg, callback)
    self.queuedDHTRequests = []
    #trigger any callbacks:
    self.builtDeferred.callback(True)
    
  def attach(self, stream):
    """Attach a stream to this circuit.  Callers are responsible for handling failure to attach!
    @param:  the Stream to be attached
    @returns: True if it succeeded, False otherwise."""
    if stream.is_done():
      log_msg("Stream (%s) is already done, should not try to attach to Circuit (%s)." % (stream.id, self.id), 0)
      return False
    if self.is_done():
      log_msg("Circuit (%s) is already done, cannot attach Stream (%s)." % (self.id, stream.id), 0)
      return False
    if not self.app.is_tor_ready():
      log_msg("Cannot attach stream (%s) to circuit (%s) if Tor is not running!" % (stream.id, self.id), 0)
      return False
    #streams can only be attached if the circuit is built
    if self.status == "BUILT":
      def failure(error):
        log_ex(error, "Stream (%s) failed to attach to Circuit (%s)" % (stream.id, self.id), [TorCtl.ErrorReply])
        stream.ignoreCircuits.add(self)
      try:
        #try attaching the stream
        d = self.app.torApp.conn.attach_stream(stream.id, self.id)
        d.addErrback(failure)
        #and what streams are attached to us
        self.add_stream(stream)
        #mark this circuit as dirty if it is not already:
        if not self.dirtiedAt:
          self.dirtiedAt = time.time()
        log_msg("Added stream=%d to circ=%d" % (stream.id, self.id), 4, "stream")
      except TorCtl.ErrorReply, e:
        log_msg("Stream (%s) failed to attached to Circuit (%s): %s" % (stream.id, self.id, e), 1, "stream")
        stream.ignoreCircuits.add(self)
        return False
    #otherwise, they just go on the list of pending streams
    else:
      #Make sure too many are not already attached:
      self.pendingStreams.add(stream)
      log_msg("Added stream=%d to pendingStreams of circ=%d" % (stream.id, self.id), 4, "stream")
    #if it succeeded, remember the circuit for the stream
    stream.circuit = self
    return True
    
  def on_done(self, reason=0, remoteReason=0):
    """Called when a Circuit is done.  Performs various cleanup
    Parameters are not used yet.  They should be the same as the 
    codes from status events, and could be used in here to do
    better accounting for failures."""
    if not self.done:
      self.done = True
      #update routers about their failures
      if self.isBitBlinderCircuit:
        #TODO:  this might be bad for anonymity
        if len(self.currentPath) < len(self.finalPath):
          #it's PROBABLY the case that JUST that router failed...
          self.finalPath[len(self.currentPath)].connectionFailures += 1.0
        else:
          if not self.succeeded:
            for r in self.finalPath:
              r.connectionFailures += 1.0
      #make sure our status is right:
      if self.status not in ("FAILED", "CLOSED"):
        self.status = "CLOSED"
      #cancel the update event:
      if self.checkPaymentEvent and self.checkPaymentEvent.active():
        self.checkPaymentEvent.cancel()
      #update bw timer:
      self.on_bw_transfer_done()
      #remove ourselves from the list of live circuits
      self.app.on_circuit_done(self)
      #check if there were any pending streams:
      for stream in self.pendingStreams:
        stream.circuit = None
        #let them handle being detached:
        if stream.detachHandler:
          stream.detachHandler(stream)
        else:
          log_msg("Pending stream=%d had no detach handler, so we closed it." % (stream.id), 2, "stream")
          stream.close()
      self.pendingStreams.clear()

  def close(self, reason=0):
    """Close the circuit.  0 is the code for NONE (No reason given.), which we
    will use as the default reason.  See Tor specs for other codes."""
    self.on_done(reason)
    if self.app.is_tor_ready() and self.id != -1:
      d = self.app.torApp.conn.close_circuit(self.id, reason)
      def error(failure):
        log_ex(failure, "Circuit (%d) failed to close" % (self.id), [TorCtl.ErrorReply])
      d.addErrback(error)
      return d
    
  def get_exit(self):
    """@returns: the Relay representing the last router in our path or None if the exit router is unknown"""
    if not self.finalPath:
      return None
    exit = self.finalPath[-1]
    return exit
  
  def is_open(self):
    """@returns: True if the circuit is NOT yet closed or failed."""
    if self.status in ("CLOSED", "FAILED") or self.done:
      return False
    return True
  
  def is_done(self):
    """So that we have the same function as Stream."""
    if not self.is_open():
      #TODO:  HACK:  because sometimes this slips through and isnt properly called...
      if not self.endedAt:
        self.endedAt = time.time()
      return True
    return False
  
  def is_launching(self):
    """@returns:  True if the Circuit is being created, False otherwise"""
    if self.status in ("PRELAUNCH", "LAUNCHED", "EXTENDED", "PAR_SETUP", "PAR_SETUP2"):
      return True
    return False
  
  def is_ready(self):
    """@returns: True if the circuit is ready for streams, False, otherwise."""
    if self.status in ("BUILT"):
      return True
    return False
    
  def will_accept_connection(self, host, port, protocol="TCP"):
    """Is this circuit currently loaded to capacity, or can it accept new streams?
    @returns: True if Streams can be attached to the Circuit, False otherwise"""
    if not self.isBitBlinderCircuit:
      return False
    r = self.get_exit()
    if not r or not r.will_exit_to(host, port, protocol):
      return False
    return True
      
  def num_active_streams(self):
    """Get the number of streams that are (or soon will be) actually sending data.
    @returns: int"""
    active = len(self.pendingStreams)
    for s in self.streams:
      if s.status not in ("CLOSED", "FAILED", "DETACHED"):
        active += 1
    return active
  
  def add_stream(self, stream):
    """add a stream to our set"""
    if stream not in self.streams:
      #make sure we note any data this stream has already accumulated in case we're late in attaching
      self.handle_bw_event(stream.totalRead, stream.totalWritten)
      self.streams.add(stream)
    
  def remove_stream(self, stream):
    """remove a stream from this circuit's set of streams"""
    if stream in self.streams:
      self.streams.remove(stream)
    else:
      if stream in self.pendingStreams:
        self.pendingStreams.remove(stream)
      else:
        log_msg("remove_stream called for wrong circuit? (strm=%d, circuit=%d)" % (stream.id, self.id), 0)
  
  def on_stream_done(self, stream):
    """called when a stream finishes sending data"""
    self.remove_stream(stream)
    
  def handle_bw_event(self, dataRead, dataWritten):
    """Track how much data has been sent down this stream, send PAR messages as appropriate.
    @param dataRead:  the amount of data read in this operation
    @type  dataRead:  int
    @param dataWritten:  the amount of data read in this operation
    @type  dataWritten:  int"""
    if self.isBitBlinderCircuit and self.sendPayments:
      self.refill_payments()
    
    BWHistory.localBandwidth.handle_bw_event(dataRead, dataWritten)
    if self.app:
      self.app.handle_bw_event(dataRead, dataWritten)
    #update our own bw:
    BWHistory.BWHistory.handle_bw_event(self, dataRead, dataWritten)
    #update bw for all routers in the path:
    if not self.currentPath:
      #NOTE:  this actually happens now too, since we assign .circuit when adding the stream to pendingStreams.
      #It's so weird that these events happen so early.  Maybe they should just get kicked back until later?
      #log_msg("Circuit %d has no currentPath?" % (stream.circuit.id), 0)
      return
    #update the routers:
    for r in self.currentPath:
      r.handle_bw_event(dataRead, dataWritten)
    
  def handle_token_response(self, read, write):
    """Called when we learned about the token values in Tor
    @param read:  how many read tokens Tor has right now
    @type  read:  int
    @param write:  how many read tokens Tor has right now
    @type  write:  int"""
#    log_msg("%d handle_token_response" % (self.id))
    #and now we rest our values based on what we heard from Tor:
    self.payedReadBytes = read * Globals.BYTES_PER_CELL
    self.payedWriteBytes = write * Globals.BYTES_PER_CELL
    
  def send_dht_request(self, msg, callback):
    #are we ready to send DHT requests yet?
    if self.is_ready():
      self.dhtClient.send_request(msg, callback)
    #if not, add to the queue to send when ready
    else:
      self.queuedDHTRequests.append((msg, callback))

  def refill_payments(self, force=False):
    """Check whether we should send payments along this circuit or not.
    @param force:  if True AND it is possible to send payments, send at least one, even if it isnt necessary.
    @type  force:  bool"""
    if not self.sendPayments:
      return
      
    if not self.readyForPayments:
      return
      
    if not self.app.is_tor_ready():
      log_msg("Failed to refill payments because Tor connection is not ready", 0)
      return
      
    if not self.parClient:
      log_msg("Premature read or write (parClient is not yet open and ready)", 1)
      return
      
    if self.app.paused:
      log_msg("Not making payments because the app is paused", 4, "circuit")
      return
      
    if not self.initialTokensAdded:
      log_msg("Not making payments because we're waiting for the initial ADDTOKENS call to complete.", 4, "circuit")
      return

    #how many bytes are we missing?
    curReadBytes = self.payedReadBytes + (self.parClient.inflightReadTokens * Globals.BYTES_PER_CELL)
    curWriteBytes = self.payedWriteBytes + (self.parClient.inflightWriteTokens * Globals.BYTES_PER_CELL)
    requiredReadBytes = Globals.LOW_PAR_BYTES - curReadBytes
    if requiredReadBytes < 0:
      requiredReadBytes = 0
    requiredWriteBytes = Globals.LOW_PAR_BYTES - curWriteBytes
    if requiredWriteBytes < 0:
      requiredWriteBytes = 0
    #do we need any payments?
    if force or requiredReadBytes + requiredWriteBytes > 0:
      numPayments = 1 + ((requiredReadBytes + requiredWriteBytes + 2*Globals.BYTES_PER_CELL) / (Globals.BYTES_PER_CELL * Globals.CELLS_PER_PAYMENT))
      #lets give half to read, half to write
      numReadCells = 1 + (requiredReadBytes / Globals.BYTES_PER_CELL)
      numWriteCells = 1 + (requiredWriteBytes / Globals.BYTES_PER_CELL)
      #how much is left over?
      leftoverCells = numPayments*Globals.CELLS_PER_PAYMENT - (numReadCells + numWriteCells)
      assert leftoverCells >= 0, "cannot have negative leftover cells"
      if force or (requiredReadBytes and requiredWriteBytes):
        numReadCells += leftoverCells / 2
        if leftoverCells % 2 != 0:
          numReadCells += 1
        numWriteCells += leftoverCells / 2
      elif requiredReadBytes:
        numReadCells += leftoverCells
      else:
        numWriteCells += leftoverCells
      log_msg("PAR CHECK:  R=%s|%s|%s  W=%s|%s|%s" % \
              (self.payedReadBytes/Globals.BYTES_PER_CELL, self.parClient.inflightReadTokens, numReadCells,
               self.payedWriteBytes/Globals.BYTES_PER_CELL, self.parClient.inflightWriteTokens, numWriteCells), 4, "par")
      self.parClient.send_payment_request(numReadCells, numWriteCells)
      
  def handle_stream(self, stream, proto):
    """Attach the stream to this circuit, or fail if that is not possible.  Used
    in place of an Application to handle misc. streams.
    @param stream:  the Stream object to be attached
    @param proto:  the Protocol object that generated the Stream"""
    #TODO:  this whole process is a bit weird, sorry  :(
    self.app.register_new_stream(stream, proto)
    #do not try to attach to any other circuits
    stream.detachHandler = None
    #force attach to this circuit, it is definitely the one we wanted
    if not self.attach(stream):
      #1 -- REASON_MISC           (catch-all for unlisted reasons)
      stream.close(1)
      log_msg("Stream=%d failed to attached to Circuit=%d" % (stream.id, self.id), 1, "stream")
      
