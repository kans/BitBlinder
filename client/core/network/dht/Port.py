#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Represents a port that is forwarded for DHT.  Starts the service when the port
is known to be open."""

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui import GUIController
from core.network import ForwardedPort
from core.network.dht import Node

class DHTPort(ForwardedPort.ForwardedPort):
  def __init__(self, name, port, bbApp, dataFileName):
    ForwardedPort.ForwardedPort.__init__(self, name, port, bbApp, "UDP", False)
    self._add_events("started", "stopped")
    self.dataFileName = dataFileName
    self.dhtNode = None
    
  def _start_dht(self):
    if not self.dhtNode:
      log_msg("Started DHT service...", 2, "dht")
      self.dhtNode = Node.DHTNode(self.port, self.dataFileName)
      self._trigger_event("started")
    
  def _stop_dht(self):
    if self.dhtNode:
      log_msg("Stopped DHT service...", 2, "dht")
      self.dhtNode.stop()
      self._trigger_event("stopped")
    self.dhtNode = None
    
  def is_ready(self):
    return self.dhtNode != None
    
  def get_node(self):
    return self.dhtNode
    
  def on_reachable(self):
    ForwardedPort.ForwardedPort.on_reachable(self)
    self._start_dht()
  
  #TODO:  fix this by adding circuit-based or distributed backoff for port testing.  Currently relies completely on test server.
  #TODO:  when this is more reliable, call stop or _stop_dht here if it's actually unreachable
  def on_unreachable(self, reachabilityResult):
    #for now, lets pretend that reachabilityResult==None implies reachability if UPnP was successful:
    if reachabilityResult is None and self.usedUPNP is True:
      self._on_reachable()
      return
    #otherwise, we failed
    ForwardedPort.ForwardedPort.on_unreachable(self, reachabilityResult)

  def stop(self):
    self._stop_dht()
    return ForwardedPort.ForwardedPort.stop(self)
    
