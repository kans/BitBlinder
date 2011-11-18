#!/usr/bin/env python

# Written by John Hoffman
# see LICENSE.txt for license information

from twisted.internet import defer
from download_bt1 import Torrent
from RawServer import JashRawServer
from RateLimiter import RateLimiter
from ServerPortHandler import MultiHandler
from parsedir import parsedir
from natpunch import UPnP_test
from random import seed
from socket import error as socketerror
from threading import Event
from sys import argv, exit
import sys, os
from clock import clock
from __init__ import createPeerID, mapbase64
from cStringIO import StringIO

import BitTorrent.BitTorrentClient
from core.network import dht
from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from gui import GUIController

UPnP_ERROR = "unable to forward port via UPnP"

def fmttime(n):
    try:
        n = int(n)  # n may be None or too large
        assert n < 5184000  # 60 days
    except:
        return 'downloading'
    m, s = divmod(n, 60)
    h, m = divmod(m, 60)
    return '%d:%02d:%02d' % (h, m, s)

class LaunchMany:
    def __init__(self, config, Output, isAnonymous):
        try:
            self.config = config
            self.Output = Output

            self.torrent_dir = config['torrent_dir']
            self.torrent_cache = {}
            self.file_cache = {}
            self.blocked_files = {}
            self.scan_period = config['parse_dir_interval']
            self.stats_period = config['display_interval']

            self.torrent_list = []
            self.downloads = {}
            self.counter = 0
            self.doneflag = Event()

            self.hashcheck_queue = []
            self.hashcheck_current = None
            
            self.rawserver = JashRawServer()
            upnp_type = UPnP_test(config['upnp_nat_access'])
            self.listen_port = None
            while True:
                try:
                    self.listen_port = self.rawserver.find_and_bind(
                                    config['minport'], config['maxport'], config['bind'],
                                    ipv6_socket_style = config['ipv6_binds_v4'],
                                    upnp = upnp_type, randomizer = config['random_port'])
                    break
                except socketerror, e:
                    if upnp_type and e == UPnP_ERROR:
                        log_msg('WARNING: COULD NOT FORWARD VIA UPnP', 0)
                        upnp_type = 0
                        continue
                    self.failed("Couldn't listen - " + str(e))
                    return
                    
            self.dht = None
            if isAnonymous:
              self.dht = dht.Proxy.DHTProxy(BitTorrent.BitTorrentClient.get())
            else:
              if self.listen_port:
                self.dht = dht.Node.LocalDHTNode(self.listen_port, config['dht_file_name'])
            self.ratelimiter = RateLimiter(self.rawserver.add_task,
                                           config['upload_unit_size'])
            self.ratelimiter.set_upload_rate(config['max_upload_rate'])

            self.handler = MultiHandler(self.rawserver, self.doneflag, config)
            seed(createPeerID())
            #self.rawserver.add_task(self.scan, 0)
            if self.scan_period:
              self.scan()
              self.scanEvent = Scheduler.schedule_repeat(self.scan_period, self.scan)
            else:
              self.scanEvent = None
#            self.rawserver.add_task(self.stats, 0)

        except Exception, error:
            log_ex(error, "LaunchMany failed")
            
    #allow clean shutdown:
    def quit(self, force=False):
      """@param force: Force a quick and dirty shutdown?  
      @type force: bool
      Note: force is mainly just passed through to the rerequester atm, but this should be used elsewhere too"""
      self.hashcheck_queue = []
      dList = []
      for hash in self.torrent_list:
          d = self.downloads[hash].shutdown(force=force)
          if d:
            dList.append(d)
      dList.append(self.rawserver.shutdown())
      if self.dht:
        self.dht.stop()
      if self.scanEvent and self.scanEvent.active():
        self.scanEvent.cancel()
      return defer.DeferredList(dList)

    def scan(self):
        #self.rawserver.add_task(self.scan, self.scan_period)
                                
        r = parsedir(self.torrent_dir, self.torrent_cache,
                     self.file_cache, self.blocked_files,
                     return_metainfo = True, errfunc = self.Output.message)

        ( self.torrent_cache, self.file_cache, self.blocked_files,
            added, removed ) = r

        for hash, data in removed.items():
            log_msg('dropped "'+Basic.clean(data['path'])+'"', 2)
            self.remove(hash)
        for hash, data in added.items():
            log_msg('added "'+Basic.clean(data['path'])+'"', 2)
            self.add(hash, data)

    def stats(self, spew=False):            
#        self.rawserver.add_task(self.stats, self.stats_period)
        data = []
        for hash in self.torrent_list:
            cache = self.torrent_cache[hash]
            if self.config['display_path']:
                name = cache['path']
            else:
                name = cache['name']
            size = cache['length']
            d = self.downloads[hash]
            progress = '0.0%'
            peers = 0
            seeds = 0
            seedsmsg = "S"
            dist = 0.0
            uprate = 0.0
            dnrate = 0.0
            upamt = 0
            dnamt = 0
            knownSeeds = 0
            knownPeers = 0
            t = 0
            if d.is_dead():
                status = 'stopped'
            elif d.waiting:
                status = 'waiting for hash check'
            elif d.checking:
                status = d.statusMsg
                progress = '%.1f%%' % (d.statusDone*100)
            else:
                stats = d.startStats(spew)
                s = stats['stats']
                
                #TODO:  this is not necessarily the best place for this, but...
                #check if we are seeding, or completely done with all of the downloading
                if d.seed or (stats.has_key('done') and stats.has_key('wanted') and stats['done'] == stats['wanted']):
                  if not d.wasPausedOnce:
                    d.wasPausedOnce = True
                    d.Pause()
                
                if d.seed:
                    status = 'seeding'
                    progress = '100.0%'
                    seeds = s.numOldSeeds
                    seedsmsg = "s"
                    dist = s.numCopies
                else:
                    if s.numSeeds + s.numPeers:
                        t = stats['time']
                        if t == 0:  # unlikely
                            t = 0.01
                        status = fmttime(t)
                    else:
                        t = -1
                        status = 'connecting to tracker'
                    progress = '%.1f%%' % (int(stats['frac']*1000)/10.0)
                    seeds = s.numSeeds
                    dist = s.numCopies
                    dnrate = stats['down']
                peers = s.numPeers
                uprate = stats['up']
                upamt = s.upTotal
                dnamt = s.downTotal
                knownSeeds = s.knownSeeds
                knownPeers = s.knownPeers
                if s.failureReason:
                  status += " (%s)" % (s.failureReason)
                   
            if d.is_dead() or d.statusErrorTime+300 > clock():
                msg = d.statusErr[-1]
            else:
                msg = ''

            data.append(( name, status, progress, peers, seeds, seedsmsg, dist,
                          uprate, dnrate, upamt, dnamt, size, t, msg, hash, knownSeeds, knownPeers ))
        return data

    def remove(self, hash):
        self.torrent_list.remove(hash)
        self.downloads[hash].shutdown()
        del self.downloads[hash]
        
    def add(self, hash, data):
        #check if we already know about this torrent:
        if hash in self.downloads:
          #if so, just add the trackers and return:
          self.downloads[hash].add_trackers(data['metainfo'])
          #and tell the user that that is what happened, so they're not suprised:
          GUIController.get().show_msgbox("BitBlinder added all new trackers from that .torrent file.", title="Already Downloading Torrent!")
          return None
        self.counter += 1
        peer_id = createPeerID()
        d = Torrent(self, hash, data['metainfo'], self.config, peer_id, self.dht, self.can_open_more_connections)
        self.torrent_list.append(hash)
        self.downloads[hash] = d
        
        #added because this normally happens when scanning:
        self.torrent_cache[hash] = data
        return d
        
    def can_open_more_connections(self):
      numOpen = 0
      for hash, download in self.downloads.iteritems():
        if download and download.encoder:
          numOpen += download.encoder.incompletecounter
          numOpen += len(download.encoder.connections)
      if numOpen >= self.config['global_connection_limit']:
        return False
      return True
      
    def get_trackers(self, infohash):
      if infohash not in self.downloads:
        log_msg("Cannot get trackers for %s--not downloading that torrent" % (str(infohash).encode("hex")), 0)
        return None
      return self.downloads[infohash].rerequest.get_trackers()
      
    #TODO:  save the trackers to the torrent file after editing them
    #NOTE:  it may not be writable, so we'll have to move to having our own copies of .torrent files
    def set_trackers(self, infohash, trackerList):
      if infohash not in self.downloads:
        log_msg("Cannot set trackers for %s--not downloading that torrent" % (str(infohash).encode("hex")), 0)
        return
      self.downloads[infohash].rerequest.set_trackers(trackerList)

    def saveAs(self, hash, name, saveas, isdir):
        x = self.torrent_cache[hash]
        style = self.config['saveas_style']
        if style == 1 or style == 3:
            if saveas:
                saveas = os.path.join(saveas,x['file'][:-1-len(x['type'])])
            else:
                saveas = x['path'][:-1-len(x['type'])]
            if style == 3:
                if not os.path.isdir(saveas):
                    try:
                        os.mkdir(saveas)
                    except:
                        raise OSError("couldn't create directory for "+x['path']
                                      +" ("+saveas+")")
                if not isdir:
                    saveas = os.path.join(saveas, name)
        else:
            #Josh:  changed:
            #if saveas:
            #    saveas = os.path.join(saveas, name)
            #else:
            #    saveas = os.path.join(os.path.split(x['path'])[0], name)
            #to:
            if not saveas:
                raise Exception("You must specify a filename to use BitTorrent nowadays!")
                
        if isdir and not os.path.isdir(saveas):
            try:
                os.mkdir(saveas)
            except:
                raise OSError("couldn't create directory for "+x['path']
                                      +" ("+saveas+")")
        return saveas


    def hashchecksched(self, hash = None):
        if hash:
            self.hashcheck_queue.append(hash)
        if not self.hashcheck_current:
            self._hashcheck_start()

    def _hashcheck_start(self):
        self.hashcheck_current = self.hashcheck_queue.pop(0)
        self.downloads[self.hashcheck_current].hashcheck_start(self.hashcheck_callback)

    def hashcheck_callback(self):
        self.downloads[self.hashcheck_current].hashcheck_callback()
        if self.hashcheck_queue:
            self._hashcheck_start()
        else:
            self.hashcheck_current = None

    def died(self, hash):
        if hash in self.torrent_cache:
            log_msg('DIED: "'+Basic.clean(self.torrent_cache[hash]['path'])+'"', 1)
        else:
            log_msg('DIED: "'+Basic.clean(hash)+'"', 1)
        
    def was_stopped(self, hash):
        if hash in self.hashcheck_queue:
            self.hashcheck_queue.remove(hash)
        if self.hashcheck_current == hash:
            self.hashcheck_current = None
            if self.hashcheck_queue:
                self._hashcheck_start()

    def failed(self, s):
        log_ex(s, 'generic BitTornado failure')

    def exchandler(self, s):
        log_ex(s, 'generic BitTornado exception')
