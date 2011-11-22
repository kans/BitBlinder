#!/usr/bin/python
#Copyright 2008-2009 Innominet
"""Periodically pings servers to see if any are offline"""
#TODO:  does not properly detect whether the SVN server is running because that is on a VM behind VMWare Server, which acts as a software NAT

import time
import atexit
import signal
import socket

from Events import ServerDown
import EventLogging
EventLogging.open_logs("/mnt/logs/ping/ping_events.out")

#TODO:  move to a reactor so that we can lower this interval to a minute.  Currently not possible because the TCP connection timeout is too long and there are too many servers
INTERVAL = 60 * 60
#INTERVAL = 10

signal.signal(signal.SIGHUP, signal.SIG_IGN)

print 'Pinging servers every %s seconds' % (INTERVAL)
def done():
  EventLogging.close_logs()
  print 'all done'
  
atexit.register(done)

def is_reachable(url):
  """See if we can connect to a given host:port.
  Just want to know that the service is alive and reachable."""
  try:
    host, port = url.split(":")
    port = int(port)
    testSocket = socket.socket(socket.AF_INET)
    testSocket.settimeout(30.0)
    testSocket.connect((host, port))
    return True
  except:
    print("%s was unreachable" % (url))
    return False
    
def check_server(url):
  """Log an event if the url is unreachable"""
  if not is_reachable(url):
    EventLogging.save_event(ServerDown(url=url))

def check_all_servers():
  """Check server health--were each of the following servers online all day?"""
  #TODO:  this is a crazy way to test if we can reach the internet...
  if is_reachable("google.com:80"):
    #public svn
    check_server("svn.bitblinder.com:3690")
    #private svn
    check_server("private.bitblinder.com:3690")
    #amazon
    check_server("bitblinder.com:80")
    #emailslice
    check_server("innomi.net:80")
    #web server
    check_server("bitblinder.com:81")
    #bank server
    check_server("login.bitblinder.com:33348")
    #login server
    check_server("login.bitblinder.com:33349")
    #ftp server
    check_server("login.bitblinder.com:33330")
    #authorities
    check_server("174.129.199.15:33351")
    check_server("174.143.240.110:33353")
    check_server("174.129.199.15:33355")
    #email servers
    check_server("mail.bitblinder.com:143")
    check_server("mail.bitblinder.com:993")
  else:
    EventLogging.save_event(ServerDown(url="(test script)"))

while True:
  #figure out how long to sleep until the next interval
  curTime = time.time()
  extra = curTime - int(curTime)
  secondsLeft = INTERVAL - ((int(curTime) % INTERVAL) + extra)
#  print "Sleeping for %s seconds..." % (secondsLeft)
  time.sleep(secondsLeft)
  
  #then do the check
  check_all_servers()
  

