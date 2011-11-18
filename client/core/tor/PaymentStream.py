#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Transfer messages required for payment"""

import struct
from twisted.internet.defer import Deferred

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common import Globals
from common.Errors import InsufficientACoins
from common.classes import EncryptedDatagram

#: the type of coins being sent for payment.  Only one now...
COIN_TYPES = {
  "A": 1
}
#: what version of the protocol to use and accept
PAR_VERSION = 1
#: how long to wait for PAR operations (setup and payment) to finish.  If they fail to finish this quickly, the circuit will be closed.
PAR_TIMEOUT = 30.0
#: how many tokens merchants should send back after a setup message
MAX_MERCHANT_TOKENS = 4

class PaymentStream():
  """Object to track payments for a specific hop in a circuit that we built"""
  def __init__(self, hexId, hop, parClient):
    #: the hexId of the router that we make payments to
    self.hexId = hexId
    #: which hop in the circuit the router is
    self.hop = hop
    #: backreference to a ClientPaymentHandler (for sending messages, etc)
    self.parClient = parClient
    #: maps from merchant request ID to their tokens
    self.paymentTokens = {}
    #: maps from customer request ID to our deferreds, to be triggered when the receipt arrives
    self.paymentDeferreds = {}
    #: the current customer request ID
    self.currentRequestId = 0
    #: whether the setup process is done
    self.setupDone = False
    #: the PAR version to use for this relay
    self.version = 0
    #: a queue of in-progress payments
    self.pendingPayments = []
    #: which hop to use as the payment proxy.  1 is the only value that works right now
    self.paymentProxyHop = 1
    #: the public key for the relay that we send payments to
    self.key = parClient.torApp.relayKeys[self.parClient.circ.finalPath[self.hop-1].desc.idhex]
  
  def send_setup(self):
    """Send the initial setup message
    @returns: Deferred (triggered when message is sent)"""
    return self.parClient.send_direct_tor_message(Basic.write_byte(PAR_VERSION), "setup", True, self.hop)
    
  def read_payment_tokens(self, msg):
    """Read merchant payment tokens from a message"""
    #read the number of payment requests:
    numTokens, msg = Basic.read_byte(msg)
    #determine the size of the tokens:
    assert len(msg) % numTokens == 0, "bad payment token message"
    tokenSize = len(msg) / numTokens
    #read each of the payment requests:
    while msg:
      token, msg = msg[:tokenSize], msg[tokenSize:]
      requestId, token, tokenSig = struct.unpack("!L%ss%ss" % (Globals.ACOIN_KEY_BYTES, Globals.TOR_ID_KEY_BYTES), token)
      if not self.key.verify(token, tokenSig):
        #END_CIRC_REASON_TORPROTOCOL
        if not self.parClient.circ.is_done():
          log_ex("Signature invalid", "Error unpacking payment tokens")
          self.parClient.circ.close(1)
          return False
      self.paymentTokens[requestId] = token
    return True
    
  def handle_setup_reply(self, version, msg):
    """Parse the setup reply messages (just a bunch of payment requests)
    @param version: what version of the payment protocol the merchant would like to use
    @type  version:  int
    @param msg:  the setup reply message
    @type  msg:  str"""
    self.version = version
    if self.read_payment_tokens(msg):
      #ok, setup is definitely complete now
      self.setupDone = True
    
  def send_payment(self, readTokens, writeTokens):
    """Send a number of payments to the merchant (determined by read/writeTokens
    @param readTokens:  how many read tokens to pay the merchant for
    @type  readTokens:  int
    @param writeTokens:  how many write tokens to pay the merchant for
    @type  writeTokens:  int
    @returns:  Deferred (will be triggered after receipts have been received (ie, when the merchant has definitely been paid)"""
    #this deferred will be triggered when everything for this payment is done--ie, when we receive the receipt message
    finalDeferred = Deferred()
    finalDeferred.addErrback(self.parClient.generic_error_handler)
    curId = self.currentRequestId
    self.currentRequestId += 1
    self.paymentDeferreds[curId] = finalDeferred
    #if there are not enough tokens left, wait for more:
    numPayments = (readTokens + writeTokens) / Globals.CELLS_PER_PAYMENT
    assert numPayments <= MAX_MERCHANT_TOKENS, "not enough merchant tokens to send payments"
    if numPayments > len(self.paymentTokens):
      self.pendingPayments.append([readTokens, writeTokens, curId])
    else:
      self.start_bank_process(readTokens, writeTokens, curId)    
    return finalDeferred
      
  def start_bank_process(self, readTokens, writeTokens, paymentId):
    """Create the bank message, and send it to the payment proxy for relaying to the bank.
    @param readTokens:  how many read tokens to pay the merchant for
    @type  readTokens:  int
    @param writeTokens:  how many write tokens to pay the merchant for
    @type  writeTokens:  int
    @param paymentId:  the id for this payment, for tracking when it is completed
    @type  paymentId:  int
    """
    #generate the response message:
    msg  = Basic.write_byte(PAR_VERSION)
    msg += Basic.write_int(readTokens)
    msg += Basic.write_int(writeTokens)
    msg += Basic.write_long(paymentId)
    #figure out how many payments must be made:
    totalTokens = readTokens + writeTokens
    numPayments = totalTokens / Globals.CELLS_PER_PAYMENT
    msg += Basic.write_byte(numPayments)
    bankMsg = Basic.write_byte(numPayments)
    for i in range(0, numPayments):
      #get a token to use for this payment:
      requestId, token = self.paymentTokens.popitem()
      #send it to the bank for signing
      coin = self.parClient.bank.get_acoins(1)
      if not coin:
        paymentDeferred = self.paymentDeferreds[paymentId]
        del self.paymentDeferreds[paymentId]
        paymentDeferred.errback(InsufficientACoins("No ACoins left."))
        return
      coin = coin[0]
      self.parClient.circ.app.coinsSpent += 1
#      log_msg("Srsly, wtf is going on? %s" % (coin.interval), 4)
      bankMsg += coin.write_binary() + token
      msg += Basic.write_byte(COIN_TYPES['A']) + Basic.write_long(requestId)
    key = EncryptedDatagram.ClientSymKey(self.parClient.bank.PUBLIC_KEY)
    bankMsg = Basic.write_byte(1) + key.encrypt(Basic.write_byte(3) + bankMsg)
    msg = Basic.write_byte(PAR_VERSION) + Basic.write_byte(self.hop-1) + Basic.write_lenstr(bankMsg) + Basic.write_lenstr(msg)
    self.parClient.send_direct_tor_message(msg, "bank_relay", True, self.paymentProxyHop)
    
  def handle_receipt(self, msg):
    """Handle a receipt message from our merchant"""
    ourId, msg = Basic.read_long(msg)
    if not self.read_payment_tokens(msg):
      return
    #check if we are waiting on new tokens:
    if len(self.pendingPayments) > 0 and ((self.pendingPayments[0][0] + self.pendingPayments[0][1])/Globals.CELLS_PER_PAYMENT) <= len(self.pendingPayments):
      readTokens, writeTokens, paymentId = self.pendingPayments.pop(0)
      self.start_bank_process(readTokens, writeTokens, paymentId)
    #and trigger any callbacks waiting for this receipt
    paymentDeferred = self.paymentDeferreds[ourId]
    del self.paymentDeferreds[ourId]
    paymentDeferred.callback(True)
    
