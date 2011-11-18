#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""BROKEN:  Please update this class to work better, and be used everywhere that 
we're essentially using an instance factory anyway"""

from twisted.internet import protocol

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class InstanceFactory(protocol.ClientFactory):  
  def __init__(self, reactor, instance, failureCB=None):
    self.reactor = reactor
    self.instance = instance
    self.failureCB = failureCB
    self.oldConnectionMadeFunc = instance.connectionMade
    def temp():
      self.failureCB = None
      self.instance.connectionMade = self.oldConnectionMadeFunc
      self.instance.connectionMade()
    instance.connectionMade = temp
  
  def __repr__(self):
    return "<DefaultInstanceFactory: %r>" % (self.instance, )
  
  def buildProtocol(self, addr):
    return self.instance
  
  def clientConnectionFailed(self, connector, reason):
    if self.failureCB:
      cb = self.failureCB
      self.failureCB = None
      cb(reason)
  
  def clientConnectionLost(self, connector, reason):
    if self.failureCB:
      cb = self.failureCB
      self.failureCB = None
      cb(reason)
    else:
      self.instance.connectionLost(reason)