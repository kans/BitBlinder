# Written by Bram Cohen
# see LICENSE.txt for license information

from cStringIO import StringIO
from binascii import b2a_hex
from socket import error as socketerror
from urllib import quote
import copy
import time

from twisted.internet import protocol, defer

from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from BTProtocol import OutgoingBTProtocol, IncomingBTProtocol
import BitTorrent.BitTorrentClient
from Applications import BitBlinder

default_task_id = []
protocol_name = 'BitTorrent protocol'

class _dummy_banlist:
    def includes(self, x):
        return False
      
      
class JashEncoder():
    #: how often to retry peers that previously failed
    PEER_RETRY_INTERVAL = 5 * 60.0
    
    def __init__(self, connecter, raw_server, my_id, max_len,
            schedulefunc, keepalive_delay, download_id, 
            measurefunc, config, can_open_more_connections, bans=_dummy_banlist() ):
        self.can_open_more_connections = can_open_more_connections
        self.raw_server = raw_server
        self.connecter = connecter
        self.my_id = my_id
        self.max_len = max_len
        self.schedulefunc = schedulefunc
        self.keepalive_delay = keepalive_delay
        self.measurefunc = measurefunc
        self.config = config
        self.banned = {}
        self.external_bans = bans
        self.download_id = download_id
        self.connections = set()
        self.to_connect = []
        self.prev_connected = []
        self.never_connected = []
        self.paused = False
        self.startConnectionsEvent = None
        self.done = False
        self.lastPeerList = None
        self.rerequester = None
        self.incompletecounter = 0
        self.lastPeerCycleTime = 0
        self.completedConnections = 0
        if self.config['max_connections'] == 0:
            self.max_connections = 2 ** 30
        else:
            self.max_connections = self.config['max_connections']
        schedulefunc(self.send_keepalives, keepalive_delay)
        
    def connect_succeeded(self, p):
      if self.done:
        p.transport.loseConnection()
        return
      self.connections.add(p)
    
    def direct_connect_succeeded(self, p):
      return
      
    def connect_failed(self, reason):
      #log_msg("BTConnection failed:  %s" % (reason))
      log_msg("BT Protocol Failed", 4, "btconn")
      self.incompletecounter -= 1
      return
    
    def start_connection(self, dns, id, encrypted = None):
      #This means that we are closed or shutting down
      if self.done:
        return
      #if self.connections == None:
      #    return
      cons = len(self.connections) + self.incompletecounter
      if ( self.paused
           or cons >= self.max_connections
           or id == self.my_id
           or not self.check_ip(ip=dns[0]) ):
          return
      #check if there are too many connections globally
      if not self.can_open_more_connections():
        return
      if self.config['crypto_only']:
          if encrypted is None or encrypted:  # fails on encrypted = 0
              encrypted = True
          else:
              return
      for v in self.connections:
          if v is None:
              continue
          if id and v.id == id:
              return True
          ip = v.get_ip()
          if self.config['security'] and ip != 'unknown' and ip == dns[0]:
              return
      
      #log_msg("BT Protocol Began", 3, "btconn")
      self.incompletecounter += 1
      log_msg("Starting BT connection:  %s %s" % (len(self.connections), self.incompletecounter), 3, "btconn")
      if self.config['use_socks']:
        BitBlinder.get().launch_external_protocol(dns[0], dns[1], OutgoingBTProtocol(self, id, encrypted, True), self.handle_stream, self.connect_failed, id)
      else:
        d = protocol.ClientCreator(Globals.reactor, OutgoingBTProtocol, self, id, encrypted, False).connectTCP(dns[0], dns[1], 30)
        d.addCallback(self.direct_connect_succeeded)
        d.addErrback(self.connect_failed)
      return
    
    #attach the stream to our circuit, or fail if that is not possible
    def handle_stream(self, stream, proto):
      #call on_new_stream for our app
      BitTorrent.BitTorrentClient.get().on_new_stream(stream, proto)

    def send_keepalives(self):
        self.schedulefunc(self.send_keepalives, self.keepalive_delay)
        if self.paused:
            return
        for c in self.connections:
            c.keepalive()

    def start_connections(self, list):
        peers_added = 0
        #add to our current list except duplicates:       
        for peer in list:
            if self.to_connect.count(peer) == 0:
                if self.prev_connected.count(peer) == 0:
                    self.never_connected.append(peer)
                    peers_added += 1
                else:
                    self.to_connect.append(peer)
                    peers_added += 1
        log_msg("Added %s to our list of peers, now %s long." % (peers_added, len(self.to_connect)), 2, "tracker")
        
        #without this, the peers would be each get connected to twice on the very first update if they fail
        if self.lastPeerCycleTime == 0:
          self.lastPeerCycleTime = time.time()
        
        #for testing:  sometimes handy to print out peers so I can make sure we can connect to them later
        #f = open("peer_list.txt", "wb")
        #for x in list:
        #  dns, id, encrypted = x
        #  #log_msg("%s %s (%s)" % (encrypted, dns, id))
        #  f.write("%s:%s\n" % (dns[0], dns[1]))
        #f.close()
        #make sure we're starting connections from that list:
        if not self.startConnectionsEvent:
          self.startConnectionsEvent = Scheduler.schedule_repeat(1.0, self._start_connection_from_queue)
          self._start_connection_from_queue()
          
    def _should_connect_to_new_peer(self,  opened):
      numOpened = opened
      log_msg("BT Connections:  connected=%s  opening=%s" % (len(self.connections), self.incompletecounter), 4, "btconn")
      cons = len(self.connections) + self.incompletecounter
      if cons >= self.max_connections or cons >= self.config['max_initiate']:
        return False
      elif self.incompletecounter >= self.config['max_half_open']:
        return False
      elif numOpened >= self.config['max_initiate_per_second']:
        return False
      return True

    def _start_connection_from_queue(self):
      try:
        if not self.paused:
          numOpened = 0
          #connect to peers that we have never connected to before  
          while len(self.never_connected) > 0:
            if self._should_connect_to_new_peer(numOpened):
                peer = self.never_connected.pop(0)
                dns, id, encrypted = peer
                self.start_connection(dns, id, encrypted)
                self.prev_connected.append(peer)
                numOpened += 1
            else:
                break
          #connect to peers that have had succesful connections previously
          while len(self.to_connect) > 0:
            if self._should_connect_to_new_peer(numOpened):
                dns, id, encrypted = self.to_connect.pop(0)
                self.start_connection(dns, id, encrypted)
                numOpened += 1
            else:
                break
        #reduce the prev_connected array to 300 in the event it gets larger
        if len(self.prev_connected) >= 300:
            del self.prev_connected[:len(self.prev_connected) - 300]
        #TODO:  kinda stupid that we just keep cycling through the last list of peers, but we need some list of them so that we can retry when circuits go down
        #Better ideas include a global cache of peers obtained from PX, DHT, etc, or even a cache incorporating time last seen for peers from trackers
        if len(self.to_connect) <= 0:
          #dont repeatedly try the same peers more than once every RETRY_INTERVAL
          curTime = time.time()
          if curTime > self.lastPeerCycleTime + self.PEER_RETRY_INTERVAL:
            self.lastPeerCycleTime = curTime
            log_msg("Cycling through the list of peers again...", 2, "btconn")
            self.to_connect = copy.copy(self.prev_connected)
      except Exception, e:
        log_ex(e, "Failed while starting BT connections")
      return True

    def _start_connection(self, dns, id, encrypted = None):
        def foo(self=self, dns=dns, id=id, encrypted=encrypted):
            self.start_connection(dns, id, encrypted)
        self.schedulefunc(foo, 0)

    def check_ip(self, connection=None, ip=None):
        """verifies that the ip has not been banned by us"""
        if not ip:
            ip = connection.get_ip()
        if self.config['security'] and self.banned.has_key(ip):
            return False
        if self.external_bans.includes(ip):
            return False
        return True

    def got_id(self, connection):
        #This means that we are closed or shutting down
        #if self.connections == None:
        #    return False
        if connection.id == self.my_id:
            #NOTE:  this happens for 2 reasons:
            #1.  We connect to ourselves because we connect to the forwarded port peer
            #2.  We connect to someone who happens to be using our peer id (extremely unlikely, or they're trying to cheat us somehow)
            #Because it might open anonymity attacks by specifically NOT connecting to our forwarded port, I'm leaving this in for now
            self.connecter.external_connection_made -= 1
            return False
        ip = connection.get_ip()
        toClose = []
        retVal = True
        for v in self.connections:
            if connection is not v:
                if connection.id == v.id:
                    if ip == v.get_ip():
                        toClose.append(v)
                    else:
                        retVal = False
                        break
                if self.config['security'] and ip != 'unknown' and ip == v.get_ip():
                  if ip != "127.0.0.1":
                    toClose.append(v)
                  #else:
                  #  log_msg("Allowing multiple connections from localhost")
        for v in toClose:
          v.close()
        return retVal

    def externally_handshaked_connection_made(self, connection, options, already_read, encrypted = None):
        shouldClose = False
        if self.done:
          shouldClose = True
          log_msg("Refusing connection because we are shutting down", 4)
        #TODO:  move this earlier in the connection process, or ideally, get Twisted to listen only from localhost when socks is enabled
        elif self.config['use_socks'] and connection.get_ip() != "127.0.0.1":
          shouldClose = True
          log_msg("Refusing connection from outside peer because they attempted to connect directly!  ip=%s" % (Basic.clean(ip)), 1)
        elif self.paused:
          shouldClose = True
          log_msg("Refusing connection becase we're paused", 4)
        elif len(self.connections) >= self.max_connections:
          shouldClose = True
          log_msg("Refusing connection becase we have too many already", 4)
        elif self.check_ip(connection=connection):
          shouldClose = True
          log_msg("Refusing connection becase check_ip failed", 4)
        #ok, is there any reason to close?
        if shouldClose:
          connection.close()
          return False
        #guess not, add this to the connections:
        self.connect_succeeded(connection)
        connection.externalHandshakeDone(self, encrypted, options)
        #TODO:  make sure the data is getting handled properly?
        ##connection.complete = True
        #if already_read:
        #    #con.data_came_in(con, already_read)
        #    connection.dataReceived(already_read)
        return True

    def close_all(self):
        temp = copy.copy(self.connections)
        self.done = True
        for c in temp:
            c.close()
        if self.startConnectionsEvent:
          if self.startConnectionsEvent.active():
            self.startConnectionsEvent.cancel()
          self.startConnectionsEvent = None
        #NOTE:  setting this to None indicates that the connection is closed
        #NOTE2:  actually, setting it to None causes the program to hang when you are downloading 2 torrents and delete one.
        #self.connections = None

    def ban(self, ip):
        self.banned[ip] = 1

    def pause(self, flag):
        self.paused = flag
