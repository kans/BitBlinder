# Written by Bram Cohen
# see LICENSE.txt for license information

from bisect import insort
from random import shuffle, randrange
from natpunch import UPnP_open_port, UPnP_close_port
import socket
from cStringIO import StringIO
from traceback import print_exc
from select import error
from threading import Thread, Event
from time import sleep
from clock import clock
import sys

from twisted.internet import protocol, defer
from twisted.internet.error import CannotListenError
from BT1.BTProtocol import OutgoingBTProtocol, IncomingBTProtocol
from core.network import UPNPPort
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler

def autodetect_ipv6():
    try:
        assert sys.version_info >= (2,3)
        assert socket.has_ipv6
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except:
        return 0
    return 1

def autodetect_socket_style():
	if sys.platform.find('linux') < 0:
		return 1
	else:
		try:
			f = open('/proc/sys/net/ipv6/bindv6only','r')
			dual_socket_style = int(f.read())
			f.close()
			return int(not dual_socket_style)
		except:
			return 0


class IncomingBTFactory(protocol.ClientFactory):
  protocol = IncomingBTProtocol
  def buildProtocol(self, addr):
    p = self.protocol(self.multihandler, False)
    return p
    
  def clientConnectionFailed(self, connector, reason):
    log_msg("Connection failed:  %s" % (str(reason)), 4)
  
  def clientConnectionLost(self, connector, reason):
    log_msg("Connection lost", 4)
        
class JashRawServer:
    def __init__(self):
        self.events = {}
        self.curEventId = 1
        self.idMapping = {}
        self.listener = None
        self.port_forwarded = None

    def get_exception_flag(self):
        return None

    def add_task(self, func, delay = 0, id = None):
        assert float(delay) >= 0
        eventId = self.curEventId
        self.curEventId += 1
        if not self.idMapping.has_key(id):
          self.idMapping[id] = set()
        self.idMapping[id].add(eventId)
        def wrapperFunc(func=func, id=id, eventId=eventId):
          if self.idMapping.has_key(id) and eventId in self.idMapping[id]:
            self.idMapping[id].remove(eventId)
            if len(self.idMapping[id]) <= 0:
              del self.idMapping[id]
          if self.events.has_key(id) and self.events[id].has_key(eventId):
            del self.events[id][eventId]
            if len(self.events[id]) <= 0:
              del self.events[id]
          func()
        if not self.events.has_key(id):
          self.events[id] = {}
        self.events[id][eventId] = Scheduler.schedule_once(delay, wrapperFunc)
        
    def bind(self, port, bind = '', reuse = False, ipv6_socket_style = 1, upnp = 0):
      port = int(port)
      #TEMP:  disabling incoming BT connections:
      if True:
        return
      
      self.listener = Globals.reactor.listenTCP(port, self.factory)
      self.port_forwarded = UPNPPort.UPNPPort("BitBlinder", port)
      self.port_forwarded.start()

    def find_and_bind(self, minport, maxport, bind = '', reuse = False,
                      ipv6_socket_style = 1, upnp = 0, randomizer = False):
        self.factory = IncomingBTFactory()
        e = 'maxport less than minport - no ports to check'
        if maxport-minport < 50 or not randomizer:
            portrange = range(minport, maxport+1)
            if randomizer:
                shuffle(portrange)
                portrange = portrange[:20]  # check a maximum of 20 ports
        else:
            portrange = []
            while len(portrange) < 20:
                listen_port = randrange(minport, maxport+1)
                if not listen_port in portrange:
                    portrange.append(listen_port)
        for listen_port in portrange:
            try:
                self.bind(listen_port, bind,
                               ipv6_socket_style = ipv6_socket_style, upnp = upnp)
                return listen_port
            except CannotListenError, e:
                log_msg("Could not bind %s to listen for BT server" % (listen_port), 3)
                pass
        raise socket.error(str(e))
      
    def get_stats(self):
        return {}

    def listen_forever(self, handler):
        return

    def is_finished(self):
        return False

    def kill_tasks(self, id):
        if self.events.has_key(id):
          for event in self.events[id].values():
            if event.active():
              event.cancel()
            else:
              log_msg("There should never be any inactive events in self.events!", 2)
          if len(self.idMapping[id]) > 0:
            del self.idMapping[id]
            del self.events[id]

    def shutdown(self):
      """Returns a deferred for when the server is done shutting down"""
      d = None
      if self.listener:
        self.listener.stopListening()
        d = self.port_forwarded.stop()
      if not d:
        d = defer.succeed(True)
      #remove ALL events:
      for eventList in self.events.values():
        for event in eventList.values():
          if event.active():
            event.cancel()
          else:
            log_msg("There should never be any inactive events in self.events!",2)
      return d
