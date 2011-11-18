# The contents of this file are subject to the BitTorrent Open Source License
# Version 1.1 (the License).  You may not copy or use this file, in either
# source code or executable form, except in compliance with the License.  You
# may obtain a copy of the License at http://www.bittorrent.com/license/.
#
# Software distributed under the License is distributed on an AS IS basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied.  See the License
# for the specific language governing rights and limitations under the
# License.

# Written by Greg Hazel
# based on code by Bram Cohen, Uoti Urpala

import sys
import copy
import urllib
import random
import logging
from binascii import b2a_hex
_ = str

from twisted.python.failure import Failure
from twisted.internet import defer
from twisted.web.error import Error as WebError
import BitTorrent.BitTorrentClient
from core.network.socks import Errors as sockserror
from common import Globals
from common.Errors import DependencyError
from common.utils import Basic
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler

version = Globals.VERSION
import time
bttime = time.time
from btformats import check_peers
from BitTorrent.bencode import bencode, bdecode
BTFailure = Exception
import twisted.internet.error

LOG_RESPONSE = False

def quote(x):
    return urllib.quote(x, safe='')
    
class Cancelled(Exception): pass
class ExhaustedTrackerList(Exception): pass

class Rerequester(object):

  def __init__( self, port, myid, infohash, torrentData, config,
                sched, errorfunc, excfunc, connect,
                howmany, amount_left, up, down, upratefunc, downratefunc,
                doneflag, unpauseflag, dht):
    """
     @param announceList: ?
     @param config:    preferences obj storing BitTorrent-wide
                       configuration.
     @param sched:     used to schedule events from inside rawserver's
                       thread.
     @param howmany:   callback to get the number of complete connections.
     @param connect:   callback to establish a connection to a peer
                       obtained from the tracker.
     @param amount_left: callback to obtain the number of bytes left to
                       download for this torrent.
     @param up:        callback to obtain the total number of bytes sent
                       for this torrent.
     @param down:      callback to obtain the total number of bytes
                       received for this torrent.
     @param port:      port to report to the tracker.  If the local peer
                       is behind a NAT then this is the local peer's port
                       on the NAT facing the outside world.
     @param myid:      local peer's unique (self-generated) id.
     @param infohash:  hash of the info section of the metainfo file.
     @param errorfunc: callback to report errors.
     @param doneflag:  when set all threads cleanup and then terminate.
     @param upratefunc: callback to obtain moving average rate on the
                       uplink for this torrent.
     @param downratefunc: callback to obtain moving average rate on the
                       downlink for this torrent.
    """
    assert type(port) in (int, long) and port > 0 and port < 65536, "Port: %s" % repr(port)
    assert callable(connect)
    assert callable(amount_left)
    assert callable(errorfunc)
    assert callable(upratefunc)
    assert callable(downratefunc)
    
    self.dht = dht
    self.unpauseflag = unpauseflag
    
    self.infohash = infohash
    self.peerid = myid
    self.port = port
    self.config = config
    self._sched = sched
    self.howmany = howmany
    self.connect = connect
    self.amount_left = amount_left
    self.up = up
    self.down = down
    self._errorfunc = errorfunc
    self.doneflag = doneflag
    self.upratefunc = upratefunc
    self.downratefunc = downratefunc
    self.previousDown = 0
    self.previousUp = 0
    
    #: a handle on the repeated calling of on_update
    self.updateEvent = None
    #: current status of the torrent.  One of 'started', '', 'completed', or 'stopped'.  See the tracker spec definition for a more detailed description of these states
    self.currentStatus = None
    #: a deferred that will be triggered when the current sequence of tracker requests is done
    self.currentDeferred = None
    #: the current tracker request sequence object (a RequestSequence)
    self.currentRequest = None
    #: a very short error message to display to the user
    self.errorMsg = None
    
    self.lastTime = 0
    self.failWait = None
    self.interval = self.config['rerequest_interval']
    self.knownSeeds = 0
    self.knownPeers = 0
    
    announceList = self._extract_tracker_list(torrentData)
    self.announceList = announceList
    # shuffle a new copy of the whole set only once
    shuffledAnnounceList = []

    for tier in announceList:
      # strip out udp urls
      shuffled_tier = self._make_announce_tier(tier)
      if not shuffled_tier:
        # strip blank lists
        continue
      random.shuffle(shuffled_tier)
      shuffledAnnounceList.append(shuffled_tier)
    if shuffledAnnounceList:
      self.announceList = shuffledAnnounceList
    if not self.announceList:
      raise Exception("No valid trackers in announce list!  (%s)" % (announceList))
        
#    #for testing trackers that are down
#    #self.announceList = [[TrackerConnection("http://47.45.33.22/", config['http_timeout'])]]
#    self.announceList.insert(0, [TrackerConnection("http://47.45.33.22/", config['http_timeout'])])
#    self.announceList[0].insert(0, TrackerConnection("http://47.45.33.22/", config['http_timeout']))

    
    #add any new DHT nodes listed in the torrent:
    self._load_nodes(torrentData)
    
  def _extract_tracker_list(self, torrentData):
    if torrentData.has_key('announce-list'):
      trackerlist = torrentData['announce-list']
    else:
      trackerlist = [[torrentData['announce']]]
    return trackerlist
    
  def _load_nodes(self, torrentData):
    if not self.dht:
      return
    try:
      if torrentData.has_key('nodes'):
        for host, port in torrentData['nodes']:
          self.dht.add_contact(host, port)
    except Exception, e:
      log_ex(e, "Failed to load new DHT nodes")
      
  def start(self):
    #cancel any current request:
    self._cancel_current_request()
    #make sure that the update function is scheduled properly:
    if not self.updateEvent:
      self.updateEvent = Scheduler.schedule_repeat(10, self._on_update)
    #and send off the new request to stop this torrent:
    return self._begin_new_request('started')
      
  def force_stop(self):
    """Called to forcefully stop any and all tracker communications"""
    #cancel any current request:
    self._cancel_current_request()
    
  def stop(self):
    #cancel any current request:
    self._cancel_current_request()
    #if we cannot announce, just go ahead and say that we're all done:
    if not self._can_announce():
      return None
    #send off the new request to stop this torrent:
    d = self._begin_new_request('stopped')
    d.addCallback(self._on_stopped)
    d.addErrback(log_ex, "failed to stop current tracker request")
    return d
    
  def get_trackers(self):
    allTrackers = []
    for trackerList in self.announceList:
      for tracker in trackerList:
        allTrackers.append(tracker.baseURL)
    return allTrackers
    
  def _has_tracker_url(self, url):
    for tier in self.announceList:
      for tracker in tier:
        if url == tracker.baseURL:
          return True
    return False
    
  def set_trackers(self, urlList):
    #check if there are any new trackers?
    hasNewTrackers = False
    for url in urlList:
      if not self._has_tracker_url(url):
        hasNewTrackers = True
        break
    #were any trackers deleted?
    trackersRemoved = False
    for tier in self.announceList:
      for tracker in tier:
        if tracker.baseURL not in urlList:
          trackersRemoved = True
          break
    #we're done if there are no new trackers, and none were removed
    if not hasNewTrackers and not trackersRemoved:
      return
    #cancel any existing request
    self._cancel_current_request()
    #make a new announcelist based on trackerList
    self.announceList = [self._make_announce_tier(urlList)]
    #only bother restarting if trackers were added:
    if hasNewTrackers:
      #reset this so it looks like we've just started up
      self.currentStatus = None
      #then send a new start event:
      self.start()
    
  def _make_announce_tier(self, tier):
    trackerList = []
    for url in tier:
      if not url.lower().startswith("udp://"):
        trackerList.append(TrackerConnection(url, self.config['http_timeout']))
    return trackerList
    
  def add_trackers(self, torrentData):
    #add any new nodes from the torrent file too
    self._load_nodes(torrentData)
    #and add any new trackers:
    announceList = self._extract_tracker_list(torrentData)
    #add all unique new trackers from each tier:
    for tier in range(0, len(announceList)):
      #make sure we have such a tier:
      if tier >= len(self.announceList):
        self.announceList.append([])
      #check each tracker from that tier
      newTrackers = []
      for tracker in announceList[tier]:
        #does this URL already exit?
        found = False
        for t in self.announceList[tier]:
          if tracker == t.baseURL:
            found = True
            break
        if not found:
          newTrackers.append(TrackerConnection(tracker, self.config['http_timeout']))
      #then add all those new trackers to our list:
      #NOTE:  These new trackers MUST go at the end of the list, because we manipulate the list on tracker success  :(
      self.announceList[tier] = self.announceList[tier] + newTrackers
    
  #if the stopped event finishes successfully, then cancel the update event:
  def _on_stopped(self, result):
    if result is True:
      #this is effectively the same as the mainline BitTorrent code
      self.previousUp = self.up()
      self.previousDown = self.down()
    if self.updateEvent and self.updateEvent.active():
      self.updateEvent.cancel()
      self.updateEvent = None
    
  #This gets called a number of places, but we're already updating as regularly as possible
  def update(self, force=False):
    if not force:
      return
    if not self.currentRequest:
      self._announce()

  def finish(self):
    #cancel any current request:
    self._cancel_current_request()
    #and send off the new request to stop this torrent:
    return self._begin_new_request('completed')
    
  def _begin_new_request(self, status):
    self.currentDeferred = defer.Deferred()
    self.currentStatus = status
    self._announce()
    return self.currentDeferred
    
  def _cancel_current_request(self):
    if self.currentRequest:
      self.currentRequest.stop()
      self.currentRequest = None
    if self.currentDeferred:
      self.currentDeferred.callback(False)
      self.currentDeferred = None

  def _on_update(self):
    try:
      #figure out if we should announce or not
      shouldAnnounce = True
      #is there a request in progress?
      if self.currentRequest != None:
        shouldAnnounce = False
      #do we have to wait longer due to failure?
      curTime = bttime()
      if self.failWait and curTime < self.lastTime + self.failWait:
        shouldAnnounce = False
      #is this a regular update?
      if self.currentStatus == '':
        #do we have to wait longer because the tracker told us to?
        if curTime < self.lastTime + self.interval:
          shouldAnnounce = False
        #do we have so many peers that we dont need to do an update?
        if self.howmany() > self.config['min_peers']:
          shouldAnnounce = False
      if shouldAnnounce:
        #ok, looks like we should start a new update:
        self._announce()
    except Exception, e:
      log_ex(e, "Unexpected error while considering tracker update")
    #because we want this to be called repeatedly:
    return True
    
  def _can_announce(self):
    #check that we're ready to be sending tracker connections
    if not BitTorrent.BitTorrentClient.get().is_ready():
      log_msg("Not announcing because BitTorrent is not ready yet.", 0, "tracker")
      return False
    #dont bother sending updates if we're paused:
    if not self.unpauseflag.isSet():
      log_msg("Not announcing because this torrent is paused.", 4, "tracker")
      return False
    return True

  def _announce(self):
    if not self._can_announce():
      return
    #make sure that no request is already in progress:
    assert not self.currentRequest
    #make the tracker request string
    s = ('uploaded=%s&downloaded=%s&left=%s' %
         (str(self.up() - self.previousUp),
          str(self.down() - self.previousDown), 
          str(self.amount_left())))
    #if we have enough peers already, don't ask for more- 
    #TODO: maybe shouldn't ask for peers if our status is stopped?
    if self.howmany() >= self.config['max_initiate']:
      s += '&numwant=0'
    #otherwise, check if we should maybe ask DHT too
    else:
      s += '&compact=1'
      #check if we should also do a dht announce
      self._announce_dht()
    if self.currentStatus not in (None, ''):
      s += '&event=' + self.currentStatus
    s += '&info_hash=%s&peer_id=%s&port=%s' % (quote(self.infohash), quote(self.peerid), str(self.port))
    #create and return the actual request object
    self.currentRequest = RequestSequence(copy.deepcopy(self.announceList), s)
    d = self.currentRequest.start()
    if d:
      d.addCallback(self._on_tracker_success, prevRequest=self.currentRequest)
      d.addErrback(self._on_tracker_failure, prevRequest=self.currentRequest)
    
  def _announce_dht(self):
    if self.dht:
      #don't request more peers unless this is the start or an update (ie, not when stopping or finishing)
      if self.currentStatus == 'started':
        self.dht.get_peers_and_announce(self.infohash, self.port, self._handle_new_peers)
      elif self.currentStatus == '':
        self.dht.get_peers(self.infohash, self._handle_new_peers)
              
  def _on_tracker_success(self, successfulTracker, prevRequest):
    self.currentRequest = None
    
    #swap the successful tracker to the front of the tier list
    tmp = self.announceList[prevRequest.tier].pop(prevRequest.announce_i)
    self.announceList[prevRequest.tier].insert(0, tmp)
    
    #any time an event succeeds, status gets reset to '' so that tracker updates happen properly
    self.currentStatus = ''
    self.lastTime = bttime()
    
    self.knownSeeds = successfulTracker.tracker_num_seeds
    self.knownPeers = successfulTracker.tracker_num_peers
    
    #actually parse the response
    r = successfulTracker.data
    if 'min interval' in r:
      self.interval = r['min interval']
    else:
      self.interval = r.get('interval', self.interval)
    self.failWait = None
    #see if there were any warnings or errors in any of the tracker responses:
    self.errorMsg = self._get_error_message(prevRequest.announceList)

    self._handle_new_peers(r)
    
    #trigger any events that were waiting on this deferred to finish
    if self.currentDeferred:
      self.currentDeferred.callback(True)
      self.currentDeferred = None

  def _handle_new_peers(self, r):
    p = r['peers']
    peers = []
    if type(p) == type(''):
        lenpeers = len(p)/6
    else:
        lenpeers = len(p)
    cflags = r.get('crypto_flags')
    if type(cflags) != type('') or len(cflags) != lenpeers:
        cflags = None
    if cflags is None:
        cflags = [None for i in xrange(lenpeers)]
    else:
        cflags = [ord(x) for x in cflags]
    if type(p) == type(''):
        for x in xrange(0, len(p), 6):
            ip = '.'.join([str(ord(i)) for i in p[x:x+4]])
            port = (ord(p[x+4]) << 8) | ord(p[x+5])
            peers.append(((ip, port), 0, cflags[int(x/6)]))
    else:
        for i in xrange(len(p)):
            x = p[i]
            peers.append(((x['ip'].strip(), x['port']),
                          x.get('peer id',0), cflags[i]))
    ps = len(peers) + self.howmany()
    if ps < self.config['max_initiate']:
        if self.doneflag.isSet():
            if r.get('num peers', 1000) - r.get('done peers', 0) > ps * 1.2:
                self.last = None
        else:
            if r.get('num peers', 1000) > ps * 1.2:
                self.last = None
    self.connect(peers)
    log_msg('Tracker response: %d peers' % (len(peers)), 3, "tracker")
    
  def _get_error_message(self, announceList):
    """@returns:  the error or warning, or None if there was no error or warning for any trackers."""
    #first see if there is a trackerError or errorMsg
    warning = None
    for tier in announceList:
      for tracker in tier:
        if tracker.trackerError:
          return tracker.trackerError
        if tracker.errorMsg:
          return tracker.errorMsg
        if tracker.trackerWarning:
          warning = tracker.trackerWarning
    #then check for a tracker warning
    return warning
    
  def _on_tracker_failure(self, exc=None, prevRequest=None):
    self.currentRequest = None
    if exc:
      #ensure that exc is the actual Exception (not a failure)
      if hasattr(exc, "value"):
        exc = exc.value
      #completely ignore Cancelled exceptions as failures
      if issubclass(type(exc), Cancelled):
        return
      #dont bother logging when we've exhausted the tracker list
      if issubclass(type(exc), ExhaustedTrackerList):
        log_msg("Tried all trackers, no response from any.", 4, "tracker")
      #wasnt an expected error, so log it
      else:
        log_ex(exc, "Unexpected tracker error")
    #parse through the various failures to find why.
    self.errorMsg = self._get_error_message(prevRequest.announceList)
    if not self.errorMsg:
      self.errorMsg = "Failed to connect"
    
    if self.failWait is None:
      self.failWait = 5
    else:
      self.failWait *= 1.4 + random.random() * .2
    self.failWait = min(self.failWait, self.config['max_announce_retry_interval'])
    
  # Must destroy all references that could cause reference circles
  def cleanup(self):
    self.sched = None
    self.howmany = None
    self.connect = None
    self.amount_left = None
    self.up = None
    self.down = None
    self.upratefunc = None
    self.downratefunc = None

  def _give_up(self):
    if self.howmany() == 0 and self.amount_left() > 0 and not self.has_dht:
      # sched shouldn't be strictly necessary
      def die():
        self.diefunc(logging.CRITICAL,
                     _("Aborting the torrent as it could not "
                       "connect to the tracker while not "
                       "connected to any peers. "))
      self.sched(0, die)
        
class RequestSequence(object):
    """keeps track of tracker request attempts while appropriately trying
    higher tier trackers in the case of a failure"""
    def __init__( self, announceList, extraArgs):      
      self.announceList = announceList
      self.deferred = None
      self.isRunning = False
      self.extraArgs = extraArgs
      self.tier = 0
      self.announce_i = 0
      
    def start(self):
      if not self.isRunning:
        self.isRunning = True
        #reset the indices (start from base tier again next time)
        self.tier = 0
        self.announce_i = 0
        self.deferred = defer.Deferred()
        self._rerequest()
      return self.deferred
      
    def stop(self):
      if self.isRunning:
        currentTracker = self._announce_list_next()
        currentTracker.stop()
        self._failure(Cancelled())

    def _announce_list_fail(self):
      """@returns: True if the announce-list was restarted"""
      self.announce_i += 1
      #if that was the last tracker in the current tier:
      if self.announce_i == len(self.announceList[self.tier]):
          self.announce_i = 0
          self.tier += 1
          #if that was the last tier in the current announce list:
          if self.tier == len(self.announceList):
              self.tier = 0
              return True
      return False

    def _announce_list_next(self):
      return self.announceList[self.tier][self.announce_i]

    def _rerequest(self):
      #get the next tracker to connect to:
      currentTracker = self._announce_list_next()
      #and start the request:
      d = currentTracker.start(self.extraArgs)
      d.addCallback(self._tracker_done)
      d.addErrback(log_ex, "failed to connect to tracker")
      
    def _success(self):
      if self.isRunning:
        self.isRunning = False
        currentTracker = self._announce_list_next()
        self.deferred.callback(currentTracker)
        self.deferred = None
      
    def _failure(self, reason):
      if self.isRunning:
        self.isRunning = False
        self.deferred.errback(reason)
        self.deferred = None
      
    def _tracker_done(self, didSucceed):
      #return immediately if we've been cancelled (arent running):
      if not self.isRunning:
        return
      #did the connection succeed?
      if didSucceed:
        self._success()
        return
      #if not, determine the next tracker:
      restarted = self._announce_list_fail()
      #fail completely if that was the last tracker (ie, we tried them all)
      if restarted:
        self._failure(ExhaustedTrackerList("Tried all trackers"))
        return
      #otherwise, send the next request
      self._rerequest()
      
class TrackerConnection(object):
  """actual tracker connections
  can start, or stop an attempt to communicate with a tracker
  """
  def __init__(self, url, timeout):
    self.baseURL = url
    self.timeout = timeout
    self.key = b2a_hex(''.join([chr(random.randrange(256)) for i in xrange(4)]))
    self.numRetries = 0
    self.MAX_RETRIES = 3
    self.started = False
    self.finished = False
    self.deferred = None
    self.last = None
    self.trackerId = None
    self.tracker_num_seeds = None
    self.tracker_num_peers = None
    self.trackerWarning = None
    self.trackerError = None
    self.errorMsg = None
    self.error = None
    self.data = None
    self.extraArgs = None

  #NOTE:  the first time this is called, it must be passed extraArgs.  
  #subsequent calls will use those args until new args are passed
  def start(self, extraArgs=None):
    #stop if we dont care about this sequence anymore
    assert not self.finished, 'all done, why are you calling me?'
    if not self.started:
      self.deferred = defer.Deferred()
      self.started = True
    if extraArgs:
      self.extraArgs = extraArgs
    assert self.extraArgs, 'I must be called with extra args at start'
    #create the tracker URL from the base URL and our extra arguments:
    url = self._get_url(self.extraArgs)
    #ok, everything is ready.  Actually send the request (might be proxied)
    BitTorrent.BitTorrentClient.get().send_tracker_request(url, self.timeout, self._on_success, self._on_failure)
    return self.deferred
    
  def stop(self):
    self._on_failure(Cancelled())
    
  def _get_url(self, extraArgs):
    myArgs = ['key=%s' % (self.key)]
    if extraArgs:
      myArgs += [extraArgs]
    if self.last is not None:
      myArgs += ['last=%s' % (quote(str(self.last)))]
    if self.trackerId is not None:
      myArgs += ['trackerid=%s' % (quote(str(self.trackerId)))]
    myArgsString = '&'.join(myArgs)
    url = self.baseURL
    if '?' in url:
      url += "&" + myArgsString
    else:
      url += "?" + myArgsString
    return url
               
  def _on_failure(self, failure, httpDownloadInstance=None, errorMsg=None):
    #ignore errors if this connection is already done:
    if self.finished:
      return
    #ignore errors if this connection was cancelled:
    if type(failure) is type(Cancelled()):
      self.errorMsg = "Cancelled"
      log_msg("Tracker connection with %s was cancelled." % (Basic.clean(self.baseURL)), 1, "tracker")
      self.finished = True
      self.deferred.callback(False)
      return
      
    #determine the exception that caused this failure:
    exc = failure
    if hasattr(exc, "value"):
      exc = exc.value

    #should we just retry this tracker immediately?  (eg, if the circuit failed, not the tracker)
    if httpDownloadInstance and not httpDownloadInstance.circuit_is_alive():
      shouldRetry = False
      #these are the two errors that potentially mean we should retry the tracker
      if issubclass(type(exc), defer.TimeoutError):
        log_msg("Retrying tracker because of timeout error", 4, "tracker")
        shouldRetry = True
      elif issubclass(type(exc), sockserror.ConnectError):
        log_msg("Retrying tracker because of connection error", 4, "tracker")
        shouldRetry = True
      #try again if we havent already done so too many times:
      if shouldRetry and self.numRetries < self.MAX_RETRIES:
        self.numRetries += 1
        self.start()
        return

    #ignore these errors:
    self.errorMsg = None
    #happens during shutdown when BitBlinder is no longer ready
    if Basic.exception_is_a(exc, [DependencyError]):
      log_msg("Did not connect to tracker %s because %s" % (Basic.clean(self.baseURL), exc), 4, "tracker")
    #for when we're closing connections during shutdown or if the tracker doesnt want to talk to us
    elif Basic.exception_is_a(exc, [twisted.internet.error.ConnectionDone, twisted.internet.error.ConnectionLost, twisted.internet.error.ConnectionRefusedError]):
      self.errorMsg = "closed connection"
      log_msg("Tracker %s disconnected cleanly before responding" % (Basic.clean(self.baseURL)), 4, "tracker")
    #tracker took too long
    elif Basic.exception_is_a(exc, [defer.TimeoutError, twisted.internet.error.TCPTimedOutError]):
      self.errorMsg = "timeout"
      log_msg("Tracker %s timed out" % (Basic.clean(self.baseURL)), 4, "tracker")
    #generic errors meaning that the host was legitimately not reachable
    elif Basic.exception_is_a(exc, [sockserror.ConnectError, twisted.internet.error.ConnectError]):
      self.errorMsg = "unreachable"
      log_msg("Tracker %s appears unreachable" % (Basic.clean(self.baseURL)), 4, "tracker")
    #tracker web server is down or moved or something
    elif Basic.exception_is_a(exc, [WebError]):
      self.errorMsg = str(exc)
      log_msg("Tracker %s is down:  %s" % (Basic.clean(self.baseURL), exc), 2, "tracker")
    #generic error handler--let it be an exception that gets logged so we can learn about it and handle appropriately
    else:
      log_ex(failure, "Unexpected failure during tracker connection")
    
    #format the error and return
    if not self.errorMsg:
      try:
        self.errorMsg = failure.getErrorMessage()
      except:
        self.errorMsg = str(failure)
      msg = "Problem connecting to tracker (%s): %s" % (Basic.clean(self.baseURL), self.errorMsg)
      log_msg(msg, 2, "tracker")
    
    self.finished = True
    self.deferred.callback(False)

  def _on_success(self, response, httpDownloadInstance=None):
    #stop if we dont care about this sequence anymore
    if self.finished:
      return
    #try decoding the tracker response
    try:
      data = bdecode(response)
      log_msg('tracker response: %r' % (Basic.clean(data)), 4, "tracker")
      check_peers(data)
    #try the next tracker if that failed, and log the bad response
    except Exception, e:
      log_ex(e, "Bad data from tracker:  %s" % (Basic.clean(response)))
      self.errorMsg = "Bad data from tracker"
      self.finished = True
      self.deferred.callback(False)
      return
    
    assert self.trackerError is None, 'tracker error'
    #check if we got a critical error from the tracker
    if 'failure message' in data:
      self.trackerError = data['failure message']
    if 'failure reason' in data:
      self.trackerError = data['failure reason']
    #if we did, have to return, we failed
    if self.trackerError:
      self.errorMsg = self.trackerError
      self.finished = True
      self.deferred.callback(False)
      return
      
    if 'warning message' in data:
      self.trackerWarning = data['warning message']
      
    if (isinstance(data.get('complete'), (int, long)) and
        isinstance(data.get('incomplete'), (int, long))):
      self.tracker_num_seeds = data['complete']
      self.tracker_num_peers = data['incomplete']
    else:
      self.tracker_num_seeds = None
      self.tracker_num_peers = None
      
    self.trackerId = data.get('tracker id', self.trackerId)
    self.last = data.get('last')
    
    #tracker connection succeeded, trigger the deferred
    self.data = data
    self.finished = True
    self.deferred.callback(True)
        
