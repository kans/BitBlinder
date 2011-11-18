#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""UDP protocol for making online payments to the bank"""

import time
from twisted.internet.error import ConnectError
from twisted.internet.defer import Deferred, TimeoutError
from twisted.internet.protocol import DatagramProtocol

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals

class UDPPayment():
  def __init__(self, bank, msg, retryInterval=60.0, udpInterval=4.0):
    """Resends updpayments to the bank after a timeout.
    @param retryInterval: how many seconds to continue retrying until we assume a payment has failed
    @param udpInterval: how long to wait for any single UDP packet before we assume it was lost and resend"""
    self.retryInterval = retryInterval
    self.udpInterval = udpInterval
    self.bank = bank
    #: a Deferred to trigger on the ultimate success or failure of the payment process
    self.finishedDeferred = Deferred()
    #: the message to relay
    self.msg = msg
    #: whether we have succeeded or failed already
    self.done = False
    #: the time after which we will stop retrying:
    self.doneTime = time.time() + self.retryInterval
    #: the SingleUDPPayment that we are currently waiting on:
    self.currentPayment = None
    #send the first message:
    self.proxy_message()
    
  def get_deferred(self):
    return self.finishedDeferred

  def proxy_message(self):
    singleMessageDeferred = Deferred()
    self.currentPayment = SingleUDPPayment(self.bank.host, self.bank.port, self.msg, singleMessageDeferred)
    self.currentPayment.listener = Globals.reactor.listenUDP(0, self.currentPayment)
    Globals.reactor.callLater(self.udpInterval, self.currentPayment.timed_out)
    singleMessageDeferred.addCallback(self.success)
    singleMessageDeferred.addErrback(self.failure)
    
  def failure(self, error):
    if error and hasattr(error, "value"):
      if issubclass(type(error.value), ConnectError):
        log_msg("Bank appears to be down?")
        error = None
      elif issubclass(type(error.value), TimeoutError):
        log_msg("Payment was dropped, trying again...", 4, "par")
        error = None
    if error:
      log_ex(error, "Bank payment message failed!")
    #check if the global timeout is up yet:
    if time.time() < self.doneTime:
      #and if not, send try sending again
      self.proxy_message()
    #otherwise, trigger the errback
    else:
      self.finishedDeferred.errback(TimeoutError())
      
  def success(self, result):
    self.finishedDeferred.callback(result)
    
class SingleUDPPayment(DatagramProtocol):
  """Protocol for relayed payment messages from customers when this node is acting as the payment proxy"""
  def __init__(self, host, port, msg, finishedDeferred):
    self.host = host
    self.port = port
    #: a Deferred to trigger on success or failure of the payment
    self.finishedDeferred = finishedDeferred
    #: the message to relay
    self.msg = msg
    #: whether we have succeeded or failed already
    self.done = False
    #: the twisted port that is listening for responses
    self.listener = None
      
  def startProtocol(self):
    self.transport.connect(self.host, self.port)
    self.transport.write(self.msg)
      
  def datagramReceived(self, data, (host, port)):
    if not self.done:
      self.done = True
      self.listener.stopListening()
      self.finishedDeferred.callback(data)

  def connectionRefused(self):
    if not self.done:
      self.done = True
      self.listener.stopListening()
      self.finishedDeferred.errback(ConnectError())
      
  def timed_out(self):
    if not self.done:
      self.done = True
      self.listener.stopListening()
      self.finishedDeferred.errback(TimeoutError())
      