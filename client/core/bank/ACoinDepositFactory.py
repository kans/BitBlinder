#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Protocol for sending ACoins to the bank (to be deposited to your account)"""

import struct
import copy

from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from core.bank import BankMessages

class ACoinDepositProtocol(Int32StringReceiver):
  """Protocol for DEPOSIT messages"""
  PROTOCOL_VERSION = 1
  MAX_LENGTH = 128 * 1024 * 1024 #128 megabytes
  def connectionMade(self):
    msg = self.factory.bank.make_bank_prefix(self.PROTOCOL_VERSION, 'acoin deposit')
    msg += struct.pack('!H', len(self.factory.coins))
    for coin in self.factory.coins:
      msg += coin.write_binary()
    encryptedMsg = self.factory.bank.encrypt_message(msg)
    self.sendString(encryptedMsg)
    log_msg("ACoin DEPOSIT message set. (%s coins)" % (len(self.factory.coins)), 4)
  
  def stringReceived(self, data):
    self.responseReceived = True
    self.factory.gotResponse = True
    data = self.factory.bank.decrypt_message(data)
    log_msg("ACoin DEPOSIT response received.", 4)
    (newBalance, interval, expiresCurrent, expiresNext), returnSlip = Basic.read_message('!IIII', data)
    self.factory.bank.on_new_info(newBalance, interval, expiresCurrent, expiresNext)
    returnSlip = list(struct.unpack('c'*len(self.factory.coins), returnSlip))
    for i in range(0, len(self.factory.coins)):
      coin = self.factory.coins[i]
      status = returnSlip[i]
      gotAcceptableResponse = True
      badACoin = True
      if status == "0":
        badACoin = False
      elif status == "3":
        log_msg("ACoin deposit failed.  Some node must have double-spent.", 1)
      elif status == "2":
        log_msg("ACoin deposit failed.  You apparently already sent this acoin.", 1)
      elif status == "1":
        log_msg("ACoin deposit failed.  ACoin was not valid?  %s" % (repr(coin.write_binary())), 0)
      else:
        log_msg("Bank returned unknown status message:  %s" % (status), 0)
        gotAcceptableResponse = False
      if badACoin:
        #close the circuit, they're trying to cheat us!
        if coin.originCircuit:
          coin.originCircuit.close()
    self.transport.loseConnection()
      
class ACoinDepositFactory(BankMessages.BankConnectionFactory):
  """Factory for DEPOSIT messages"""
  protocol = ACoinDepositProtocol
  def __init__(self, bank, coins, finishedDeferred=None):
    BankMessages.BankConnectionFactory.__init__(self, bank)
    if not coins:
      self.coins = []
    else:
      self.coins = copy.copy(list(coins))
    self.gotResponse = False
    self.finishedDeferred = finishedDeferred
    
  def clientConnectionFailed(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionFailed(self, connector, reason)
    self.on_done(reason)
  
  def clientConnectionLost(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionLost(self, connector, reason)
    self.on_done(reason)
    
  def on_done(self, reason):
    self.bank.acoinDepositInProgress = False
    if self.gotResponse:
      for coin in self.coins:
        if coin in self.bank.depositingACoins:
          self.bank.depositingACoins.remove(coin)
        else:
          log_msg("Tried to deposit a coin we didnt even have?", 0)
      if self.finishedDeferred:
        self.finishedDeferred.callback(True)
    else:
      if self.finishedDeferred:
        self.finishedDeferred.errback(reason)
        