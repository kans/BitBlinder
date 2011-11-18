# Written by Bram Cohen
# see LICENSE.txt for license information

from twisted.internet import defer
from zurllib import urlopen
from urlparse import urlparse
from BT1.btformats import check_message
from BT1.Choker import Choker
from BT1.Storage import Storage
from BT1.StorageWrapper import StorageWrapper
from BT1.FileSelector import FileSelector
from BT1.Uploader import UploadPeer
from BT1.Downloader import Downloader
from BT1.HTTPDownloader import HTTPDownloader
from BT1.JashConnecter import JashConnecter
from RateLimiter import RateLimiter
from BT1.JashEncrypter import JashEncoder
from RawServer import autodetect_ipv6, autodetect_socket_style
from BT1.Rerequester import Rerequester
from BT1.DownloaderFeedback import DownloaderFeedback
from RateMeasure import RateMeasure
from CurrentRateMeasure import Measure
from BT1.PiecePicker import PiecePicker
from BT1.Statistics import Statistics
from bencode import bencode, bdecode
from natpunch import UPnP_test
from sha import sha
from os import path, makedirs, listdir
from parseargs import parseargs, formatDefinitions, defaultargs
from socket import error as socketerror
from random import seed
from threading import Event
from clock import clock
from BTcrypto import CRYPTO_OK

import BitTorrent.BitTorrentClient
from gui import GUIController
from common import Globals
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

defaults = [
    ('max_uploads', 7,
        "the maximum number of uploads to allow at once."),
    ('keepalive_interval', 120.0,
        'number of seconds to pause between sending keepalives'),
    ('download_slice_size', 2 ** 14,
        "How many bytes to query for per request."),
    ('upload_unit_size', 1460,
        "when limiting upload rate, how many bytes to send at a time"),
    ('request_backlog', 10,
        "maximum number of requests to keep in a single pipe at once."),
    ('max_message_length', 2 ** 23,
        "maximum length prefix encoding you'll accept over the wire - larger values get the connection dropped."),
    ('ip', '',
        "ip to report you have to the tracker."),
    ('minport', 10000, 'minimum port to listen on, counts up if unavailable'),
    ('maxport', 60000, 'maximum port to listen on'),
    ('random_port', 1, 'whether to choose randomly inside the port range ' +
        'instead of counting up linearly'),
    ('responsefile', '',
        'file the server response was stored in, alternative to url'),
    ('url', '',
        'url to get file from, alternative to responsefile'),
    ('crypto_allowed', int(CRYPTO_OK),
        'whether to allow the client to accept encrypted connections'),
    ('crypto_only', 0,
        'whether to only create or allow encrypted connections'),
    ('crypto_stealth', 0,
        'whether to prevent all non-encrypted connection attempts; ' +
        'will result in an effectively firewalled state on older trackers'),
    ('selector_enabled', 1,
        'whether to enable the file selector and fast resume function'),
    ('expire_cache_data', 10,
        'the number of days after which you wish to expire old cache data ' +
        '(0 = disabled)'),
    ('priority', '',
        'a list of file priorities separated by commas, must be one per file, ' +
        '0 = highest, 1 = normal, 2 = lowest, -1 = download disabled'),
    ('saveas', '',
        'local file name to save the file as, null indicates query user'),
    ('timeout', 300.0,
        'time to wait between closing sockets which nothing has been received on'),
    ('timeout_check_interval', 60.0,
        'time to wait between checking if any connections have timed out'),
    ('max_slice_length', 2 ** 17,
        "maximum length slice to send to peers, larger requests are ignored"),
    ('max_rate_period', 10.0,
        "maximum amount of time to guess the current rate estimate represents"),
    ('bind', '', 
        'comma-separated list of ips/hostnames to bind to locally'),
#    ('ipv6_enabled', autodetect_ipv6(),
    ('ipv6_enabled', 0,
         'allow the client to connect to peers via IPv6'),
    ('ipv6_binds_v4', autodetect_socket_style(),
        "set if an IPv6 server socket won't also field IPv4 connections"),
    ('upnp_nat_access', 0,
        'attempt to autoconfigure a UPnP router to forward a server port ' +
        '(0 = disabled, 1 = mode 1 [fast], 2 = mode 2 [slow])'),
    ('upload_rate_fudge', 5.0, 
        'time equivalent of writing to kernel-level TCP buffer, for rate adjustment'),
    ('tcp_ack_fudge', 0.03,
        'how much TCP ACK download overhead to add to upload rate calculations ' +
        '(0 = disabled)'),
    ('display_interval', .5,
        'time between updates of displayed information'),
    ('rerequest_interval', 5 * 60,
        'time to wait between requesting more peers'),
    ('http_timeout', 60, 
        'number of seconds to wait before assuming that an http connection has timed out'),
    ('min_peers', 20, 
        'minimum number of peers to not do rerequesting'),
    ('max_initiate', 40,
        'number of peers at which to stop initiating new connections'),
    ('max_connections', 0,
        "the absolute maximum number of peers to connect with (0 = no limit)"),
    ('check_hashes', 1,
        'whether to check hashes on disk'),
    ('max_upload_rate', 0,
        'maximum kB/s to upload at (0 = no limit, -1 = automatic)'),
    ('max_download_rate', 0,
        'maximum kB/s to download at (0 = no limit)'),
    ('alloc_type', 'normal',
        'allocation type (may be normal, background, pre-allocate or sparse)'),
    ('alloc_rate', 2.0,
        'rate (in MiB/s) to allocate space at using background allocation'),
    ('buffer_reads', 1,
        'whether to buffer disk reads'),
    ('write_buffer_size', 4,
        'the maximum amount of space to use for buffering disk writes ' +
        '(in megabytes, 0 = disabled)'),
    ('breakup_seed_bitfield', 1,
        'sends an incomplete bitfield and then fills with have messages, '
        'in order to get around stupid ISP manipulation'),
    ('snub_time', 30.0,
        "seconds to wait for data to come in over a connection before assuming it's semi-permanently choked"),
    ('spew', 0,
        "whether to display diagnostic info to stdout"),
    ('rarest_first_cutoff', 2,
        "number of downloads at which to switch from random to rarest first"),
    ('rarest_first_priority_cutoff', 5,
        'the number of peers which need to have a piece before other partials take priority over rarest first'),
    ('min_uploads', 4,
        "the number of uploads to fill out to with extra optimistic unchokes"),
    ('max_files_open', 50,
        'the maximum number of files to keep open at a time, 0 means no limit'),
    ('round_robin_period', 30,
        "the number of seconds between the client's switching upload targets"),
    ('super_seeder', 0,
        "whether to use special upload-efficiency-maximizing routines (only for dedicated seeds)"),
    ('security', 1,
        "whether to enable extra security features intended to prevent abuse"),
    ('auto_kick', 1,
        "whether to allow the client to automatically kick/ban peers that send bad data"),
    ('double_check', 1,
        "whether to double-check data being written to the disk for errors (may increase CPU load)"),
    ('triple_check', 0,
        "whether to thoroughly check data being written to the disk (may slow disk access)"),
    ('lock_files', 1,
        "whether to lock files the client is working with"),
    ('lock_while_reading', 0,
        "whether to lock access to files being read"),
    ('auto_flush', 0,
        "minutes between automatic flushes to disk (0 = disabled)"),
    ('dedicated_seed_id', '',
        "code to send to tracker identifying as a dedicated seed"),
    ]

argslistheader = 'Arguments are:\n\n'

class Torrent:
    def __init__(self, controller, hash, response, config, myid, dht, can_open_more_connections):
        self.can_open_more_connections = can_open_more_connections
        self.controller = controller
        self.infohash = hash
        self.response = response
        self.config = config
        
        self.doneflag = Event()
        self.waiting = True
        self.checking = False
        self.working = False
        self.seed = False
        self.closed = False

        self.statusMsg = ''
        self.statusErr = ['']
        self.statusErrorTime = 0
        self.statusDone = 0.0

        self.rawserver = controller.handler.newRawServer(hash, self.doneflag)

        self.excfunc = controller.exchandler
        self.myid = myid
        self.port = controller.listen_port
        
        self.info = self.response['info']
        self.pieces = [self.info['pieces'][x:x+20]
                       for x in xrange(0, len(self.info['pieces']), 20)]
        self.isPrivate = False
        if 'private' in self.info:
          self.isPrivate = bool(self.info['private'])
        self.dht = dht
        #no DHT if this is a private tracker
        if self.isPrivate:
          self.dht = None
        self.len_pieces = len(self.pieces)
        self.argslistheader = argslistheader
        self.unpauseflag = Event()
        self.unpauseflag.set()
        self.wasPausedOnce = False
        self.downloader = None
        self.storagewrapper = None
        self.fileselector = None
        self.super_seeding_active = False
        self.filedatflag = Event()
        self.spewflag = Event()
        self.superseedflag = Event()
        self.whenpaused = None
        self.finflag = Event()
        self.rerequest = None
        self.encoder = None
        self.tcp_ack_fudge = config['tcp_ack_fudge']

        self.selector_enabled = config['selector_enabled']
        self.appdataobj = BitTorrent.BitTorrentClient.get()

        #self.excflag = self.rawserver.get_exception_flag()
        self.failed = False
        self.checkingHash = False
        self.started = False
        self.filename = None
        
        #: for waiting for tracker stop events on shutdown
        self.shutdownDeferred = None

        self.picker = PiecePicker(self.len_pieces, config['rarest_first_cutoff'],
                             config['rarest_first_priority_cutoff'])
        self.choker = Choker(config, self.rawserver.add_task,
                             self.picker, self.finflag.isSet, self.get_swarm_size)

    def start(self):
        if not self.saveAs():
            self.shutdown()
            return
        self._hashcheckfunc = self.initFiles()
        if not self._hashcheckfunc:
            self.shutdown()
            return
        self.controller.hashchecksched(self.infohash)

    def hashcheck_start(self, donefunc):
        if self.is_dead():
            self.shutdown()
            return
        self.waiting = False
        self.checking = True
        self._hashcheckfunc(donefunc)

    def hashcheck_callback(self):
        self.checking = False
        if self.is_dead():
            self.shutdown()
            return
        if not self.startEngine(ratelimiter = self.controller.ratelimiter):
            self.shutdown()
            return
        self.startRerequester()
        self.rawserver.start_listening(self.getPortHandler())
        self.working = True

    def is_dead(self):
        return self.doneflag.isSet()

    #TODO:  simplify
    def shutdown(self, torrentdata=None, force=False):
      """@param force: force the shutdown without waiting for tracker anounce?
      @type force: bool"""
      if not torrentdata:
        torrentdata = {}
      d = None
      if self.closed:
        return d
      self.doneflag.set()
      self.rawserver.shutdown()
      #pickle the pause state of the torrent with the rest of infos
      torrentdata['pause flag'] = self.unpauseflag.isSet()
      if self.checking or self.working:
        if self.checkingHash or self.started:
          self.storagewrapper.sync()
          self.storage.close()
          d = self.stop_rerequest(force)
        if self.fileselector and self.started:
          if not self.failed:
            self.fileselector.finish()
            #TODO:  I'm pretty sure priority doesnt get saved here anymore, and that nothing passes a torrentData
            torrentdata['resume data'] = self.fileselector.pickle()
        shouldWriteData = self.started or not self.doneflag.set()
        if shouldWriteData:
          try:
            self.appdataobj.writeTorrentData(self.infohash, torrentdata)
          except Exception, e:
            log_ex(e, "writeTorrentData failed during shutdown")
            self.appdataobj.deleteTorrentData(self.infohash) # clear it
      self.waiting = False
      self.checking = False
      self.working = False
      self.closed = True
      self.controller.was_stopped(self.infohash)
      self.controller.died(self.infohash)
      return d            

    def statusfunc(self, activity = None, fractionDone = None):
        # really only used by StorageWrapper now
        if activity:
            self.statusMsg = activity
        if fractionDone is not None:
            self.statusDone = float(fractionDone)

    def finfunc(self):
        self.seed = True

    def errorfunc(self, msg):
        if self.doneflag.isSet():
            self.shutdown()
        self.statusErr.append(msg)
        self.statusErrorTime = clock()
        log_ex(msg, 1)
                             
    def get_swarm_size(self):
        if self.rerequest:
            return self.rerequest.knownSeeds + self.rerequest.knownPeers
        return 0


    def checkSaveLocation(self, loc):
        if self.info.has_key('length'):
            return path.exists(loc)
        for x in self.info['files']:
            if path.exists(path.join(loc, x['path'][0])):
                return True
        return False
                

    def saveAs(self):
        try:
            def make(f, forcedir = False):
                if not forcedir:
                    f = path.split(f)[0]
                if f != '' and not path.exists(f):
                    makedirs(f)

            if self.info.has_key('length'):
                file_length = self.info['length']
                file = self.controller.saveAs(self.infohash, self.info['name'],
                                self.config['saveas'], False)
                if file is None:
                    return None
                make(file)
                files = [(file, file_length)]
            else:
                file_length = 0L
                for x in self.info['files']:
                    file_length += x['length']
                file = self.controller.saveAs(self.infohash, self.info['name'],
                                self.config['saveas'], True)
                if file is None:
                    return None

                # if this path exists, and no files from the info dict exist, we assume it's a new download and 
                # the user wants to create a new directory with the default name
                existing = 0
                if path.exists(file):
                    if not path.isdir(file):
                        self.errorfunc(file + 'is not a dir')
                        return None
                    if len(listdir(file)) > 0:  # if it's not empty
                        for x in self.info['files']:
                            if path.exists(path.join(file, x['path'][0])):
                                existing = 1
                        if not existing:
                            file = path.join(file, self.info['name'])
                            if path.exists(file) and not path.isdir(file):
                                if file[-8:] == '.torrent':
                                    file = file[:-8]
                                if path.exists(file) and not path.isdir(file):
                                    self.errorfunc("Can't create dir - " + self.info['name'])
                                    return None
                make(file, True)

                files = []
                for x in self.info['files']:
                    n = file
                    for i in x['path']:
                        n = path.join(n, i)
                    files.append((n, x['length']))
                    make(n)
        except OSError, e:
            self.errorfunc("Couldn't allocate dir - " + str(e))
            return None

        self.filename = file
        self.files = files
        self.datalength = file_length

        return file
    

    def getFilename(self):
        return self.filename


    def _finished(self):
        self.finflag.set()
        try:
            self.storage.set_readonly()
        except (IOError, OSError), e:
            self.errorfunc('trouble setting readonly at end - ' + str(e))
        if self.superseedflag.isSet():
            self._set_super_seed()
        self.choker.set_round_robin_period(
            max( self.config['round_robin_period'],
                 self.config['round_robin_period'] *
                                     self.info['piece length'] / 200000 ) )
        self.rerequest_complete()
        self.finfunc()
#        #TODO:  implement better seeding GUI, so we can ask people if they want to keep seeding instead of just pausing:
#        self.Pause()

    def _data_flunked(self, amount, index):
        self.ratemeasure_datarejected(amount)
        if not self.doneflag.isSet():
            log_msg('piece %d failed hash check, re-downloading it' % (index), 0)

    def _failed(self, reason):
        self.failed = True
        self.doneflag.set()
        if reason is not None:
            self.errorfunc(reason)
        
    def initFiles(self, old_style = False, statusfunc = None):
        if self.doneflag.isSet():
            return None
        if not statusfunc:
            statusfunc = self.statusfunc

        disabled_files = None
        if self.selector_enabled:
            self.priority = self.config['priority']
            if self.priority:
                try:
                    self.priority = self.priority.split(',')
                    assert len(self.priority) == len(self.files)
                    self.priority = [int(p) for p in self.priority]
                    for p in self.priority:
                        assert p >= -1
                        assert p <= 2
                except Exception, e:
                    self.errorfunc('bad priority list given, ignored')
                    self.priority = None

            data = self.appdataobj.getTorrentData(self.infohash)
            disabled_files = None
            if data:
              #set the pause flag if possible
              if 'pause flag' in data:
                shouldPause = not bool(data['pause flag'])
                if shouldPause:
                  self.unpauseflag.clear()
              #get the priorities if possible
              if 'resume data' in data and 'priority' in data['resume data']:
                d = data['resume data']['priority']
                if len(d) == len(self.files):
                  disabled_files = [x == -1 for x in d]
            if not disabled_files and self.priority:
                  disabled_files = [x == -1 for x in self.priority]

        try:
            try:
                self.storage = Storage(self.files, self.info['piece length'],
                                       self.doneflag, self.config, disabled_files)
            except IOError, e:
                #self.errorfunc('trouble accessing files - ' + str(e))
                GUIController.get().show_msgbox(str(e))
                return None
            if self.doneflag.isSet():
                return None

            self.storagewrapper = StorageWrapper(self.storage, self.config['download_slice_size'],
                self.pieces, self.info['piece length'], self._finished, self._failed,
                statusfunc, self.doneflag, self.config['check_hashes'],
                self._data_flunked, self.rawserver.add_task,
                self.config, self.unpauseflag)
            
        except ValueError, e:
            self._failed('bad data - ' + str(e))
        except IOError, e:
            self._failed('IOError - ' + str(e))
        if self.doneflag.isSet():
            return None

        if self.selector_enabled:
            self.fileselector = FileSelector(self.files, self.info['piece length'],
                                             self.appdataobj.getPieceDir(self.infohash),
                                             self.storage, self.storagewrapper,
                                             self.rawserver.add_task,
                                             self._failed)
            if data:
                data = data.get('resume data')
                if data:
                    self.fileselector.unpickle(data)
                
        self.checkingHash = True
        if old_style:
            return self.storagewrapper.old_style_init()
        return self.storagewrapper.initialize


    def getCachedTorrentData(self):
        return self.appdataobj.getTorrentData(self.infohash)


    def _make_upload(self, connection, ratelimiter, totalup):
        return UploadPeer(connection, ratelimiter, totalup,
                      self.choker, self.storagewrapper, self.picker,
                      self.config)

    def _kick_peer(self, connection):
        def k(connection = connection):
            connection.close()
        self.rawserver.add_task(k,0)

    def _ban_peer(self, ip):
        self.encoder_ban(ip)

    def _received_raw_data(self, x):
        if self.tcp_ack_fudge:
            x = int(x*self.tcp_ack_fudge)
            self.ratelimiter.adjust_sent(x)

    def _received_data(self, x):
        self.downmeasure.update_rate(x)
        self.ratemeasure.data_came_in(x)

    def _received_http_data(self, x):
        self.downmeasure.update_rate(x)
        self.ratemeasure.data_came_in(x)
        self.downloader.external_data_received(x)

    def _cancelfunc(self, pieces):
        self.downloader.cancel_piece_download(pieces)
        self.httpdownloader.cancel_piece_download(pieces)
    def _reqmorefunc(self, pieces):
        self.downloader.requeue_piece_download(pieces)

    def startEngine(self, ratelimiter = None, statusfunc = None):
        if self.doneflag.isSet():
            return False
        if not statusfunc:
            statusfunc = self.statusfunc

        self.checkingHash = False

        if not CRYPTO_OK:
            if self.config['crypto_allowed']:
                self.errorfunc('warning - crypto library not installed')
            self.config['crypto_allowed'] = 0
            self.config['crypto_only'] = 0
            self.config['crypto_stealth'] = 0

        for i in xrange(self.len_pieces):
            if self.storagewrapper.do_I_have(i):
                self.picker.complete(i)
        self.upmeasure = Measure(self.config['max_rate_period'],
                            self.config['upload_rate_fudge'])
        self.downmeasure = Measure(self.config['max_rate_period'])

        if ratelimiter:
            self.ratelimiter = ratelimiter
        else:
            self.ratelimiter = RateLimiter(self.rawserver.add_task,
                                           self.config['upload_unit_size'],
                                           self.setConns)
            self.ratelimiter.set_upload_rate(self.config['max_upload_rate'])
        
        self.ratemeasure = RateMeasure()
        self.ratemeasure_datarejected = self.ratemeasure.data_rejected

        self.downloader = Downloader(self.storagewrapper, self.picker,
            self.config['request_backlog'], self.config['max_rate_period'],
            self.len_pieces, self.config['download_slice_size'],
            self._received_data, self.config['snub_time'], self.config['auto_kick'],
            self._kick_peer, self._ban_peer)
        self.downloader.set_download_rate(self.config['max_download_rate'])

        self.connecter = JashConnecter(self._make_upload, self.downloader, self.choker,
                            self.len_pieces, self.upmeasure, self.config,
                            self.ratelimiter, self.rawserver.add_task)
        self.encoder = JashEncoder(self.connecter, self.rawserver,
            self.myid, self.config['max_message_length'], self.rawserver.add_task,
            self.config['keepalive_interval'], self.infohash,
            self._received_raw_data, self.config, self.can_open_more_connections)
        self.encoder_ban = self.encoder.ban

        self.httpdownloader = HTTPDownloader(self.storagewrapper, self.picker,
            self.rawserver, self.finflag, self.errorfunc, self.downloader,
            self.config['max_rate_period'], self.infohash, self._received_http_data,
            self.connecter.got_piece)
        if self.response.has_key('httpseeds') and not self.finflag.isSet():
            #TODO:  fix HTTPDownloader to be anonymous and non-threaded?
            log_msg("HTTP seeds are currently not supported!", 0)
            #for u in self.response['httpseeds']:
            #    self.httpdownloader.make_download(u)

        if self.selector_enabled:
            self.fileselector.tie_in(self.picker, self._cancelfunc,
                    self._reqmorefunc, self.rerequest_ondownloadmore)
            if self.priority:
                self.fileselector.set_priorities_now(self.priority)
            self.appdataobj.deleteTorrentData(self.infohash)
                                # erase old data once you've started modifying it

        if self.config['super_seeder']:
            self.set_super_seed()

        self.started = True
        return True

    def rerequest_complete(self):
        if self.rerequest:
            self.rerequest.finish()

    def stop_rerequest(self, forceShutdown):
        """@param forceShutdown: just drop everything, or try to notify trackers?
        @type forceShutdown: bool
        @returns: deferred or None"""
        if forceShutdown:
          if self.rerequest:
            self.rerequest.force_stop()
          return None
        if self.rerequest and not self.shutdownDeferred:
            d = self.rerequest.stop()
            if d == None:
              return None
            d.addCallback(self.tracker_stop_event_done)
            self.shutdownDeferred = defer.Deferred()
            return self.shutdownDeferred
        return None
        
            
    def force_stop_tracker(self):
      #presupposes that you have already called shutdown
      if self.shutdownDeferred:
        self.rerequest.force_stop()
        
    def tracker_stop_event_done(self, *args):
        if self.shutdownDeferred:
            log_msg("Stop event sent to tracker for %s" % (Basic.clean(self.filename)), 2, "tracker")
            self.shutdownDeferred.callback(True)
            self.shutdownDeferred = None

    def rerequest_lastfailed(self):
        if self.rerequest:
            return bool(self.rerequest.failureReason)
        return False

    def rerequest_ondownloadmore(self):
        if self.rerequest:
            self.rerequest.update()
    
    def add_trackers(self, torrentData):        
        self.rerequest.add_trackers(torrentData)

    def startRerequester(self):
        self.rerequest = Rerequester(self.port, self.myid, self.infohash, 
            self.response, self.config, 
            self.rawserver.add_task,
            self.errorfunc, self.excfunc,
            self.encoder.start_connections,
            self.connecter.how_many_connections, 
            self.storagewrapper.get_amount_left, 
            self.upmeasure.get_total, self.downmeasure.get_total,
            self.upmeasure.get_rate, self.downmeasure.get_rate,
            self.doneflag, self.unpauseflag, self.dht)
        self.encoder.rerequester = self.rerequest
        self.rerequest.start()

    def startStats(self, spew):
        self.statistics = Statistics(self.upmeasure, self.downmeasure,
                    self.connecter, self.httpdownloader, self.ratelimiter,
                    self.rerequest, self.filedatflag)
        if self.info.has_key('files'):
            self.statistics.set_dirstats(self.files, self.info['piece length'])
        if spew:
            self.spewflag.set()
        else:
            self.spewflag.clear()
            
        d = DownloaderFeedback(self.choker, self.httpdownloader, self.rawserver.add_task,
            self.upmeasure.get_rate, self.downmeasure.get_rate,
            self.ratemeasure, self.storagewrapper.get_stats,
            self.datalength, self.finflag, self.spewflag, self.statistics)
        return d.gather()


    def getPortHandler(self):
        return self.encoder


    def setUploadRate(self, rate):
        try:
            def s(self = self, rate = rate):
                self.config['max_upload_rate'] = rate
                self.ratelimiter.set_upload_rate(rate)
            self.rawserver.add_task(s)
        except AttributeError:
            pass

    def setConns(self, conns, conns2 = None):
        if not conns2:
            conns2 = conns
        try:
            def s(self = self, conns = conns, conns2 = conns2):
                self.config['min_uploads'] = conns
                self.config['max_uploads'] = conns2
                if (conns > 30):
                    self.config['max_initiate'] = conns + 10
            self.rawserver.add_task(s)
        except AttributeError:
            pass
        
    def setDownloadRate(self, rate):
        try:
            def s(self = self, rate = rate):
                self.config['max_download_rate'] = rate
                self.downloader.set_download_rate(rate)
            self.rawserver.add_task(s)
        except AttributeError:
            pass

    def startConnection(self, ip, port, id):
        self.encoder._start_connection((ip, port), id)
      
    def _startConnection(self, ipandport, id):
        self.encoder._start_connection(ipandport, id)
        
    def setInitiate(self, initiate):
        try:
            def s(self = self, initiate = initiate):
                self.config['max_initiate'] = initiate
            self.rawserver.add_task(s)
        except AttributeError:
            pass

    def getConfig(self):
        return self.config

    def getDefaults(self):
        return defaultargs(defaults)

    def getUsageText(self):
        return self.argslistheader

    def getResponse(self):
        try:
            return self.response
        except:
            return None

    def Pause(self):
        if not self.storagewrapper:
            return False
        self.unpauseflag.clear()
        self.rawserver.add_task(self.onPause)
        return True

    def onPause(self):
        self.whenpaused = clock()
        if not self.downloader:
            return
        self.downloader.pause(True)
        self.encoder.pause(True)
        self.choker.pause(True)
    
    def Unpause(self):
        self.unpauseflag.set()
        self.rawserver.add_task(self.onUnpause)

    def onUnpause(self):
        if not self.downloader:
            return
        self.downloader.pause(False)
        self.encoder.pause(False)
        self.choker.pause(False)
        if self.rerequest and self.whenpaused and clock()-self.whenpaused > 60:
            self.rerequest.update()      # rerequest automatically if paused for >60 seconds

    def set_super_seed(self):
        self.superseedflag.set()
        self.rawserver.add_task(self._set_super_seed)

    def _set_super_seed(self):
        if not self.super_seeding_active and self.finflag.isSet():
            self.super_seeding_active = True
            self.errorfunc('        ** SUPER-SEED OPERATION ACTIVE **\n' +
                           '  please set Max uploads so each peer gets 6-8 kB/s')
            def s(self = self):
                self.downloader.set_super_seed()
                self.choker.set_super_seed()
            self.rawserver.add_task(s)
            if self.finflag.isSet():        # mode started when already finished
                def r(self = self):
                    self.rerequest.update()  # so after kicking everyone off, reannounce
                self.rawserver.add_task(r)

    def am_I_finished(self):
        return self.finflag.isSet()

    def get_transfer_stats(self):
        return self.upmeasure.get_total(), self.downmeasure.get_total()
    
