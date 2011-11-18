#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Contains many possible Exceptions that we generate."""

import time

class InnomiNetError(Exception):
  """Derive from this for all of our customer exception classes"""
  def __str__(self):
    s = self.__doc__
    if self.args:
        s = '%s: %s.' % (s, ' '.join(self.args))
    return s

class DownloadSizeError(InnomiNetError):  pass
class CoinValidationError(InnomiNetError): pass
class DependencyError(InnomiNetError):  pass
class EarlyDepositError(InnomiNetError):  pass
class InsufficientACoins(InnomiNetError):  pass

class BadLoginPasswordError(Exception):
  """Format the amount of time left until you can try logging in again"""
  def __init__(self, timeout):
    self.timeout = timeout
    
  def __str__(self):
    currentTime = int(time.time())
    difference = self.timeout - currentTime
    if currentTime > self.timeout or self.timeout == 0:
      t = None
    elif difference == 1:
      t ="second"
    elif  difference < 60:
      t ="%s seconds" % (difference)
    elif difference < 60*60:
      t= "%s minutes" % (difference/60.0)
    elif difference < 24*60*60:
      t = "%s hours" % (difference/3600.0)
    else:
      t= "%s days" % (difference/86400.0)
    if not t:
      return "You supplied an invalid username or password or both.  Please try again :)"
    else:
      return "Invalid username or password or both:\n You may not login for another %s" % (t)

