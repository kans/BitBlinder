#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Transfer messages required for payment"""

from twisted.internet.defer import TimeoutError

from core.bank import BankMessages
from core.bank import UDPPayment
from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.tor import PaymentMessageHandler
from core.tor import PaymentStream

class ServerPaymentHandler(PaymentMessageHandler.PaymentMessageHandler):
  """Represents a circuit at a relay (the circuit did NOT originate here)"""
  def __init__(self, bank, baseCircuit):
    PaymentMessageHandler.PaymentMessageHandler.__init__(self, baseCircuit)
    self.bank = bank
    #: our requests for payment.  Maps from ID to ACoinRequest
    self.requests = {}
    #: the number of the next request ID to use
    self.currentRequestId = 0
    
  def get_implemented_messages(self):
    return ("setup", "payment", "bank_relay")
    
  def handle_setup(self, msg):
    """Handle a setup message.  Just add tokens and send the reply."""
    self.send_setup_reply()
    self.add_start_tokens()
    
  def generate_payment_request_message(self):
    """Create a payment request object, store it for later, increase ID, and create the message associated with it
    @returns: str (message for payment request)"""
    #REFACTOR
    cost = self.torApp.get_relay().get_cost()
    interval = self.bank.currentACoinInterval
    #generate ACoin request
    request = BankMessages.make_acoin_request(self.bank, interval, cost)
    request.id = self.currentRequestId
    self.requests[request.id] = request
    self.currentRequestId += 1
    return Basic.write_long(request.id) + request.msg + Globals.PRIVATE_KEY.sign(request.msg)
    
  def get_prefix(self):
    """@returns:  the beginning of the message from this relay"""
    #send back the PAR version first, so that people can deal with the message intelligently
    msg = Basic.write_byte(self.parVersion)
    #send back our hexid, so they know who this is from:
    msg += Basic.write_hexid(Globals.FINGERPRINT)
    return msg
   
  def send_setup_reply(self):
    """Send a bunch of payment requests to the origin node"""
    msg = self.get_prefix()
    #send back the number of payment tokens that we will send:
    msg += Basic.write_byte(PaymentStream.MAX_MERCHANT_TOKENS)
    #pack each of the payment tokens:
    for i in range(0, PaymentStream.MAX_MERCHANT_TOKENS):
      msg += self.generate_payment_request_message()
    #finally, send the message back to the customer
    self.send_direct_tor_message(msg, "setup_reply", False, 3)

  def handle_payment(self, msg):
    """Unpack, process, and respond to a payment message.
    @param msg:  the payment message from the origin.
    @type  msg:  str"""
    #if there are any failures, log them, and close the circuit:
    try:
      #read the PAR protocol version:
      version, msg = Basic.read_byte(msg)
      assert version == 1, "currently only accept PAR version 1"
      readTokens, msg = Basic.read_int(msg)
      writeTokens, msg = Basic.read_int(msg)
      #read their request ID too
      theirId, msg = Basic.read_long(msg)
      #read the number of coins:
      numCoins, msg = Basic.read_byte(msg)
      #read each coin:
      creditsEarned = 0
      requests = []
      for i in range(0, numCoins):
        #what type of coin is this?
        coinType, msg = Basic.read_byte(msg)
        #we only accept acoins for now:
        assert coinType == PaymentStream.COIN_TYPES['A'], "bad coin type"
        #get the matching request:
        requestId, msg = Basic.read_long(msg)
        requests.append(requestId)
      assert len(msg) % numCoins == 0, "bad payment message length"
      coinLen = len(msg) / numCoins
      for requestId in requests:
        #if this is not true, there wont even be another part to the response
        assert Basic.read_byte(msg)[0] == ord('0'), "bad leading byte in payment message"
        blob, msg = msg[:coinLen], msg[coinLen:]
        request = self.requests[requestId]
        del self.requests[requestId]
        code, sig = Basic.read_byte(blob)
        #validate the ACoin
        coin = BankMessages.parse_acoin_response(self.bank, sig, request)
        if not coin:
          raise Exception("Invalid ACoin sent for payment!")
        #success!
        creditsEarned += coin.get_expected_value()
        coin.originCircuit = self
        self.bank.on_earned_coin(coin)
      receiptMessageDeferred = self.send_receipt_message(theirId, numCoins)
      if not receiptMessageDeferred:
        return
      #check that they paid enough:
      requestedTokens = readTokens + writeTokens
      paidTokens = creditsEarned * Globals.CELLS_PER_PAYMENT
      if paidTokens < requestedTokens:
        raise Exception("Relays asked for %s, but only paid for %s" % (requestedTokens, paidTokens))
      #inform Tor that we got a payment message:
      addTokensDeferred = self.add_tokens(readTokens, writeTokens)
      if not addTokensDeferred:
        return
      def response(result):
        if result:
          read, write = result
          log_msg("%s paid us %s for exit stream, now %d / %d" % (Basic.clean(self.baseCircuit.prevHexId[:4]), creditsEarned, read, write), 3, "par")
      addTokensDeferred.addCallback(response)
    except Exception, error:
      log_ex(error, "Got bad PAR message")
      self.close()
      
  def send_receipt_message(self, theirId, numTokens):
    """Send a new payment request after a successful payment
    @param theirId:  the id that the origin has associated with this payment
    @type  theirId:  int
    @param numTokens:  how many payment requests to send back to the origin
    @type  numTokens:  int
    @returns:  deferred (triggered when message is done sending)"""
    msg = self.get_prefix()
    msg += Basic.write_long(theirId)
    msg += Basic.write_byte(numTokens)
    for i in range(0, numTokens):
      msg += self.generate_payment_request_message()
    return self.send_direct_tor_message(msg, "receipt", False, 3)
    
  def handle_bank_relay(self, msg):
    """Send a message to the bank on behalf of someone else, then send the reply onward
    @param msg:  the message to relay
    @type  msg:  str"""
    version, msg = Basic.read_byte(msg)
    assert version == 1, "only accepts version 1 of PAR protocol"
    responseHop, msg = Basic.read_byte(msg)
    bankMsg, msg = Basic.read_lenstr(msg)
    responseMsg, msg = Basic.read_lenstr(msg)
    payment = UDPPayment.UDPPayment(self.bank, bankMsg)
    paymentDeferred = payment.get_deferred()
    def success(response, responseMsg=responseMsg, responseHop=responseHop):
      responseMsg += response
      if responseHop != 0:
        self.send_direct_tor_message(responseMsg, "payment", True, responseHop)
      else:
        self.handle_payment(responseMsg)
    paymentDeferred.addCallback(success)
    def failure(error):
      if error and hasattr(error, "value") and issubclass(type(error.value), TimeoutError):
        #TODO:  this indicates that the bank is down, or something is wrong with their network?
        log_msg("Relayed payment timed out  :(", 0, "par")
      else:
        log_ex(error, "Relaying payment message failed!")
    paymentDeferred.addErrback(failure)
    
  def close(self):
    """Close the relayed circuit (for bad messages or payments)
    @returns:  Deferred (triggered when circuit is closed)"""
    return self.add_tokens(-1, -1)
    
