# Written by Bram Cohen
# see LICENSE.txt for license information

import time
from random import randrange, shuffle
from BitTorrent.clock import clock

class Choker:
    def __init__(self, config, schedule, picker, done, swarmSize):
        self.config = config
        self.round_robin_period = config['round_robin_period']
        self.schedule = schedule
        self.picker = picker
        self.connections = []
        self.last_preferred = 0
        self.last_round_robin = clock()
        self.done = done
        self.super_seed = False
        self.paused = False
        self.perCircuit = {}
        self.get_swarm_size = swarmSize
        schedule(self._round_robin, 5)

    def set_round_robin_period(self, x):
        self.round_robin_period = x

    def _round_robin(self):
        self.schedule(self._round_robin, 5)
        curTime = time.time()
        toBeClosed = []
        maxInactiveTime = self.config['max_inactive_time']
        #NOTE:  this is a weird place for this maybe, but it had to be added somewhere...
        #if we have lots of connections
        if len(self.connections)+5 >= self.config['max_initiate']:
          #and there are other peers in the swarm to try:
          if self.get_swarm_size() > 1.5*len(self.connections):
            #close any connections that timed out
            for c in self.connections:
                #ignore seeds:
                if c.download.get_peer_completion() >= 1.0:
                  continue
                if c.lastActive + maxInactiveTime < curTime:
                  toBeClosed.append(c)
            for c in toBeClosed:
              c.protocol.close()

        if self.super_seed:
            cons = range(len(self.connections))
            to_close = []
            count = self.config['min_uploads']-self.last_preferred
            if count > 0:   # optimization
                shuffle(cons)
            for c in cons:
                i = self.picker.next_have(self.connections[c], count > 0)
                if i is None:
                    continue
                if i < 0:
                    to_close.append(self.connections[c])
                    continue
                self.connections[c].send_have(i)
                count -= 1
            for c in to_close:
                c.close()
        if self.last_round_robin + self.round_robin_period < clock():
            self.last_round_robin = clock()
            self.perCircuit = {}
            for i in xrange(1, len(self.connections)):
                c = self.connections[i]
                u = c.get_upload()
                if u.is_choked() and u.is_interested():
                    self.connections = self.connections[i:] + self.connections[:i]
                    break
        self._rechoke()

    def _rechoke(self):
        """Control which peers we are uploading to.  Prefers to upload to those peers that we are downloading from fastest right now."""
        preferred = []
        maxuploads = self.config['max_uploads']
        #Josh:  added better choke policy for when proxying connections
        usingTor = self.config['use_socks']
        #Choke all peers when paused
        if self.paused:
            for c in self.connections:
                c.get_upload().choke()
            return
        #if we are allowed to upload at all:
        if maxuploads > 1:
            #make an array of (rate, connection) for upload candidates
            for c in self.connections:
                u = c.get_upload()
                #ignore uninterested peers
                if not u.is_interested():
                    continue
                #if our download is done
                if self.done():
                    #prefer uploading to the best UPLOADERS
                    r = u.get_rate()
                else:
                    #otherwise upload to those peers who send data to us the fastest
                    d = c.get_download()
                    r = d.get_rate()
                    #ignore peers who have snubbed us, or are not uploading at an appreciable rate
                    if r < 1000 or d.is_snubbed():
                        continue
                #add the peer to the list of possible uploaders
                preferred.append((-r, c))
            self.last_preferred = len(preferred)
            #sort the list of uploaders by rate, essentially
            preferred.sort()
            #if data is being proxied, then upload to at most one peer per circuit
            if usingTor:
              #remove any entries that are no longer interested:
              toRemove = []
              for circ, c in self.perCircuit.iteritems():
                if not c.get_upload().is_interested():
                  toRemove.append(circ)
              for circ in toRemove:
                del self.perCircuit[circ]
              #first pick the optimistic unchoke if we need one
              if len(self.perCircuit) <= 0:
                for c in self.connections:
                  #pick the first interested peer
                  circ = c.get_circuit()
                  if circ and c.get_upload().is_interested():
                    self.perCircuit[circ] = c
                    break
              #then pick the rest based on our download speed from them:
              for r, c in preferred:
                #check that we dont have the max amount of uploads
                if len(self.perCircuit) >= maxuploads:
                  break
                circ = c.get_circuit()
                #if we dont yet have an upload peer for this circuit
                if circ and not self.perCircuit.has_key(circ):
                  #use this one
                  self.perCircuit[circ] = c
              #properly set the preffered list
              preferred = self.perCircuit.values()
            else:
              #delete all peers below a certain threshold
              del preferred[maxuploads-1:]
              #change the list to just be of the peers, in order of upload
              preferred = [x[1] for x in preferred]
        #number of upload slots taken by reciprocation for peers that are sending lots of data to us
        count = len(preferred)
        hit = False
        #since we already have the optimistic unchoke taken care of above
        if usingTor:
          hit = True
        to_unchoke = []
        #determine choking status for each connection
        for c in self.connections:
            u = c.get_upload()
            #unchoke preferred connections
            if c in preferred:
                to_unchoke.append(u)
            else:
                #unchoke the first peers if we have extra upload slots, or still need to fill the optimistic unchoke (hit)
                if count < maxuploads or not hit:
                    if u.is_interested():
                        #if we're proxying data
                        if usingTor:
                          #then ensure that we dont select more than one upload slot per circuit
                          circ = c.get_circuit()
                          if not circ or self.perCircuit.has_key(circ):
                            u.choke()
                            continue
                          else:
                            self.perCircuit[circ] = c
                        #add this peer as one of our upload slots
                        to_unchoke.append(u)
                        count += 1
                        hit = True
                    else:
                        to_unchoke.append(u)
                #otherwise, dont upload
                else:
                    u.choke()
        #unchoke the peers that we decided to upload to
        for u in to_unchoke:
            u.unchoke()

    def connection_made(self, connection, p = None):
        if p is None:
            p = randrange(-2, len(self.connections) + 1)
        self.connections.insert(max(p, 0), connection)
        self._rechoke()

    def connection_lost(self, connection):
        self.connections.remove(connection)
        self.picker.lost_peer(connection)
        if connection.get_upload().is_interested() and not connection.get_upload().is_choked():
            self._rechoke()

    def interested(self, connection):
        if not connection.get_upload().is_choked():
            self._rechoke()

    def not_interested(self, connection):
        if not connection.get_upload().is_choked():
            self._rechoke()

    def set_super_seed(self):
        while self.connections:             # close all connections
            self.connections[0].close()
        self.picker.set_superseed()
        self.super_seed = True

    def pause(self, flag):
        self.paused = flag
        self._rechoke()
