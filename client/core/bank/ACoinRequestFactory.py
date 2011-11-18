#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Protocol for withdrawing ACoins from the bank (debited from your account)"""

import struct

from twisted.protocols.basic import Int32StringReceiver

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common import Globals
from core import ProgramState
from core.bank import BankMessages

class ACoinRequestProtocol(Int32StringReceiver):
  """Protocol to request ACoins from the bank"""
  PROTOCOL_VERSION = 1
  MAX_LENGTH = 128 * 1024 * 1024 #128 megabytes
  def connectionMade(self):
    msg = self.factory.bank.make_bank_prefix(self.PROTOCOL_VERSION, 'acoin request')
    #the bank needs to know what to do with the binary stuffs
    msg += struct.pack('!HI', self.factory.number, self.factory.value)
    for request in self.factory.requests:
      msg += struct.pack('!%ss'%(Globals.ACOIN_KEY_BYTES), request.msg)
    encryptedMsg = self.factory.bank.encrypt_message(msg)
    self.sendString(encryptedMsg)
    log_msg("ACoin REQUEST sent. (%s coins)" % (self.factory.number), 4)
  
  def stringReceived(self, encryptedMsg):
    self.responseReceived = True
    self.transport.loseConnection()
    blob = self.factory.bank.decrypt_message(encryptedMsg)
    log_msg("ACoin REQUEST response received.", 4)
    responseCode, blob = Basic.read_byte(blob)
    #we had enough credits in our account
    if responseCode == 0:
      (newBalance, number), coins = Basic.read_message('!II', blob)
      #update the balance
      self.factory.bank.on_new_balance_from_bank(newBalance)
      acoinStrFormat = "%ss" % (Globals.ACOIN_KEY_BYTES)
      format = '!' + (acoinStrFormat * number)
      sigs = list(struct.unpack(format, coins))
      while len(self.factory.requests) > 0:
        request = self.factory.requests.pop(0)
        sig = sigs.pop(0)
        coin = BankMessages.parse_acoin_response(self.factory.bank, sig, request, ProgramState.DEBUG)
        if coin:
          self.factory.bank.add_acoin(coin)
        else:
          log_msg("Got an invalid ACoin from the bank!?", 3)
    #the bank could not check out the coins because our account doesn't have enough credits!
    else:
      (newBalance,), blob = Basic.read_message('!I', blob)
      self.factory.bank.on_new_balance_from_bank(newBalance)

class ACoinRequestFactory(BankMessages.BankConnectionFactory):
  """Factory for requesting ACoins"""
  protocol = ACoinRequestProtocol
  def __init__(self, bank, value, number):
    BankMessages.BankConnectionFactory.__init__(self, bank)
    #: the value for each ACoin to have, individually
    self.value = value
    #:  a list of all ACoinRequests
    self.requests = []
    #: how many coins to request
    self.number = number
    interval = self.bank.currentACoinInterval
    for i in range(0, number):
      #store the values for later:
      self.requests.append(BankMessages.make_acoin_request(self.bank, interval, value))
      
  def clientConnectionFailed(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionFailed(self, connector, reason)
    self.bank.acoinRequestInProgress = False
  
  def clientConnectionLost(self, connector, reason):
    BankMessages.BankConnectionFactory.clientConnectionLost(self, connector, reason)
    self.bank.acoinRequestInProgress = False
    
