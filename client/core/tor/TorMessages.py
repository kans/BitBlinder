#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Transfer messages required for payment"""

from twisted.internet.defer import DeferredList

 
from core.tor import TorCtl
from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

#: to indicate the type of message received from Tor from another relay
MESSAGE_CODES = {
  "setup":         1,
  "setup_reply":   2,
  "payment":       3, 
  "receipt":       4,
  "bank_relay":    5,
  "dht_request":   6,
  "dht_response":  7
}

class BaseCircuit():
  """Represents a circuit, in the strict Tor sense, at this relay.
  May have started here or somewhere else."""
  def __init__(self, torApp, prevHexId, nextHexId, prevCircId, nextCircId):
    """Initialization
    @param prevHexId:  hex-encoded ID of the previous relay.  None if this is the first relay in the circuit.
    @type  prevHexId:  str or None
    @param nextHexId:  hex-encoded ID of the next relay.  None if this is the last relay in the circuit.
    @type  nextHexId:  str or None
    @param prevCircId:  the Tor-level circuit ID for the previous hop in this circuit.  0 if there is no previous hop.
    @type  prevCircId:  int
    @param nextHexId:  the Tor-level circuit ID for the previous hop in this circuit.  0 if there is no next hop.
    @type  nextHexId:  int"""
    self.torApp = torApp
    self.prevHexId = prevHexId
    self.nextHexId = nextHexId
    self.prevCircId = prevCircId
    self.nextCircId = nextCircId
    #: storage for messages that have only been partially received (if they were too long for a single Tor cell)
    self.buffer = ""
    #: the classes that handle incoming messages.  Maps from message name to the appropriate handler
    self.messageHandlers = {}
    #: whether this circuit is closed or not
    self.isClosed = False
    
  def add_handler(self, handler):
    implementedMessages = handler.get_implemented_messages()
    for msgName in implementedMessages:
      assert msgName not in self.messageHandlers
      self.messageHandlers[msgName] = handler
      
  def close(self):
    self.isClosed = True
    
  def is_closed(self):
    return self.isClosed
    
  def send_direct_tor_message(self, msg, msgType, forward=True, numHops=1, sendOverCircuit=False):
    """Tunnel a message through Tor.  There are two ways to send data:
    
    sendOverCircuit=True:  These messages are visible (plain-text) to the hops 
    that they pass through!  Callers are responsible for any necessary secrecy 
    and intergrity.
    
    sendOverCircuit=False:  These messages are encrypted like normal, relayed 
    Tor cells.  They are thus encrypted and authenticated, but messages may not 
    be sent between two relays (only between the origin and relays)
    
    In either case, messages that are too long will be sent in multiple cells.
    
    @param msg:  the message to send
    @type  msg:  str
    @param msgType:  the type of message.  Must be one of MESSAGE_CODES.
    @type  msgType:  str
    @param forward:  whether to send towards the exit (True) or towards the origin (False)
    @type  forward:  bool
    @param numHops:  how many relays to traverse before the message is delivered.
                     MUST NOT BE 0--in that case, call the handler directly yourself.
    @type  numHops:  int
    @param sendOverCircuit:  whether to send over the circuit (True) or simply send over OR connections to adjacent hops (False)
    @type  sendOverCircuit:  bool"""
    
    if not self.torApp.is_ready():
      raise TorCtl.TorCtlClosed
    if self.isClosed:
      log_msg("Cannot send Tor message, circuit was closed (%s)" % (msgType))
      return
    #if numHops is 0, you should handle the message yourself, not send it
    assert numHops != 0, "cannot send a zero hop message"
    msg = Basic.write_byte(MESSAGE_CODES[msgType]) + msg
    #put the length in front of the message:
    msgLen = len(msg)
    msg = Basic.write_short(msgLen) + msg
    #who to send it to:
    nextHexId = self.nextHexId
    nextCircId = self.nextCircId
    if not forward:
      nextCircId = self.prevCircId
      nextHexId = self.prevHexId
    dList = []
    #different message lengths depending on if sendOverCircuit if True or False:
    if sendOverCircuit:
      #are sent as normal relayed messages, so they should be this long
      WRITABLE_BYTES = 498
    else:
      #since the Tor cell is 512 bytes, but we need 2 for circid, and 1 for the cell command
      WRITABLE_BYTES = 507
    while len(msg) > 0:
      dataToSend = msg[:WRITABLE_BYTES]
      msg = msg[WRITABLE_BYTES:]
      def add_padding(tmp, desiredLen):
        extraChars = desiredLen - len(tmp)
        return tmp + (" " * extraChars)
      dataToSend = add_padding(dataToSend, WRITABLE_BYTES)
      dataToSend = dataToSend.encode("base64")
      dataToSend = dataToSend.replace('\n', '').replace('=', '')
      #convert sendOverCircuit to "1" or "0" for the control connection:
      if sendOverCircuit:
        sendOverCircuitToken = "1"
      else:
        sendOverCircuitToken = "0"
      dataToSend = "SENDPAYMENT %s %s %s %s %s\r\n" % (nextHexId, nextCircId, dataToSend, numHops, sendOverCircuitToken)
      d = self.torApp.conn.sendAndRecv(dataToSend)
      dList.append(d)
    d = DeferredList(dList)
    def response(result):
      for x in result:
        if not x[0]:
          raise Exception(str(x))
        if x[1][0][0] != '250':
          raise Exception(str(result))
      read, write = x[1][0][1].split(" ")
      read = int(read)
      write = int(write)
      return (read, write)
    d.addCallback(response)
    def error(failure):
      #this happens occasionally when the circuit is closed at approximately the same time that we send a payment
      #it can be safely ignored because the circuit is closed and we already learned about it
      if "552 Cannot find circuit with id" in str(failure):
        log_msg("A circuit that we tried to send a payment message to was closed.  Oops.", 4)
        self.close()
        return
      #otherwise, log an error because this is unexpected
      log_ex(failure, "SENDPAYMENT failed for circuit=%s" % (nextCircId), [TorCtl.ErrorReply])
    d.addErrback(error)
    return d

  def message_arrived(self, msg):
    """Called when a payment message is received via the controller.
    Is responsible for piecing it back together into the actual message.
    @param msg:  the data received from Tor
    @type  msg:  str"""
    self.buffer += msg
    #is the whole message here?
    msgLen, msgData = Basic.read_short(self.buffer)
    if len(msgData) >= msgLen:
      msgData = msgData[:msgLen]
      #we just discard the rest of the cell, two messages are never packed in the same cell currently
      self.buffer = ""
      #what type of message is this?
      msgType, msgData = Basic.read_byte(msgData)
      #ok, now handle that message:
      for msgName in MESSAGE_CODES.keys():
        if msgType == MESSAGE_CODES[msgName]:
          #if we don't know how to handle this message, just close the circuit
          if msgName not in self.messageHandlers:
            log_msg("Remote request for %s, which we do not know how to handle" % (msgName), 1)
            self.close()
            return
          #get the handler:
          handler = self.messageHandlers[msgName]
          #get the handler function:
          funcName = "handle_%s" % (msgName)
          if not hasattr(handler, funcName):
            raise Exception("%s cannot handle %s payment message?" % (handler, msgName))
          f = getattr(handler, funcName)
          f(msgData)
          return
      #uhh, not sure how to handle this message:
      raise Exception("Unknown message type for payment message:  %s" % (msgType))
    
class TorMessageHandler:
  def __init__(self, baseCircuit):
    self.baseCircuit = baseCircuit
    
  def send_direct_tor_message(self, *args, **kwargs):
    return self.baseCircuit.send_direct_tor_message(*args, **kwargs)
    
  def get_implemented_messages(self):
    """Must override this function to return a list of messages that you want to handle"""
    raise NotImplementedError()
  