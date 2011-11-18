#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Classes for running a DHT node locally"""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Scheduler
from core.network.dht.khashmir.utkhashmir import UTKhashmir
from core.network.dht.khashmir.khashmir import KhashmirBase

VERSION = 0

def _make_callback(callback):
  def response(data, callback=callback):
    if len(data) <= 0:
      return
    log_msg("Got some peers from DHT!", 4, "dht")
    peerList = {'peers': "".join(data[0])}
    callback(peerList)
  return response
  
#TODO:  put our own DHT bootstrap nodes here
#it resolves to this IP, but maybe they'll change it in the future ("72.20.34.145")
BOOTSTRAP_NODES = [("router.utorrent.com", 6881)]
  
def add_bootstrap_nodes(dhtNode):
  for host, port in BOOTSTRAP_NODES:
    dhtNode.add_contact(host, port)

class DHTNode(UTKhashmir):
  def __init__(self, port, dataFileName):
    UTKhashmir.__init__(self, "", port, dataFileName, Scheduler.schedule_once, Globals.reactor.listenUDP)
    add_bootstrap_nodes(self)
    
  def stop(self):
    self.checkpoint()
    KhashmirBase.stop(self)
    
  def get_dht_peers(self):
    globalPeers = self.table.numPeers()
    knownPeers = self.table.get_num_known_peers()
    return (knownPeers, globalPeers)
    
class LocalDHTNode(DHTNode):
  
  #TODO:  would be great if this function actually announced, but it has been impossible to debug.
  #maybe get_peers_and_announce requires a bit more persistance when debugging?
  def get_peers_and_announce(self, infohash, port, callback):
    log_msg("Sending DHT get peers and announce messages", 4, "dht")
    response = _make_callback(callback)
    #UTKhashmir.get_peers_and_announce(self, infohash, port, response)
    UTKhashmir.get_peers(self, infohash, response)
    
  def get_peers(self, infohash, callback):
    log_msg("Sending DHT get peers message", 4, "dht")
    response = _make_callback(callback)
    UTKhashmir.get_peers(self, infohash, response)
    
