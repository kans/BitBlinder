#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""The client Twisted factory for SOCKS5 connections"""

from twisted.internet import tcp
from twisted.internet import protocol, defer
from twisted.python import failure

from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from core.network.socks import ClientFactory

class ClientConnector(tcp.Connector):
  """Object used to connect to some host using intermediate server
  supporting SOCKS5 protocol.

  This IConnector manages one connection.
  """
  def __init__(self, sockshost, socksport, host, port, otherFactory,
    reactor=None, method="CONNECT", login=None, password=None,
    timeout=None, readableID=None, deferred=None):
    """ Creates IConnector to connect through SOCKS

    @type sockshost: string
    @param sockshost: SOCKS5 compliant server address.

    @type socksport: int
    @param socksport: Port to use when connecting to SOCKS.

    @type timeout: float
    @param timeout: Time to wait until client connects, then fail.

    @type readableID: string
    @param readableID: Some human readable ID for this connection.

    See ClientProtocol constructor for details on other params.
    """
    factory = ClientFactory.ClientFactory(method=method, sockshost=sockshost,
        socksport=socksport, host=host, port=port, login=login,
        password=password, otherFactory=otherFactory, timeout=timeout,
        readableID=readableID, deferred=deferred)
    
    if not reactor:
      reactor = Globals.reactor
      
    tcp.Connector.__init__ (self, host=sockshost, port=socksport,
        factory=factory, timeout=timeout, bindAddress=None,
        reactor=reactor)