#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Transfer messages required for payment"""

from twisted.internet.defer import Deferred, DeferredList
from twisted.internet import defer
from twisted.python import failure

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common import Globals
from common.classes import Scheduler
from core.tor import PaymentMessageHandler
from core.tor import PaymentStream
from core.tor import TorCtl

class ClientPaymentHandler(PaymentMessageHandler.PaymentMessageHandler):
  """A class representing a circuit in Tor that began here"""
  def __init__(self, bank, baseCircuit, circ):
    PaymentMessageHandler.PaymentMessageHandler.__init__(self, baseCircuit)
    self.circ = circ
    self.bank = bank
    #: tracks request payments before setup is complete
    self.queuedReadTokens = 0
    self.queuedWriteTokens = 0
    #: tracks amount of payment that is in progress
    self.inflightReadTokens = 0
    self.inflightWriteTokens = 0
    #: have we started the setup process?
    self.setupStarted = False
    #: have we finished the setup process?
    self.setupDone = False
    #: mapping from hop id hex -> PaymentStream
    self.paymentStreams = {}
    #: create the PaymentStreams
    hop = 1
    for relay in self.circ.finalPath:
      self.paymentStreams[relay.desc.idhex] = PaymentStream.PaymentStream(relay.desc.idhex, hop, self)
      hop += 1
    
  def _on_setup_timeout(self):
    if not self.setupDone:
      self.circ.on_done()
      
  def get_implemented_messages(self):
    return ("setup_reply", "receipt")
      
  def get_payment_stream(self, msg):
    """Determine which PaymentStream should handle this message
    @param msg:  the message, reads the hexid off the front
    @type  msg:  str
    @returns:  PaymentStream"""
    hexId, msg = Basic.read_hexid(msg)
    return self.paymentStreams[hexId], msg

  def start(self):
    """Initializes the ClientPaymentHandler.  Have to convert the global Circuit ID to the Tor one.
    @returns:  Deferred (triggered for circuit id response from Tor control)"""
    if not self.torApp.is_ready():
      return defer.fail(failure.Failure(TorCtl.TorCtlClosed()))
    #convert our circuit id to a nextCircId
    torDeferred = self.torApp.conn.sendAndRecv("CONVERTCIRCID %s\r\n" % (self.baseCircuit.nextCircId))
    def response(result):
      self.baseCircuit.nextCircId = int(result[0][1])
      self.torApp.set_par_handler(self.baseCircuit.nextHexId, self.baseCircuit.nextCircId, self.baseCircuit)
    torDeferred.addCallback(response)
    return torDeferred
    
  def send_setup_message(self):
    """Send the setup messages from each PaymentStream"""
    if not self.setupStarted:
      log_msg("circ=%d:  Sending PAR setup message" % (self.circ.id), 3, "par")
      self.setupStarted = True
      self.inflightReadTokens += PaymentMessageHandler.START_READ_TOKENS
      self.inflightWriteTokens += PaymentMessageHandler.START_WRITE_TOKENS
      for paymentStream in self.paymentStreams.values():
        paymentStream.send_setup()
      #schedule a timeout so we dont wait forever:
      def par_setup_timeout():
        if not self.setupDone:
          #END_CIRC_REASON_TIMEOUT
          if not self.circ.is_done():
            self.circ.close(10)
      Scheduler.schedule_once(PaymentStream.PAR_TIMEOUT, par_setup_timeout)
    
  def all_setup_done(self):
    """Check if setup is done for each PaymentStream
    @returns:  True if all setup is done, False otherwise"""
    for paymentStream in self.paymentStreams.values():
      if not paymentStream.setupDone:
        return False
    return True
    
  def handle_setup_reply(self, msg):
    """Handle a setup reply.  Send it to the appropriate PaymentStream, then check if they are all done"""
    log_msg("circ=%d:  PAR setup done." % (self.circ.id), 3, "par")
    #unpack the messages:
    forwardParVersion, msg = Basic.read_byte(msg)
    if forwardParVersion < self.parVersion:
      self.parVersion = forwardParVersion
    payStream, msg = self.get_payment_stream(msg)
    payStream.handle_setup_reply(forwardParVersion, msg)
    if self.all_setup_done():
      initialTokensDeferred = self.add_start_tokens()
      #this usually happens if the circuit is already closed, if not, an exception will already be logged
      if not initialTokensDeferred:
        self.circ.on_done()
        return
      def initial_tokens_added(result):
        self.circ.initialTokensAdded = True
        self._add_tokens_callback(result, PaymentMessageHandler.START_READ_TOKENS, PaymentMessageHandler.START_WRITE_TOKENS)
        return result
      initialTokensDeferred.addCallback(initial_tokens_added)
      initialTokensDeferred.addErrback(self.generic_error_handler)
      self.setupDone = True
      #send any payment requests that are waiting on the setup:
      reads = self.queuedReadTokens
      writes = self.queuedWriteTokens
      self.queuedReadTokens = 0
      self.queuedWriteTokens = 0
      if self.queuedReadTokens or self.queuedWriteTokens:
        self.send_payment_request(reads, writes)
      self.circ.on_par_ready()
    
  def send_payment_request(self, readTokens, writeTokens):
    """Called by a Circuit object when it wants to actually make a payment
    @param readTokens:  the number of read tokens to pay for at each hop in the circuit
    @type  readTokens:  int
    @param writeTokens:  the number of read tokens to pay for at each hop in the circuit
    @type  writeTokens:  int"""
    assert (readTokens + writeTokens) / Globals.CELLS_PER_PAYMENT, "tried to pay for bad number of cells"
    #make sure our setup is done:
    if not self.setupDone:
      #have we even started?
      if not self.setupStarted:
        self.send_setup_message()
      self.queuedReadTokens += readTokens
      self.queuedWriteTokens += writeTokens
      return
    #dont bother trying to send payments for circuits that are already closed
    if self.circ.is_done():
      return
    #send the payments
    deferreds = []
    for paymentStream in self.paymentStreams.values():
      deferreds.append(paymentStream.send_payment(readTokens, writeTokens))
    paymentsDoneDeferred = DeferredList(deferreds)
    paymentsDoneDeferred.addErrback(self.generic_error_handler)
    addTokensDeferred = Deferred()
    self.inflightReadTokens += readTokens
    self.inflightWriteTokens += writeTokens
    #timeout in case the payment fails.  We will close the circuit in this case.
    event = Scheduler.schedule_once(PaymentStream.PAR_TIMEOUT, self.all_receipts_received, None, addTokensDeferred, readTokens, writeTokens, None)
    paymentsDoneDeferred.addCallback(self.all_receipts_received, addTokensDeferred, readTokens, writeTokens, event)
    addTokensDeferred.addCallback(self._add_tokens_callback, readTokens, writeTokens)
    addTokensDeferred.addErrback(self.generic_error_handler)
    
  def _add_tokens_callback(self, result, readTokens, writeTokens):
    self.inflightReadTokens -= readTokens
    self.inflightWriteTokens -= writeTokens
    self.circ.handle_token_response(result[0], result[1])
    log_msg("circ=%d:  now has R=%.2fMB W=%.2fMB" % (self.circ.id, self.circ.payedReadBytes / (1024.0*1024.0), self.circ.payedWriteBytes / (1024.0*1024.0)), 3, "par")
    
  def handle_receipt(self, msg):
    """Handle a receipt message from Tor control"""
    version, msg = Basic.read_byte(msg)
    payStream, msg = self.get_payment_stream(msg)
    payStream.handle_receipt(msg)
      
  def all_receipts_received(self, results, receiptAction, readTokens, writeTokens, event):
    """Called when all receipts have been received by each PaymentStream
    Will add tokens locally and update inflight payments"""
    #this means that we must have timed out:
    if not results:
      log_msg("PAR timed out while waiting for receipts  :(", 0)
      #END_CIRC_REASON_TIMEOUT
      if not self.circ.is_done():
        self.circ.close(10)
      return
    #validate that all results were successful
    for resultTuple in results:
      if not resultTuple[0]:
        log_msg("One of the receipts had a problem, closing circuit:  %s" % (str(resultTuple)), 0)
        #END_CIRC_REASON_REQUESTED
        if not self.circ.is_done():
          self.circ.close(3)
        return
    #otherwise, cancel the timeout:
    if event and event.active():
      event.cancel()
    #just add our tokens:
    addTokensDeferred = self.add_tokens(readTokens, writeTokens)
    if not addTokensDeferred:
      return
    #and we're done!  :)
    def response(result):
      if result:
        receiptAction.callback(result)
    addTokensDeferred.addCallback(response)
    addTokensDeferred.addErrback(self.generic_error_handler)
      
  def query_payments(self):
    """Ask Tor about how many read and write tokens this circuit has.
    @returns: Deferred (triggered when Tor control gets the response)"""
    return self.add_tokens(0, 0)
    
  def send_direct_tor_message(self, msg, msgType, forward=True, numHops=1, sendOverCircuit=False):
    if self.circ.is_done():
      log_msg("Not sending direct tor message because circuit (%s) is closed." % (self.circ.id))
      return None
    return PaymentMessageHandler.PaymentMessageHandler.send_direct_tor_message(self, msg, msgType, forward, numHops, sendOverCircuit)
    
  def add_tokens(self, readTokens, writeTokens):
    if self.circ.is_done():
      log_msg("Not adding tokens because circuit (%s) is closed." % (self.circ.id))
      return None
    return PaymentMessageHandler.PaymentMessageHandler.add_tokens(self, readTokens, writeTokens)
