#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Module to interface with Tor Control interface."""

import re
import sys
import random
import threading
import time
from twisted.internet.abstract import isIPAddress
from twisted.internet.error import ConnectionDone, ConnectionLost

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import TorUtils
from common.classes import Scheduler
from common.events import GlobalEvents
from core.tor import Circuit
from core.tor import TorCtl
from core import BWHistory
from gui import GUIController
from Applications import BitBlinder

class EventHandler(TorCtl.EventHandler):
  """Handles events from the Tor controller"""  
  def __init__(self, app):
    #call parent constructor
    self.__class__.__bases__[0].__init__(self)
    self.isReady = False
    self.torApp = app
    #: keys are the messages to show to the user if they occur, values are whether the message has been shown
    self.badMessages = {"Received directory with skewed time": False, "Tor needs an accurate clock to work": False}
    EVENT_TYPE = TorCtl.EVENT_TYPE
    #: for detecting errors during the bootstrapping process
    self.startupEvents = [EVENT_TYPE.WARN]
    #: almost all of the events that we listen for from Tor, except ORCIRCUIT events, which we only listen for after Tor is completely ready
    self.basicEvents =  [EVENT_TYPE.STREAM, EVENT_TYPE.TOKEN_LEVELS, 
                         EVENT_TYPE.CIRC, EVENT_TYPE.NS, EVENT_TYPE.NEWDESC, 
                         EVENT_TYPE.NEWCONSENSUS, EVENT_TYPE.ORCONN, 
                         EVENT_TYPE.BW, EVENT_TYPE.STATUS_GENERAL, 
                         EVENT_TYPE.STATUS_CLIENT, EVENT_TYPE.STATUS_SERVER, 
                         EVENT_TYPE.WARN]
    #: includes ORCIRCUIT events
    self.allEvents =  self.basicEvents + [EVENT_TYPE.ORCIRCUIT]
  
  def check_ready(self):
    """poll Tor to see if it is loaded yet.  Calls TorApp.on_ready when Tor finishes bootstrapping"""
    #BOOTSTRAP_STATUS_HANDSHAKE_OR = 85  <--finished a connection to a router
    d = self.get_progress()
    def response(progress):
      if progress >= 85:
        if not self.isReady:
          self.isReady = True
          self.torApp.on_ready()
          return
      #TODO:  handle the case where we get here with <80% progress.  What then?  Can it even happen?
      elif progress >= 80:
        #start a thread to periodically try launching circuits to random routers:
        self.startup_circuits = []
        Scheduler.schedule_repeat(2, self.try_new_circuit)
    d.addCallback(response)
    def failure(reason):
      log_ex(reason, "Failed while checking Tor bootstrap progress", [TorCtl.TorCtlClosed])
    d.addErrback(failure)
      
  def try_new_circuit(self):
    """Try a new circuit when we are at the 'build a circuit' bootstrap phase.
    We build circuits like mad here, otherwise Tor takes forever to start up."""
    for circ in self.startup_circuits:
      if circ.is_ready():
        if not self.isReady:
          self.isReady = True
          self.torApp.on_ready()
          break
    if not self.isReady:
      path = self.torApp.make_path(1)
      if path:
        log_msg("Trying to launch a circuit to %s" % (path[0].desc.nickname), 3)
        circ = BitBlinder.get().create_circuit(path, True)
        if circ:
          #since we dont actually care about this circuit, and it will be closed when we've started up
          circ.sendPayments = False
          self.startup_circuits.append(circ)
      else:
        log_msg("No routers to try launching test circuits to during startup!", 1)
      return True
    else:
      #maybe kill any circuits we tried to launch:
      log_msg("Closing %d startup circuits" % (len(self.startup_circuits)), 1)
      for c in self.startup_circuits:
        c.close()
      return False
  
  def get_progress(self):
    """Ask Tor about it's current bootstrapping phase
    @returns:  deferred (triggered when Tor responds)"""
    def response(lines):
      info = TorCtl.StatusEvent("REQUESTED", lines["status/bootstrap-phase"])
      return int(info.data["PROGRESS"])
    d = self.torApp.conn.get_info("status/bootstrap-phase")
    d.addCallback(response)
    return d
    
  def listen_for_startup_errors(self):
    """Begin listening for errors while initially bootstrapping"""
    self.torApp.conn.set_events(self.startupEvents, True)

  def start_listening_basic(self):
    """Begin listening for most of the events that we care about"""
    self.torApp.conn.set_events(self.basicEvents, True)
    
  def start_listening_all(self):
    """Same as start_listening_basic, but also listens for ORCIRCUIT events, which we have to be able to respond to"""
    self.torApp.conn.set_events(self.allEvents, True)
    
  def closed_event(self, tp, ex, tb):
    """Called when Tor control connection is closed"""
    ignoreList = [ConnectionDone]
    if self.torApp.is_stopping() or not self.torApp.is_running():
      ignoreList += [ConnectionLost]
    log_ex(ex, "Tor failure", ignoreList, reasonTraceback=tb, excType=tp)
    if self.torApp.isReady:
      log_msg("Tor Control port was closed!  reason:  %s" % (ex), 0)
      self.torApp.on_done()
      
  def msg_event(self, event):
    for badMessage in self.badMessages:
      if badMessage in event.msg:
        if not self.badMessages[badMessage]:
          GUIController.get().show_msgbox(event.msg, title=event.level)
          self.badMessages[badMessage] = True
    
  def stream_status_event(self, event):
    """Callback from TorCtl for stream events
    @param event: the event structure from the Tor controller
    @type  event:  StreamEvent"""
    self.log_event(event, "STREAM")
    stream = BitBlinder.get().get_stream(event.strm_id)
    if not stream:
      #dont bother with streams that were started before we were:
      if event.status not in ("NEW", "NEWRESOLVE"):
        return
      BitBlinder.get().on_new_stream(event)
    else:
      #NOTE:  stream_status_event is not called for the initial event:
      stream.stream_status_event(event)
    
  def circ_status_event(self, event):
    """Callback from TorCtl for circuit events
    @param event: the event structure from the Tor controller
    @type  event:  StreamEvent"""
    self.log_event(event, "CIRC")
    circ = BitBlinder.get().get_circuit(event.circ_id)
    #NOTE:  IMPORTANT:  Circuits should NOT recieve circ_status_event calls for
    #the status event with which they were created.
    if not circ:
      #create Circuits if they dont exist already, and we're observing internal
      #circuits:
      if Circuit.OBSERVE_INTERNAL:
        circ = Circuit.Circuit(event, self.torApp, event.circ_id)
    else:
      circ.circ_status_event(event)
  
  def heartbeat_event(self, event):
    """Called before any event is recieved. Convenience function
       for any cleanup/setup/reconfiguration you may need to do.
    @param event: the event structure from the Tor controller
    """

  def unknown_event(self, event):
    """Called when we get an event type we don't recognize.  This
       is almost alwyas an error.
    @param event: the event structure from the Tor controller
    @type  event:  UnknownEvent
    """
    log_msg("Got an unknown event! %s" % (event), 1)
    self.log_event(event, "UNKNOWN")
    
  def general_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       pertaining to the general state of the program.
    @param event: the event structure from the Tor controller
    @type  event:  StatusEvent
    """
    self.log_event(event, "STATUS_GENERAL")
  
  def server_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       related to the server functionality.
    @param event: the event structure from the Tor controller
    @type  event:  StatusEvent
    """
    self.log_event(event, "STATUS_SERVER")
    if event.status_event=='CHECKING_REACHABILITY' or event.status_event=='REACHABILITY_SUCCEEDED'  or event.status_event=='REACHABILITY_FAILED':
      if event.data.has_key('ORADDRESS'):
        self.torApp.on_server_status(event.status_event, event.data['ORADDRESS'])
      elif event.data.has_key('DIRADDRESS'):
        self.torApp.on_server_status(event.status_event, event.data['DIRADDRESS'])
    elif event.status_event == "EXTERNAL_ADDRESS":
      self.torApp._trigger_event("ip_update", event.data["ADDRESS"], event.data["METHOD"])
    elif event.status_event == "BAD_SERVER_DESCRIPTOR":
      self.torApp.on_server_status(event.status_event, event.data["DIRAUTH"], event.data["REASON"])
    #NOTE:  this gets called a lot, and repeatedly
    elif event.status_event == "ACCEPTED_SERVER_DESCRIPTOR":
      self.torApp.on_server_status(event.status_event, event.data["DIRAUTH"])
    #NOTE:  this first one gets called a lot, and repeatedly
    elif event.status_event == "GOOD_SERVER_DESCRIPTOR" or event.status_event == "DNS_USELESS":
      self.torApp.on_server_status(event.status_event)
  
  def client_status_event(self, event):
    """Called when Tor prints one of a number of specified status messages
       related to the client state.
    @param event: the event structure from the Tor controller
    @type  event:  StatusEvent
    """
    if event.status_event == "BOOTSTRAP":
      #BOOTSTRAP_STATUS_HANDSHAKE_OR = 85  <--finished a connection to a router
      if int(event.data["PROGRESS"]) >= 85:
        if not self.isReady:
          self.isReady = True
          self.torApp.on_ready()
    self.log_event(event, "STATUS_CLIENT")

  def or_conn_status_event(self, event):
    """Called when an OR connection's status changes if listening to
       ORCONNSTATUS events.
    @param event: the event structure from the Tor controller
    @type  event:  ORConnEvent"""
    self.log_event(event, "OR_CONN")
    #is this an IP address or a relay?
    vals = event.endpoint.split(":")
    if len(vals) == 2 and isIPAddress(vals[0]):
      #TODO:  handle these events, maybe look up the relay by IP/Port?
      pass
    #better be a hexId:
    else:
      hexId = TorUtils.get_hex_id(event.endpoint)
      #do we know about that router?
      r = self.torApp.get_relay(hexId)
      if r:
        r.on_or_event(event)

  def bandwidth_event(self, event):
    """Called once a second if listening to BANDWIDTH events.
    @param event: the event structure from the Tor controller
    @type  event:  BWEvent"""
    self.log_event(event, "BW")
    BWHistory.remoteBandwidth.handle_bw_event(event.read, event.written)
  
  #Add new router when notified
  def new_desc_event(self, event):
    """Called when Tor learns a new server descriptor if listenting to
       NEWDESC events.
    @param event: the event structure from the Tor controller
    @type  event:  NewDescEvent
    """
    self.log_event(event, "NEW_DESC")
    for fullName in event.idlist:
      hexId = TorUtils.get_hex_id(fullName)
      self.torApp.load_relay(hexId)

  def ns_event(self, event):
    """Track which routers are online, etc:
    @param event: the event structure from the Tor controller
    @type  event:  NetworkStatusEvent"""
    self.log_event(event, "NS_EVENT")
    log_msg("Updating running routers.", 4)
    newNetworkStatus = {}
    #there might be some new routers:
    idList = self.torApp.relays.keys()
    for ns in event.nslist:
      newNetworkStatus[ns.idhex] = ns
      if not ns.idhex in idList:
        #try adding it back in:
        log_msg("Router %s is now running again." % (ns.nickname), 4)
        self.torApp.load_relay(ns.idhex)
      else:
        #update the current flags:
        self.torApp.relays[ns.idhex].desc.flags = ns.flags
        if "Running" not in ns.flags:
          log_msg("Router %s is no longer running." % (ns.nickname), 4)
        else:
          log_msg("Router %s is now running." % (ns.nickname), 4)

  def address_mapped_event(self, event):
    """Called when Tor adds a mapping for an address if listening
       to ADDRESSMAPPED events.
    @param event: the event structure from the Tor controller
    @type  event:  AddrMapEvent
    """
    self.log_event(event, "ADDR_MAPPED")
  
  def log_event(self, event, s, log="event_log"):
    """Called for every event, in case you want to log them"""

  def new_consensus_event(self, event):
    """Called when Tor learns about a new consensus document from the authority servers
    @param event: the event structure from the Tor controller
    @type  event:  NewConsensusEvent"""
    log_msg("Received new consensus, updating running relays.", 2)
    idList = self.torApp.relays.keys()
    for ns in event.data:
      if ns.idhex in idList:
        #then it is definitely running:
        log_msg("Router %s is running" % (ns.nickname), 3)
        r = self.torApp.relays[ns.idhex]
        r.desc.flags = ns.flags
        r.connectionFailures /= 2.0
        idList.remove(ns.idhex)
        #are we in the consensus?
        if ns.idhex == Globals.FINGERPRINT:
          self.torApp.on_entered_consensus()
    #now mark all unlisted relays as down:
    for idhex in idList:
      log_msg("Router %s is NOT running" % (self.torApp.relays[idhex].desc.nickname), 3)
      if "Running" in self.torApp.relays[idhex].desc.flags:
        r = self.torApp.relays[idhex]
        r.desc.flags.remove("Running")
        r.connectionFailures /= 2.0
        #if we are being marked as down and we werent before:
        if idhex == Globals.FINGERPRINT:
          self.torApp.on_exited_consensus()
          
  def token_level_event(self, event):
    """Called each second for each Circuit.
    @param event: the event structure from the Tor controller
    @type  event:  TokenLevelEvent"""
    self.log_event(event, "TOKEN_LEVELS")
    circ = BitBlinder.get().get_circuit(event.circ_id)
    if circ:
      if circ.is_done():
        return
      readTraffic = Globals.BYTES_PER_CELL * (circ.lastPayedReads - (event.reads - event.reads_added))
      writeTraffic = Globals.BYTES_PER_CELL * (circ.lastPayedWrites - (event.writes - event.writes_added))
      circ.lastPayedReads = event.reads
      circ.lastPayedWrites = event.writes
      circ.handle_token_response(event.reads, event.writes)
      circ.handle_bw_event(readTraffic, writeTraffic)
          
  def orcircuit_event(self, event):
    """Called when an ORConnection (a direct connection to another relay)
    is closed, or we recieve a payment event via them.
    @param event: the event structure from the Tor controller
    @type  event:  NetworkStatusEvent"""
    self.log_event(event, "ORCIRCUIT")
    if event.msgType == "PAYMENT":
      #is there an entry for the previous relay? (there HAS to be a previous relay)
      assert event.prevHexId, "prev hex id not defined"
      entry = self.torApp.get_par_handler(event.prevHexId, event.prevCircId)
      if not entry:
        #guess not, have to make an entry:
        entry = self.torApp.make_or_circuit(event)
        #register that this entry is the handler for the next and prev circuits:
        self.torApp.set_par_handler(event.prevHexId, event.prevCircId, entry)
        if event.nextHexId:
          self.torApp.set_par_handler(event.nextHexId, event.nextCircId, entry)
      #actually handle the event:
      entry.message_arrived(event.msgData)
    elif event.msgType == "STATUS":
      if event.msgData == "CLOSED":
        #remove any existing handlers:
        if event.prevHexId:
          self.torApp.remove_par_handler(event.prevHexId, event.prevCircId)
        if event.nextHexId:
          self.torApp.remove_par_handler(event.nextHexId, event.nextCircId)
      else:
        raise Exception("Unknown ORCIRCUIT msgData:  %s" % (event.msgData))
    else:
      raise Exception("Unknown ORCIRCUIT msgType:  %s" % (event.msgType))
      
