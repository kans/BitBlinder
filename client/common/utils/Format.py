#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Common message formatting functions."""

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def bytes_per_second(bytesPerSecond):
  """Converts from a float (in bytes per second) to a nice display string"""
  return format_bytes(bytesPerSecond) + "ps"
  
def format_bytes(numBytes):
  """Converts from a float (in bytes) to a nice display string"""
  numBytes = float(numBytes)
  labels = ["", "K", "M", "G"]
  if numBytes < 1:
    numBits = int(8 * numBytes)
    return "%d b" % (numBits)
  lim = 1024
  label = 0
  while lim < numBytes:
    lim *= 1024
    label += 1
    if label >= len(labels):
      label = len(labels)-1
      break
  lim /= 1024
  val = int(numBytes / lim)
  return "%d %sB" % (val, labels[label])

def convert_to_gb(numCredits):
  """1 credit is worth 5 MB, but about 15% or so is lost to bad circuits"""
  numMB = int(numCredits) * 5 * 0.8
  numGB = numMB / 1024.0
  if numGB > 1:
    return '%i GB' % (numGB)
  else:
    return '%i MB' % (numMB)
    
