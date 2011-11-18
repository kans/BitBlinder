#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The client Twisted protocol for SOCKS5 connections"""

import struct

from twisted.internet.interfaces import ITransport
from twisted.internet import protocol
from twisted.python import failure

from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.network.socks import Errors

class ClientProtocol (protocol.Protocol):
  """ This protocol that talks to SOCKS5 server from client side.
  """
  __implements__ = ITransport,
  disconnecting = 0

  def __init__(self, sockshost, socksport, host, port, factory, otherProtocol,
    method="CONNECT", login=None, password=None):
    """ Initializes SOCKS session
    
    @type sockshost: string
    @param sockshost: Domain name or ip address of intermediate SOCKS server.

    @type socksport: int
    @param socksport: Port number of intermediate server.

    @type host: string
    @param host: Domain name or ip address where should connect or bind.

    @type port: int
    @param port: Port number where to connect or bind.

    @type otherProtocol: object
    @param otherProtocol: Initialised protocol instance, which will receive
        all I/O and events after SOCKS connected.

    @type login: string
    @param login: Sets user name if SOCKS server requires us to
        authenticate.

    @type password: string
    @param password: Sets user password if SOCKS server requires us
        to authenticate.

    @type method: string
    @param method: What to do: may be \"CONNECT\" only. Other
        methods are currently unsupported.
    """
    # login and password are limited to 256 chars
    #
    if login is not None and len (login) > 255:
      raise Errors.LoginTooLongError()

    if password is not None and len (password) > 255:
      raise Errors.PasswordTooLongError()

    # save information
    #
    self.method         = method
    self.host           = host
    self.port           = port
    self.login          = login
    self.password       = password
    self.state          = "mustNotReceiveData"
    self.otherProtocol  = otherProtocol
    self.factory        = factory
    
    self.nomnetStream = None
    
  def connectionMade(self):
    # prepare connection string with available authentication methods
    #

    log_msg("SOCKS5.connectionMade", 4, "socks")
    methods = "\x00"
    if not self.login is None:
      methods += "\x02"

    connstring = struct.pack ("!BB", 5, len (methods))

    self.transport.write (connstring + methods)
    self.state = "gotHelloReply"
    
    if self.factory.deferred:
      self.factory.deferred.callback(self)
      self.factory.deferred = None
    if hasattr(self.otherProtocol, "_socks_connect_finished"):
      self.otherProtocol._socks_connect_finished(self.transport.getHost().port)

  def dataReceived (self, data):
    #log_msg("SOCKS state=" + self.state, 4)
    method = getattr(self, 'socks_%s' % (self.state), self.socks_thisMustNeverHappen)
    method (data)
      
  def set_stream(self, stream):
    self.nomnetStream = stream
#      self.dataReceived, self.transport.write = Basic.replace_read_write_calls(stream, self.dataReceived, self.transport.write)

  def socks_thisMustNeverHappen (self, data):
    self.transport.loseConnection()
    raise Errors.UnhandledStateError ("This SOCKS5 self.state (%s) "\
        "must never happen %s" % (self.state, self))

  def socks_mustNotReceiveData (self, data):
    """ This error might occur when server tells something into connection
    right after connection is established. Server in this case is
    certainly not SOCKS.
    """
    self.transport.loseConnection()
    self.factory.clientConnectionFailed (self, failure.Failure (
        Errors.UnexpectedDataError ("Server must not send data before client %s" % self)))

  def socks_gotHelloReply (self, data):
    """ Receive server greeting and send authentication or ask to
    execute requested method right now.
    """
    #No acceptable methods. We MUST close
    if data == "\x05\xFF":
      log_msg("No acceptable methods, closing connection", 0, "socks")
      self.transport.loseConnection()
      return
      
    #Anonymous access allowed - let's issue connect
    elif data == "\x05\x00":
      self.sendCurrentMethod()
    
    #Authentication required
    elif data == "\x05\x02":
      self.sendAuth()
      
    #Unexpected input, fail
    else:
      self.transport.loseConnection()
      self.factory.clientConnectionFailed (self, failure.Failure (
          Errors.UnhandledData ("Server returned unknown reply in gotHelloReply")))

    #From now on SOCKS server considered alive - we've got reply
    self.factory.status = "connected"

  def socks_gotAuthReply (self, data):
    """ Called when client received server authentication reply,
        we or close connection or issue "CONNECT" command
    """
    if data == "\x05\x00":
      self.sendCurrentMethod()

  def sendAuth (self):
    """ Prepare login/password pair and send it to the server
    """
    command = "\x05%s%s%s%s" % (chr (len (self.login)), self.login,
        chr (len (self.password)), self.password)
    self.transport.write (command)

    self.state = "gotAuthReply"

  def sendCurrentMethod (self):
    method = getattr(self, 'socks_method_%s' % (self.method), self.socks_method_UNKNOWNMETHOD)
    method()

  def socks_method_UNKNOWNMETHOD (self):
    self.transport.loseConnection()
    self.factory.clientConnectionFailed (self, failure.Failure (
        Errors.UnknownMethod ("Method %s is unknown %s" % (self.method, self))))

  def socks_method_CONNECT (self):
    # Check if we have ip address or domain name
    #
    log_msg("socks_method_CONNECT host = " + Basic.clean(self.host), 4, "socks")

    # The FaceTime SOCKS5 proxy treats IP addr the same way as hostname
    # if _ip_regex.match (self.host):
    #     # we have dotted quad IP address
    #     addressType = 1
    #     address = socket.inet_aton (self.host)
    # else:
    #     # we have host name
    #     address = self.host
    #     addressType = 3

    address = self.host
    addressType = 3
    addressLen = len(address)

    #Protocol version=5, Command=1 (CONNECT), Reserved=0
    #command = struct.pack ("!BBBB", 5, 1, 0, addressType)

    command = struct.pack ("!BBBBB", 5, 1, 0, addressType, addressLen)
    portstr = struct.pack ("!H", self.port)

    self.transport.write (command + address + portstr)
    self.state = "gotConnectReply"

  def socks_gotConnectReply (self, data):
    """ Called after server accepts or rejects CONNECT method.
    """
    #No need to analyze other fields of reply, we are done
    if data[:2] == "\x05\x00":
      self.state = "done"
      self.factory.status = "established"
      
      self.otherProtocol.transport = self
      self.otherProtocol.connectionMade()
      return 

    errcode = ord (data[1])

    if errcode < len (Errors.SOCKS_errors):
      self.transport.loseConnection()
      self.factory.clientConnectionFailed (self, failure.Failure (
          Errors.ConnectError ("%s %s" % (Errors.SOCKS_errors[errcode], self))))
    else:
      self.transport.loseConnection()
      self.factory.clientConnectionFailed (self, failure.Failure (
          Errors.ConnectError ("Unknown SOCKS error after CONNECT request issued %s" % (self))))

  def socks_done (self, data):
    """ Proxy received data to other protocol.
    """
    self.otherProtocol.dataReceived (data)
      
  #
  # Transport relaying
  #
  def write(self, data):
    self.transport.write(data)
      
  #Josh:  added these 2 because I wanted TLS support, idk if it will work
  def startTLS(self, ctx):
    self.transport.startTLS(ctx)
    
  def startWriting(self):
    self.transport.startWriting()

  def writeSequence(self, data):
    self.transport.writeSequence(data)

  def loseConnection(self):
    self.disconnecting = 1
    self.transport.loseConnection()
    
    #if self.disconnecting != 1:
    #  self.disconnecting = 1
    #  self.transport.loseConnection()
    #  self.otherProtocol.loseConnection()

  def getPeer(self):
    return self.transport.getPeer()

  def getHost(self):
    return self.transport.getHost()
  
  def registerProducer(self, producer, streaming):
    self.transport.registerProducer(producer, streaming)

  def unregisterProducer(self):
    self.transport.unregisterProducer()

  def stopConsuming(self):
    self.transport.stopConsuming()
    