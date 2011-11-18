#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Transfer messages required for payment"""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.Errors import InsufficientACoins
from core.tor import TorCtl
from core.tor import TorMessages
from core.tor import PaymentStream

START_READ_TOKENS = Globals.CELLS_PER_PAYMENT/2
START_WRITE_TOKENS = Globals.CELLS_PER_PAYMENT - START_READ_TOKENS

class PaymentMessageHandler(TorMessages.TorMessageHandler):
  def __init__(self, baseCircuit):
    TorMessages.TorMessageHandler.__init__(self, baseCircuit)
    self.parVersion = PaymentStream.PAR_VERSION
    self.torApp = baseCircuit.torApp
    
  def add_tokens(self, readTokens, writeTokens):
    """Send an ADDTOKENS message to Tor.  There are 3 reasons for this:
    1.  To actually add tokens to the read/write buckets, in response to a payment
    2.  To simply query the read/write buckets (send 0 and 0)
    3.  To close the circuit (send -1 and -1)
    @param readTokens:  how many tokens to add to the buckets
    @type  readTokens:  int
    @param writeTokens:  how many tokens to add to the buckets
    @type  writeTokens:  int
    @returns:  Deferred (triggered when response is received from Tor)"""
    if not self.torApp.is_ready():
      raise TorCtl.TorCtlClosed()
    hexId = self.baseCircuit.prevHexId
    circId = self.baseCircuit.prevCircId
    #if this is the source of the circuit, there will be no previous entries, so use the next:
    if not hexId:
      hexId = self.baseCircuit.nextHexId
      circId = self.baseCircuit.nextCircId
    dataToSend = "ADDTOKENS %s %s %s %s\r\n" % (hexId, circId, readTokens, writeTokens)
    torDeferred = self.torApp.conn.sendAndRecv(dataToSend)
    def response(result):
      if not result:
        return None
      read, write = result[0][1].split(" ")
      read = int(read)
      write = int(write)
      return (read, write)
    def error(failure):
      log_ex(failure, "Failed to add tokens for circuit=%s" % (circId), [TorCtl.ErrorReply])
    torDeferred.addErrback(error)
    torDeferred.addCallback(response)
    return torDeferred
    
  def add_start_tokens(self):
    """Add initial tokens for a circuit, so that they dont have to make immediate payments"""
    return self.add_tokens(START_READ_TOKENS, START_WRITE_TOKENS)
    
  def generic_error_handler(self, error):
    log_ex(error, "Something bad happened", [InsufficientACoins])
    
