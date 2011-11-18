#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Old TCP payment protocol for doing online payments.  This will only be used when UDP traffic is blocked."""

from twisted.internet.defer import Deferred
from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.bank import BankMessages

class TCPPaymentProtocol(Int32StringReceiver):
  """TCP fall back protocol for payments in case udp fails"""
  PROTOCOL_VERSION = 1
  MAX_LENGTH = 128 * 1024 * 1024 #128 megabytes
  def __init__(self, msg):
    #: a Deferred to trigger on success or failure of the payment
    self.finishedDeferred = self.factory.finishedDeferred
    #: the message to relay
    self.msg = msg
    
  def connectionMade(self):
    self.sendString(self.msg)
    log_msg("TCP Payment proxy msg sent.", 4)
    
  def stringReceived(self, data):
    self.factory.gotResponse = True
    self.transport.loseConnection()
    self.finishedDeferred.callback(data)
    
class TCPPaymentFactory(BankMessages.BankConnectionFactory):
  """Factory for Payment messages"""
  protocol = TCPPaymentProtocol
  def __init__(self, bank, msg, finishedDeferred=None):
    BankMessages.BankConnectionFactory.__init__(self, bank)
    self.gotResponse = False
    if not finishedDeferred:
      finishedDeferred = Deferred()
    self.finishedDeferred = finishedDeferred
    
  def clientConnectionFailed(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionFailed(self, connector, reason)
    self.on_done(reason)
  
  def clientConnectionLost(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionLost(self, connector, reason)
    self.on_done(reason)
    
  def on_done(self, reason):
    if not self.gotResponse:
      self.finishedDeferred.errback(reason)
      