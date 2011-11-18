#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Same interface as a DHTNode, but proxies all requests through a circuit"""

import struct
import socket

from twisted.internet.abstract import isIPAddress

from core.tor import TorMessages
from common import Globals
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from core.network.dht import Node

class RemoteDHTRequest(TorMessages.TorMessageHandler):
  def __init__(self, baseCircuit, circ):
    TorMessages.TorMessageHandler.__init__(self, baseCircuit)
    self.circ = circ
    self.callback = None
  
  def get_implemented_messages(self):
    return ("dht_response",)
    
  def send_request(self, msg, callback):
    log_msg("Sending remote DHT request", 4, "dht")
    self.callback = callback
    numHops = len(self.circ.finalPath)
    self.send_direct_tor_message(msg, "dht_request", True, numHops, True)
    
  def handle_dht_response(self, data):
    log_msg("Got remote DHT response", 4, "dht")
    version, data = Basic.read_byte(data)
    assert version == Node.VERSION
    peerList = {'peers': data}
    self.callback(peerList)
    
class DHTProxy():
  def __init__(self, app):
    self.app = app
    self.circ = None
    self.finished = False
    self.knownNodes = set()
    Node.add_bootstrap_nodes(self)

  def _send_remote_peer_request(self, infohash, callback):
    #make sure we have a circuit to send it out on:
    if self.circ and self.circ.is_done():
      self.circ = None
    if not self.circ:
      self.circ = self.app.find_or_build_best_circuit(force=True, protocol="DHT")
      if self.circ == None:
        log_msg("Could not build circuit for DHT remote peer request", 0, "dht")
        return
    #generate the message:  (version, infohash, peerList)
    msg = ""
    #header:
    msg += Basic.write_byte(Node.VERSION)
    #infohash:
    msg += infohash
    #peers:
    for host, port in self.knownNodes:
      #is this an IP address?
      if isIPAddress(host):
        msg += Basic.write_byte(0)
        msg += struct.pack("!4sH", socket.inet_aton(host), port)
      #otherwise, it's a URL that has to be resolved remotely
      else:
        msg += Basic.write_byte(1)
        msg += Basic.write_lenstr(host)
        msg += Basic.write_short(port)
    self.circ.send_dht_request(msg, self.make_callback_wrapper(callback))
    
  def get_peers_and_announce(self, infohash, port, callback):
    return self._send_remote_peer_request(infohash, self.make_callback_wrapper(callback))
    
  def get_peers(self, infohash, callback):
    return self._send_remote_peer_request(infohash, self.make_callback_wrapper(callback))
    
  #REFACTOR:  bad name, weird return value, no docstring
  def get_dht_peers(self):
    return ("unknown", "proxied")
    
  def make_callback_wrapper(self, callback):
    def callback_wrapper(*args):
      if not self.finished:
        callback(*args)
    return callback_wrapper
    
  def stop(self):
    self.finished = True
    
  def add_contact(self, host, port):
    self.knownNodes.add((host, port))
    