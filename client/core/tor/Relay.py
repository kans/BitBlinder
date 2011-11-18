#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Class representing Tor Routers (basically extending Router from TorCtl)"""

import socket
import struct
import types

from twisted.internet.abstract import isIPAddress

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from core import BWHistory

#: how many stream bw values to store
MAX_VALUES = 100
#: how much bw to assume when a relay is new and has no default BW
INITIAL_BW = 100000

class Relay(BWHistory.BWHistory):
  """Represents a relay in the BitBlinder network.
  NOTE:  this should really be a child class of Router from TorCtl, but I didnt want to modify
  that code.  The way they create/copy/store Routers is weird, so we just keep a ptr 
  to the Router class here.  Should be good enough for now"""
  
  def __init__(self):
    #call parent constructor:
    self.__class__.__bases__[0].__init__(self)
    #: how many times we've failed to connect to this relay directly
    self.connectionFailures = 0
    #: the TorCtl Router object for this relay
    self.desc = None
    
  #TODO:  make this more scientific?  It's pretty rough right now
  def get_p_failure(self):
    """@returns: probability that a connection to this node will fail"""
    return float(self.connectionFailures) / float(self.connectionFailures+2)
    
  def get_score(self):
    """@returns:  weighted bandwidth, for deciding paths"""
    #NOTE:  this is given in bytes per second
    baseScore = self.desc.bw
    if baseScore <= 0:
      baseScore = INITIAL_BW
    return baseScore * (1.0-self.get_p_failure())
    
  def set_descriptor(self, routerDescriptor):
    """Must be called before most other methods, which all access desc"""
    self.desc = routerDescriptor
    
  def on_or_event(self, event):
    """Called by EventHandler when we get an OR event
    @param event:  the ORConnEvent"""
    #Check for relays that are down:
    if event.status == "FAILED":
      #note that we've failed to extend to it:
      self.connectionFailures += 1.0
      log_msg("Failed to extend to another relay (%s) for reason:  %s" % (Basic.clean(self.desc.idhex), event.reason), 2)
      
  #TODO:  allow relays to have variable costs:
  def get_cost(self):
    """@returns:  the cost for using this relay"""
    return 1
  
  def get_ip(self):
    """@returns:  int (of the IP of this relay)"""
    return socket.inet_ntoa(struct.pack('L', self.desc.ip))
    
  def will_exit_to(self, host, port, protocol="TCP"):
    """Figure out whether this relay will allow any exit traffic to host:port.
    If host is None, return True if there is any possible host that exit traffic
    to that port would be allowed (and vice versa).  Behavior when host AND port
    are None is undefined (raises exception)"""
    if not self.desc:
      return False
    #protocol is allowed to be DHT or TCP
    if protocol == "DHT":
      return self.desc.allowsDHT
    if protocol != "TCP":
      raise ValueError("Bad value for protocol:  %s" % (protocol))
    #for the vacuous case that we dont actually care
    if not host and not port:
      return True
    #make sure that this host is an int:
    intHost = None
    if host and type(host) != types.IntType and isIPAddress(str(host)):
      intHost = struct.unpack(">I", socket.inet_aton(host))[0]
    port = int(port)
    #if we're filtering based on both host and port:
    if intHost and port:
      #check the descriptor's exit policy:
      return self.desc.will_exit_to(intHost, port)
    #if we're just filtering based on host:
    elif intHost:
      return self.will_exit_to_host(intHost)
    #if we're just filtering based on port:
    elif port:
      return self.will_exit_to_port(port)
    #should be unreachable...
    return False

  def will_exit_to_port(self, port):
    """@param port:  the port to check against the exit policy
    @returns: True if there is ANY way this router will allow exits to port."""
    for line in self.desc.exitpolicy:
      if line.port_low <= port and port <= line.port_high:
        if line.match:
          return True
    return False
        
  def will_exit_to_host(self, host):
    """@param host:  the address to check against the exit policy
    @type  host:  int
    @returns:  True if there is ANY way this router will allow exits to host."""
    for line in self.desc.exitpolicy:
      if (host & line.netmask) == line.ip:
        if line.match:
          return True
    return False
    
  def has_flags(self, flags):
    """@returns: True if the descriptor has ALL flags that are passed."""
    for f in flags:
      if f not in self.desc.flags:
        return False
    return True
  
  def does_not_have_flags(self, flags):
    """@returns: True if the descriptor does NOT have ANY of the flags that are passed."""
    for f in flags:
      if f in self.desc.flags:
        return False
    return True
    
