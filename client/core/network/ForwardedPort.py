#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Use this module to forward any port that you want to bind.  Will handle UPnP
(if available) and testing that the port is actually open."""

import time
import re
import socket
import os

from twisted.internet import utils
import twisted.internet.protocol as protocol
from twisted.internet import defer

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.network import TestablePort
from core.network import UPNPPort

class ForwardedPort(TestablePort.TestablePort, UPNPPort.UPNPPort):
  """Extending TestableUPNPPort to repeatedly test a port over time"""
  def __init__(self, name, port, bbApp=None, trafficType="TCP", isBound=True):
    """
    name = string describing this port (ie, the purpose)
    port = int port number to try forwarding
    """
    TestablePort.TestablePort.__init__(self, bbApp, trafficType, isBound)
    UPNPPort.UPNPPort.__init__(self, name, port, trafficType)
    #our state:
    self.reachableState = "UNKNOWN"
    self.upnpState = "UNKNOWN"
    
  def start(self):
    """Open the forwarded port."""
    self.reachableState = "UNKNOWN"
    self.upnpState = "UNKNOWN"
    try:
      self.start_upnp()
    except Exception, e:
      log_ex(e, "Failure while checking that port %s is properly forwarded" % (self.name))
    return True
    
  def on_upnp_done(self):
    try:
      self.start_test()
    except Exception, e:
      log_ex(e, "Error while starting test for port %s" % (self.name))
  
  def on_reachable(self):
    log_msg("Our %s port is reachable:  %s" % (self.trafficType, self.port), 2)
    self.reachableState = "YES"
  
  def on_unreachable(self, reachabilityResult):
    log_msg("Our %s port is NOT reachable:  %s" % (self.trafficType, self.port), 1)
    self.reachableState = "NO"
    
  def on_upnp_succeeded(self, ip):
    self.upnpState = "YES"
    log_msg("UPNP succeeded: (%s) %s:%s" % (self.trafficType, ip, self.port), 3)
  
  def on_upnp_failed(self, failure):
    if failure == "UNSUPPORTED":
      self.upnpState = "UNSUPPORTED"
    self.upnpState = "NO"
    log_msg("UPNP failed:  %s" % (failure), 2)
    
  def stop(self):
    """Close the forwarded port."""
    #actually stop the forwarding:
    d = self.stop_upnp()
    self.stop_test()
    return d
    
