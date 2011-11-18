#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Represents the DHT service for remote clients (which is request through Tor)"""

import socket

from core.tor import TorMessages
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from core.network.dht import Node
    
class DHTProvider(TorMessages.TorMessageHandler):
  def __init__(self, baseCircuit, dhtNode):
    TorMessages.TorMessageHandler.__init__(self, baseCircuit)
    self.dhtNode = dhtNode
    self.responses = {}
    self.currentTransactionId = 0
    
  def get_implemented_messages(self):
    return ("dht_request",)
    
  def handle_dht_request(self, data):
    log_msg("Got remote DHT request", 4, "dht")
    #unpack and validate the message:
    version, data = Basic.read_byte(data)
    assert version == Node.VERSION
    #read the infohash:
    vals, data = Basic.read_message("20s", data)
    infohash = vals[0]
    #read each peer:
    peers = set()
    while len(data) > 0:
      #what type of peer?  (ip or url)
      peerType, data = Basic.read_byte(data)
      #IP peer:
      if peerType == 0:
        vals, data = Basic.read_message("!4sH", data)
        host = socket.inet_ntoa(vals[0])
        port = vals[1]
      #URL peer:
      elif peerType == 1:
        host, data = Basic.read_lenstr(data)
        port, data = Basic.read_short(data)
      #bad peer type:
      else:
        raise Exception("Unknown peer address type:  %s" % (peerType))
      peers.add((host, port))
    #note that there is a new transaction:
    transactionId = self.currentTransactionId
    self.responses[transactionId] = ""
    self.currentTransactionId += 1
    #now add each peer:
    for host, port in peers:
      #make sure it's not one of our defaults
      #TODO:  in the future, make sure we don't already know about it anyway?  Eh, maybe that will break DHT somehow?
      if (host, port) not in Node.BOOTSTRAP_NODES:
        log_msg("Neat, someone told us about a new DHT node", 2)
        self.dhtNode.add_contact(host, port)
    #and then send out the request:
    def response(data, transactionId=transactionId):
      #is this the last message?
      if len(data) <= 0:
        #then send the response for this transaction:
        self._send_peers(transactionId)
      #otherwise, just accumulate the data for later:
      else:
        self.responses[transactionId] += "".join(data[0])
    self.dhtNode.get_peers(infohash, response)

  def _send_peers(self, transactionId):
    #don't try to send a response if that circuit was already closed
    if self.baseCircuit.is_closed():
      return
    log_msg("Sending remote DHT response", 4, "dht")
    responseData = self.responses[transactionId]
    #make the message:
    msg = Basic.write_byte(Node.VERSION)
    #just dump all the peers
    msg += responseData
    #and send it off:
    self.send_direct_tor_message(msg, "dht_response", False, 3, True)
  
