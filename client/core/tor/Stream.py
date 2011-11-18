#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A Stream class to represent the streams in Tor."""

import time
import re

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.tor import TorCtl
from core import BWHistory

#: Slightly different meaning for internal Streams than for internal Circuits--
#: internal streams are those started by Tor, after we've started listening to
#: events.  Under no circumstances do we process events for streams that were
#: started before we started listening.
OBSERVE_INTERNAL = True

#: check if Tor manipulated the exit address
TOR_EXIT_FORMAT = re.compile(r"^.+?\.[A-Fa-f0-9]{40}.exit$")

class Stream(BWHistory.BWHistory):
  """Represents streams within Tor."""
  
  def __init__(self, event):
    """Initialize the Stream class based on the TorCtl event.  Must be the very
    first event for this stream."""
    #call parent constructor:
    BWHistory.BWHistory.__init__(self)    
    #the row in CircuitList
    self.treeRow = None
    #see if this is an internal stream (started by Tor)
    self.isInternal = False
    port = 0
    ip = ""
    if event.source_addr:
      if event.source_addr == "(Tor_internal):0":
        self.isInternal = True
      else:
        ip, port = event.source_addr.split(":")
        port = int(port)
    else:
      log_msg("No source address for stream=%d on creation, that's weird" % (event.strm_id), 2)
    #stores all events recieved that contained this stream's id
    self.events = []
    self.events.append(event)
    self.id = event.strm_id
    #represents the current status of the stream
    self.status = event.status
    #should point to the Circuit object that this stream is attached to
    self.circuit = None
    if(event.circ_id != 0):
      #this should never happen
      log_msg("Why is there a circuit already for a new stream!?", 0)
    #the destination for the stream.  Should never be able to change
    #unless it is a name that gets resolved to an IP
    self.targetHost = event.target_host
    #parse the IP from the crazy tor format:
    if TOR_EXIT_FORMAT.match(str(self.targetHost)):
      self.targetHost = self.targetHost[0:-46]
    self.targetPort = int(event.target_port)
    #the source of the stream.  Can be used to look up the requesting program
    self.sourceAddr = event.source_addr
    self.source = event.source
    #Can be one of "DIR_FETCH" / "UPLOAD_DESC" / "DNS_REQUEST" / "USER" /  "DIRPORT_TEST"
    #For BitBlinder streams, we probably only care about USER
    self.purpose = event.purpose
    self.reason = None
    self.remoteReason = None
    #this is a collection of circuits that we have been detached from or failed to attach to:
    self.ignoreCircuits = set()
    #By default, just try re-attaching yourself to a new circuit if possible.
    #This can be used to prevent streams from ending up somewhere unexpected.
    #(these are set in Application::on_new_stream)
    self.detachHandler = None
    #dont try to reattach a stream too many times, it's just silly
    self.handleAttempts = 0
    self.app = None
        
  def stream_status_event(self, event):
    """Called to handle stream status events from Tor.  Update the class based
    on the new information from the event."""
    #update our data
    self.events.append(event)
    self.status = event.status
    #is there a circuit id in this update?
    if event.circ_id != 0:
      #do we already have a circuit?
      if self.circuit:
        #are they the different circuits?
        if self.circuit.id != event.circ_id:
          log_msg("stream=%d got a new circuit without a DETACH event!" % (self.id), 0)
      self.circuit = self.app.get_circuit(event.circ_id)
      #this would be bad, could possibly happen if a stream event arrives before a circuit event
      if not self.circuit:
        log_msg("No circuit for stream=%d" % (self.id), 0)
        return
      self.circuit.add_stream(self)
    self.targetHost = event.target_host
    #parse the IP from the crazy tor format:
    if TOR_EXIT_FORMAT.match(str(self.targetHost)):
      self.targetHost = self.targetHost[0:-46]
    self.targetPort = int(event.target_port)
    self.reason = event.reason
    self.remoteReason = event.remote_reason
    
    #Sent by Tor when the address is successfully resolved to an IP
    #Source == "CACHE" if the Tor client decided to remap the address because
    #of a cached, answer, and Source == "EXIT" if the remote node we queried
    #gave us the new address as a response.
    if event.status == "REMAP":
      return
    
    #Sent a connect/resolve cell along a circuit
    if event.status in ("SENTCONNECT", "SENTRESOLVE"):
      return
    
    #This happens if a circuit fails after a stream was attached, but before
    #the stream actually sent any data.  Thus, we can just reattach the stream
    #to a new circuit instead of causing it to fail
    if event.status == "DETACHED":
      #log the reason WHY the stream was detached so we can figure out what to do eventually:
      log_msg("Stream=%d was detached.  Reason=%s.  Remote Reason=%s" % (self.id, str(event.reason), str(event.remote_reason)), 2, "stream")
      if self.circuit:
        #make sure we dont try attaching to the same stream:
        self.ignoreCircuits.add(self.circuit)
        self.circuit.on_stream_done(self)
        self.circuit = None
      if self.detachHandler:
        self.detachHandler(self)
      else:
        log_msg("Detached stream=%d had no handler, so we closed it." % (self.id), 2, "stream")
        #END_STREAM_REASON_DESTROY 5
        self.close(5)
      return
    
    if event.status in ("FAILED", "CLOSED"):
      #update bw timer:
      self.on_bw_transfer_done()
      if self.circuit:
        self.circuit.on_stream_done(self)
        self.circuit = None
    
    #stream failed
    if event.status == "FAILED":
      return
      
    #stream closed.  This is usually the last event, but I think sometimes, a
    #stream will fail but never close.  It's a bug in Tor.  They'll fix it
    #someday...
    if event.status == "CLOSED":
      #inform the application that this stream is done:
      self.app.on_stream_done(self)
      return 
    
    #stream created a connection with destination host.  Stream will still 
    #be sending data for a while though before being done
    if event.status == "SUCCEEDED":
      return
    
    #Should never get to this line, but if we do, it will tell us what new
    #status event we need to handle
    log_msg("UNHANDLED STREAM STATUS:  " + event.status, 1)
    
  def close(self, reason=1):
    """Force the stream to close.  1 is the code for REASON_MISC, which we will
    use as the default reason.  See the Tor specs for other codes."""
    if not self.is_done():
      def failure(error):
        if self.app.is_ready() or self.app.is_starting():
          log_ex(error, "Stream (%d) failed to close" % (self.id), [TorCtl.ErrorReply])
      if self.app.is_tor_ready():
        d = self.app.torApp.conn.close_stream(self.id, reason)
        d.addErrback(failure)
    else:
      log_msg("Tried to close a stream (%d) that was already done." % (self.id), 1, "stream")
    
  def is_done(self):
    """Check if the stream is closed yet or not."""
    if self.status == "CLOSED":
      #TODO:  HACK:  because sometimes this slips through and isnt properly called...
      if not self.endedAt:
        self.endedAt = time.time()
      return True
    return False
