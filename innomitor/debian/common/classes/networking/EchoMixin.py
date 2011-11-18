#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""The protocol used by our port testing servers."""

import struct
import socket

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.classes.networking import MessageProtocol

class BadEchoMessageFormat(Exception):
  pass

class EchoMixin:
  #: protocol version
  VERSION = 0
  #: acceptable methods of testing connections to clients
  TEST_TYPES = {0: "TCP",
               1: "TCP_reply",
               2: "UDP",
               3: "UDP_reply"}
  #: all messages involved in the Echo protocol
  MESSAGES = {"request": 0,
              "reply":   1}
              
  def write_request(self, data, protocol, replyPort):
    #write the header:
    msg = self._write_header("request")
    #determine the protocol ID:
    protocolType = None
    for protocolId, protocolName in self.TEST_TYPES.iteritems():
      if protocolName == protocol:
        protocolType = protocolId
        break
    assert protocolType != None, "Specified bad protocol:  %s" % (protocol)
    #write the protocol type:
    msg += Basic.write_byte(protocolType)
    #write the port:
    msg += Basic.write_short(replyPort)
    #finally, add the data:
    msg += data
    return msg
    
  def send_request(self, msg, host, port, protocol):
    assert protocol in self.TEST_TYPES.values(), "Unknown protocol:  %s" % (protocol)
    if protocol == "TCP":
      self._send_tcp(host, port, msg)
    elif protocol == "UDP":
      self._send_udp(host, port, msg)
    elif protocol == "UDP_reply":
      self._send_udp(host, port, msg)
    else:
      raise NotImplementedError()
            
  def read_request(self, data, host, transport):
    try:
      #read the header:
      data = self._read_header(data, "request")
      #read the protocol type:
      protocolType, data = Basic.read_byte(data)
      assert protocolType in self.TEST_TYPES, "Unknown echo protocol:  %s" % (protocolType)
      protocol = self.TEST_TYPES[protocolType]
      #read the port:
      port, data = Basic.read_short(data)
    except AssertionError, error:
      raise BadEchoMessageFormat(str(error))
    #call the handler:
    self.handle_request(host, port, data, protocol, transport)
    
  def handle_request(self, host, port, data, protocol, transport):
    log_msg("Got request from %s to send %s to %s" % (host, protocol, port))
    #make the reply:
    msg = self.write_reply(host, data)
    #and send it back
    self.send_reply(msg, host, port, protocol, transport)
    
  def write_reply(self, host, data):
    msg = self._write_header("reply")
    #write the host:
    msg += struct.pack("!4s", socket.inet_aton(host))
    #write the data:
    msg += data
    return msg
    
  def send_reply(self, msg, host, port, protocol, transport):
    assert protocol in self.TEST_TYPES.values(), "Unknown protocol:  %s" % (protocol)
    if protocol == "TCP":
      self._send_tcp(host, port, msg)
    if protocol == "TCP_reply":
      self._connect_tcp(host, port, msg, transport)
    elif protocol == "UDP":
      self._send_udp(host, port, msg)
    elif protocol == "UDP_reply":
      transport.write(msg, self.address)
    else:
      raise NotImplementedError()

  def read_reply(self, data, host):
    try:
      #read the header:
      data = self._read_header(data, "reply")
      #read the host:
      vals, data = Basic.read_message("!4s", data)
      host = socket.inet_ntoa(vals[0])
      #read the message:
      msg = data
    except AssertionError, error:
      raise BadEchoMessageFormat(str(error))
    #call the handler:
    self.handle_reply(host, msg)
      
  def handle_reply(self, host, data):
    raise NotImplementedError()
      
  def _write_header(self, msgName):
    #write the version
    msg = Basic.write_byte(self.VERSION)
    #note that this is a reply:
    msg += Basic.write_byte(self.MESSAGES[msgName])
    return msg
    
  def _read_header(self, data, msgName):
    #read the version
    version, data = Basic.read_byte(data)
    assert version == self.VERSION, "Bad version number: %s" % (version)
    #read the message type:
    msgType, data = Basic.read_byte(data)
    assert msgType == self.MESSAGES[msgName], "Bad message type: %s" % (msgType)
    return data
      
  def _send_tcp(self, host, port, data):
    Globals.reactor.connectTCP(host, port, MessageProtocol.TCPMessageFactory(data))
    
  def _send_udp(self, host, port, data):
    protocol = MessageProtocol.UDPMessageProtocol(data, host, port)
    listener = Globals.reactor.listenUDP(0, protocol)
    listener.stopListening()
    
  def _connect_tcp(self, host, port, msg, transport):
    factory = MessageProtocol.TCPMessageFactory("")
    connectionDeferred = factory.get_deferred()
    def callback(result, transport=transport, msg=msg):
      if result is True:
        transport.protocol.sendString(msg)
      transport.loseConnection()
    connectionDeferred.addCallback(callback)
    Globals.reactor.connectTCP(host, port, factory)
      