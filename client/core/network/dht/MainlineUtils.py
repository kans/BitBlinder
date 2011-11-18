#!/usr/bin/python
#Copyright 2008-2009 InnomiNet

from time import time
bttime = time
from collections import deque

# The main drawback of this cache is that it only supports one time out 
# delay.  If you experience heavy load of cache inserts at time t then
# at t + expiration time, you will experience a heavy load due to
# expirations.  An alternative is to randomize the timeouts.  With 
# exponentially distributed timeouts we would expect load roughly obeying
# a Poisson process.  However, one can do better if the randomness if a
# function of load such that excess arrivals are redistributed evenly over the
# interval.

class Cache:
    # fixed TTL cache.  This assumes all entries have the same
    # TTL.
    def __init__(self, touch_on_access = False):
        self.data = {}
        self.q = deque()
        self.touch = touch_on_access
        
    def __getitem__(self, key):
        if self.touch:
            v = self.data[key][1]
            self[key] = v
        return self.data[key][1]

    def __setitem__(self, key, value):
        t = time()
        self.data[key] = (t, value)
        self.q.appendleft((t, key, value))

    def __delitem__(self, key):
        del(self.data[key])

    def has_key(self, key):
        return self.data.has_key(key)
    
    def keys(self):
        return self.data.keys()

    def expire(self, expire_time):
        try:
            while self.q[-1][0] < expire_time:
                x = self.q.pop()
                assert(x[0] < expire_time)
                try:
                    t, v = self.data[x[1]]
                    if v == x[2] and t == x[0]:
                        del(self.data[x[1]]) # only eliminates one reference to the
                                             # object.  If there is more than one
                                             # reference (for example if an
                                             # elements was "touched" by getitem)
                                             # then the item persists in the cache
                                             # until the last reference expires.
                                             # Note: frequently touching a cache entry
                                             # with long timeout intervals could be
                                             # viewed as a memory leak since the
                                             # cache can grow quite large.
                                             # This class is best used without
                                             # touch_on_access or with short expirations.
                except KeyError:
                    pass
        except IndexError:
            pass
            
# this is a base class for all the callbacks the server could use
class Handler(object):

    # called when the connection is being attempted
    def connection_starting(self, addr):
        temp=4

    # called when the connection is ready for writiing
    def connection_made(self, s):
        temp=4

    # called when a connection attempt failed (failed, refused, or requested)
    def connection_failed(self, s, exception):
        pass

    def data_came_in(self, addr, data):
        temp=4

    # called once when the current write buffer empties completely
    def connection_flushed(self, s):
        pass

    # called when a connection dies (lost or requested)
    def connection_lost(self, s):
        pass
        
class Measure(object):

    def __init__(self, max_rate_period, fudge=5):
        self.max_rate_period = max_rate_period
        self.ratesince = bttime() - fudge
        self.last = self.ratesince
        self.rate = 0.0
        self.total = 0
        self.when_next_expected = bttime() + fudge

    def update_rate(self, amount):
        self.total += amount
        t = bttime()
        if t < self.when_next_expected and amount == 0:
            return self.rate
        self.rate = (self.rate * (self.last - self.ratesince) +
                     amount) / (t - self.ratesince)
        self.last = t
        self.ratesince = max(self.ratesince, t - self.max_rate_period)
        self.when_next_expected = t + min((amount / max(self.rate, 0.0001)), 5)

    def get_rate(self):
        self.update_rate(0)
        return self.rate

    def get_rate_noupdate(self):
        return self.rate

    def time_until_rate(self, newrate):
        if self.rate <= newrate:
            return 0
        t = bttime() - self.ratesince
        # as long as the newrate is lower than rate, we wait
        # longer before throttling.
        return ((self.rate * t) / newrate) - t

    def get_total(self):
        return self.total
