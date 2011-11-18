#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The client Twisted factory for SOCKS5 connections"""

import sys

from twisted.internet import protocol
from twisted.python import failure

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.network.socks import Errors
from core.network.socks import ClientProtocol

class ClientFactory (protocol.ClientFactory):
  def __init__(self, sockshost, socksport, host, port, otherFactory,
    method="CONNECT", login=None, password=None, timeout=60,
    readableID=None, deferred=None):
    """ Factory creates SOCKS5 client protocol to connect through it.
    See ClientProtocol constructor for details on params.
    
    @type globalTimeout: int
    @param globalTimeout: Seconds before connection is completely and
        unconditionally closed as is.

    @type readableID: string
    @param readableID: Some human readable ID for this connection.
    """
    self.sockshost      = sockshost
    self.socksport      = socksport
    self.host           = host
    self.port           = port
    self.method         = method
    self.login          = login
    self.password       = password
    self.otherFactory   = otherFactory
    self.timeout        = timeout
    self.readableID     = readableID
    self.deferred       = deferred

    # This variable contains current status of SOCKS connection,
    # useful for diagnosting connection, without knowing SOCKS
    # internal states. One of: "unconnected", "connected" (SOCKS
    # server replied and is alive), "established"
    #
    self.status = "unconnected"

  def startedConnecting (self, connector):
    # Set global timeout
    #
    if self.timeout is not None:
      log_msg("Set timeout %d sec" % self.timeout, 2, "socks")
      delayedcall = Globals.reactor.callLater (self.timeout, self.onTimeout,
                                       connector)
      setattr (self, "delayed_timeout_call", delayedcall)

    # inherited
    #
    protocol.ClientFactory.startedConnecting (self, connector)

  def onTimeout (self, connector):
    """ Timeout occured, can't continue and should stop immediately
    and unconditionally in the whatever state I am.
    """
    connector.disconnect()
    log_msg("%s timeout %d sec" % (self, self.timeout), 2, "socks")
    self.clientConnectionFailed (self, failure.Failure (
        Errors.GlobalTimeoutError ("Timeout %s" % self)))

  def stopFactory(self):
    """ Do cleanups such as cancelling timeout
    """
    try:
      if self.timeout is not None:
        self.delayed_timeout_call.cancel()
    except:
      pass

    protocol.ClientFactory.stopFactory (self)

  def buildProtocol (self, a):
    """ Connection is successful, create protocol and let it talk to peer.
    """
    proto = ClientProtocol.ClientProtocol(sockshost=self.sockshost,
        socksport=self.socksport, host=self.host, port=self.port,
        method=self.method, login=self.login, password=self.password,
        otherProtocol=self.otherFactory.buildProtocol(self.sockshost),
        factory=self)
    
    proto.factory = self
    return proto

  def __repr__ (self):
    return "<SOCKS %s>" % self.readableID

  def clientConnectionLost(self, connector, reason):
    rmap = reason
    
    if self.deferred:
      self.deferred.errback(reason)
      self.deferred = None
    try:
      if self.status != "established":
        # Tell about error
        log_msg("Connection LOST before SOCKS established %s" % self, 1, "socks")
        self.otherFactory.clientConnectionFailed (connector, rmap)
      else:
        self.otherFactory.clientConnectionLost (connector, rmap)
    except:
      ei = sys.exc_info()
      if not str (ei[0]).count ("AlreadyCalled"):
        raise
  
  def clientConnectionFailed(self, connector, reason):
    rmap = reason
    
    if self.deferred:
      self.deferred.errback(reason)
      self.deferred = None
    try:
      if self.status != "established":
        log_msg("Connection FAILED before SOCKS established %s" % self, 1, "socks")
        self.otherFactory.clientConnectionFailed (connector, rmap)
      else:
        self.otherFactory.clientConnectionFailed (connector, rmap)
    except:
      ei = sys.exc_info()
      if not str (ei[0]).count ("AlreadyCalled"):
        raise
                