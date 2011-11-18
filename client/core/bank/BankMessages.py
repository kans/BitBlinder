#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Contains all protocols for communication with the bank."""

#REFACTOR:  these protocol classes would be a lot better if they inherited from 
#TimeoutMixin and used a deferred instead of directly calling the bank.  Then
#they could also remove the need to pass a bank instance in all the time...

#REFACTOR:  move everything out of this module/rename it to be the correct class name

import random

from twisted.internet import protocol

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.classes import Scheduler
from core.bank import ACoin
    
#: how long before we assume the bank message failed (bank is temporarily down)
TIMEOUT = 45.0

def make_acoin_request(bank, interval, value):
  """Create an acoin signing request:
  @param interval:  during which the ACoin will be valid
  @type  interval:  int
  @param value:  how much the coin should be worth
  @type  value:  int
  @returns:  ACoinRequest"""
  #determine which bank key to use:
  bankKey = bank.get_acoin_key(value)
  numRandomBits = Globals.ACOIN_BYTES * 8
  #generate random number for blinding
  blindingFactor = bankKey.get_blinding_factor(numRandomBits)
  #generate random number receipt to be signed
  receipt = Basic.long_to_bytes(random.getrandbits(numRandomBits), Globals.ACOIN_BYTES)
  #the base message is the receipt and interval
  msg = ACoin.ACoin.pack_acoin_for_signing(receipt, interval)
  #blind the message:
  msg = bankKey.blind(msg, blindingFactor, Globals.ACOIN_KEY_BYTES)
  return ACoinRequest(blindingFactor, receipt, msg, interval, value)
  
def parse_acoin_response(bank, sig, request, validate=True):
  """Turn a bank response into a valid ACoin.
  @param sig:  the bank response
  @type  sig:  str
  @param request:  the ACoinRequest that corresponds to this response
  @type  request:  str
  @param validate:  whether to validate the ACoin
  @type  validate:  bool
  @returns:  valid ACoin
  @raises:  Exception if coin is found to not be valid"""
  #determine which bank key to use:
  bankKey = bank.get_acoin_key(request.value)
  #unblind the signature:
  sig = bankKey.unblind(sig, request.blindingFactor, Globals.ACOIN_KEY_BYTES)
  #make the coin
  coin = ACoin.ACoin(bank)
  coin.create(request.value, request.receipt, sig, request.interval)
  #validate the signature:
  if validate:
    if not coin.is_valid(request.interval):
      return None
  return coin
  
class ACoinRequest():
  """Basically a struct to store the values for a single ACoin request"""
  def __init__(self, blindingFactor, receipt, msg, interval, value):
    #: the blinding factor
    self.blindingFactor = blindingFactor
    #: random, secret receipt value
    self.receipt = receipt
    #: msg sent for signing
    self.msg = msg
    #: the interval this coin should be valid during
    self.interval = interval
    #: how much the coin should be worth
    self.value = value
  
#TODO:  if failures or timeouts are detected here, we can assume the bank is down and maybe move to a backup scheme?
class BankConnectionFactory(protocol.ClientFactory):
  """Base factory for all identity-bound bank connections.  Informs the bank when the connections fail or close"""
  def __init__(self, bank):
    self.protocolInstance = None
    self.bank = bank
  
  def buildProtocol(self, addr):
    protocolInstance = protocol.ClientFactory.buildProtocol(self, addr)
    if self.protocolInstance:
      raise Exception("Hey, you're only supposed to build one protocol with this factory!")
    self.protocolInstance = protocolInstance
    self.protocolInstance.responseReceived = False
    Scheduler.schedule_once(TIMEOUT, self.on_timeout)
    return self.protocolInstance
    
  def on_timeout(self):
    if not self.protocolInstance.responseReceived:
      log_msg("Connection to the bank timed out!", 0)
      self.closeConnection()
    
  def closeConnection(self):
    if self.protocolInstance and self.protocolInstance.transport:
      self.protocolInstance.transport.loseConnection()
    
  def clientConnectionFailed(self, connector, reason):
    log_msg("Connection failed:  %s" % (str(reason)), 1)
    self.bank.on_bank_message_done()
  
  def clientConnectionLost(self, connector, reason):
    log_msg("Connection finished", 4)
    self.bank.on_bank_message_done()
     