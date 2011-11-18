#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""Server that echoes back any data sent to it, as well as your external IP address
Useful for testing whether your ports are forwarded correctly or if your internet 
connection is being filtered."""

import sys
import socket
import struct
import signal
import optparse
import os

from twisted.internet import reactor, defer, protocol
from twisted.protocols.basic import Int32StringReceiver

from common import Globals
Globals.reactor = reactor
from common.utils import Twisted
from common.classes.networking import EchoMixin

DEFAULT_PORT = 33351

if os.path.exists("THIS_IS_DEBUG"):
  from common.conf import Dev as Conf
  Globals.DEBUG = True
else:
  from common.conf import Live as Conf
  Globals.DEBUG = False

parser = optparse.OptionParser()
parser.add_option('-p', '--port', dest='port', type='int', default=DEFAULT_PORT, 
                  metavar="PORT", help='port to bind to serve clients')
(options, args) = parser.parse_args()
  
signal.signal(signal.SIGHUP, signal.SIG_IGN)
 
#TODO:  distribute this to the clients instead of our servers  :)
def main():
  Twisted.install_exception_handlers()
  Globals.reactor = reactor
  
  reactor.listenTCP(options.port, TCPServer())
  reactor.listenUDP(options.port, UDPServer())
  log_msg('Server is listening on port: %s!' % (options.port), 2)

  reactor.run()
  log_msg("Shutdown cleanly", 2)
  
def log_msg(msg, level):
  print msg
    
class UDPServer(protocol.DatagramProtocol, EchoMixin.EchoMixin):
  def __init__(self):
    self.address = None
    
  def datagramReceived(self, datagram, address):
    self.address = address
    self.read_request(datagram, address[0], self.transport)

class TCPServerProtocol(Int32StringReceiver, EchoMixin.EchoMixin):
  #: the max message length, currently 10MB
  MAX_LENGTH = 1024 * 1024 * 10
  
  def stringReceived(self, data):
    address = self.transport.getPeer()
    self.read_request(data, address.host, self.transport)
    
class TCPServer(protocol.ServerFactory):
  protocol = TCPServerProtocol
    
if __name__ == '__main__':
  reactor = main()
  
