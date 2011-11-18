#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""A module with a bunch of random functions."""

from twisted.internet import protocol
from twisted.internet import defer
from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class UDPMessageProtocol(protocol.DatagramProtocol):
  def __init__(self, data, host, port):
    self.data = data
    self.host = host
    self.port = port
    
  def startProtocol(self):
    self.transport.write(self.data, (self.host, self.port))
    
class TCPMessageProtocol(Int32StringReceiver):    
  def connectionMade(self):
    #dont send empty strings, the intent there was just to test connection
    if self.factory.data:
      self.sendString(self.factory.data)
    self.factory.clientConnectionSucceeded()
    self.transport.loseConnection()

class TCPMessageFactory(protocol.ClientFactory):
  protocol = TCPMessageProtocol
  
  def __init__(self, data):
    self.data = data
    self.finished = False
    self.connectionDeferred = defer.Deferred()
    
  def get_deferred(self):
    return self.connectionDeferred
    
  def clientConnectionSucceeded(self):
    if not self.finished:
      self.finished = True
      self.connectionDeferred.callback(True)
    
  def clientConnectionFailed(self, connector, reason):
    if not self.finished:
      self.finished = True
      self.connectionDeferred.callback(False)