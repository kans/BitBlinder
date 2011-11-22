#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""Records Average CPU usage for each minute"""

import time
import atexit
import signal

from Events import CpuUsage
import EventLogging
EventLogging.open_logs("/mnt/logs/cpu/cpu_events.out")

#time inbetween each collection point- the cpu usage is also averaged over this time period
INTERVAL = 60
#INTERVAL = 1

signal.signal(signal.SIGHUP, signal.SIG_IGN)

print 'Recording average cpu usage every %s seconds' % (INTERVAL)
def done():
  EventLogging.close_logs()
  print 'all done'
  
atexit.register(done)

def get_times():
  f = open("/proc/stat", "rb")
  line = f.readline()
  f.close()
  data = line.split(" ")
  data.pop(0)
  data.pop(0)
  userTime = int(data.pop(0))
  niceTime = int(data.pop(0))
  systemTime = int(data.pop(0))
  idleTime = int(data.pop(0))
  usage = userTime + niceTime + systemTime
  total = usage + idleTime
  return usage, total

lastUsageTime, lastTotalTime = get_times()
while True:
  time.sleep(INTERVAL)
  usageTime, totalTime = get_times()
  usage = float(usageTime - lastUsageTime) / float(totalTime - lastTotalTime)
  print usage
  EventLogging.save_event(CpuUsage(usage=usage))
  lastUsageTime, lastTotalTime = usageTime, totalTime
