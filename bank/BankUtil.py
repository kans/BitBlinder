#!/usr/bin/python
# Copyright 2008-2009 Innominet
"""Misc functions for the bank servers"""

import time
import random
import calendar

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from serverCommon import DBUtil
from serverCommon import db

MAX_BANK_CLOCK_SKEW = 1.0*60.0
EXPIRED_CHECK_INTERVAL = 1.0*60.0

def get_interval_time_deltas():
  curTime = int(time.time())
  MIN_SEC = 5
  curExp = Globals.CURRENT_ACOIN_INTERVAL[1]-curTime
  if curExp < MIN_SEC:
    curExp = MIN_SEC
  nextExp = Globals.CURRENT_ACOIN_INTERVAL[2]-curTime
  if nextExp < MIN_SEC:
    nextExp = MIN_SEC
  return curExp, nextExp

def get_intervals():
  current = Globals.CURRENT_ACOIN_INTERVAL[0]
  if current == 0:
    previous = 1
  else:
    previous = current - 1
  return previous, current
  
def err(e):
  print e
  
def get_current_acoin_interval_sql():
  sql = """SELECT interval_id, spoils_on FROM acoin_interval WHERE valid_after < %s and spoils_on > %s UNION
           SELECT interval_id, spoils_on FROM acoin_interval WHERE interval_id = 
          (SELECT interval_id FROM acoin_interval WHERE valid_after < %s and spoils_on > %s)+1"""
  now = gm_c_time()
  inj = (now, now, now, now)
  return sql, inj
  
def update_local_acoin_interval(onAcoinInterval=None, onNewIntervalCallback=None):
  """updates the local cache of the acoin interval and schedules the next update"""
  #get current and next interval info... 
  sql, inj = get_current_acoin_interval_sql()
  d = db.read(sql, inj)
  d.addCallback(check_acoin_interval, onAcoinInterval, onNewIntervalCallback)
  d.addErrback(err)
  
def check_acoin_interval(tup, onAcoinInterval=None, onNewIntervalCallback=None):
  #have we run out of intervals?
  if not tup:
    log_ex("Bank ran out of ACoin intervals!", "THIS MUST BE FIXED IMMEDIATELY")
  else:    
    learned_current_acoin_interval(tup, onAcoinInterval, onNewIntervalCallback)
    
def learned_current_acoin_interval(tup, onAcoinInterval=None, onNewIntervalCallback=None):
  #there must be at least one interval
  if len(tup) != 2:
    log_ex("Bank ran out of ACoin intervals!", "THIS MUST BE FIXED IMMEDIATELY")
    return
  current, next = tup
  interval = current[0]
  expires = DBUtil.ctime_to_int(current[1].ctime())
  expiresNext = DBUtil.ctime_to_int(next[1].ctime())
  #expires is natively a datetime
  #expires = DBUtil.ctime_to_int(expires.ctime())
  Globals.CURRENT_ACOIN_INTERVAL = [interval, expires, expiresNext]
  if onNewIntervalCallback:
    onNewIntervalCallback()
  now = int(time.time())
  if Globals.isListening == False:
    onAcoinInterval()
    Globals.isListening = True
  #schedule the next lookup after we know when the interval rolls over
  lookupTime = expires-now + (MAX_BANK_CLOCK_SKEW)
  if lookupTime <= 0:
    lookupTime = EXPIRED_CHECK_INTERVAL
  Globals.reactor.callLater(lookupTime, update_local_acoin_interval, onAcoinInterval, onNewIntervalCallback)

def add_time_tuple_to_ctime(now, dif):
  """
  now is a ctime
  dif is a timetuple or timelist
  returns a new ctime and float time
  MUST USE GM TIME
  """
  newTime = []
  timeTup = list(time.strptime(now))
  for position, item in enumerate(timeTup):
    newTime.append(item+dif[position])
  floatTime = calendar.timegm(newTime)
  newCTime = time.ctime(floatTime)
  return (newCTime, floatTime)

def is_positive_integer(num):
  if num <= 0 or type(num) is not int:
    return False
  else:
    return True
    
def gm_c_time(t=None):
  """returns a ctime like string of a time tuple"""
  if not t:
    t = time.gmtime()
  return time.asctime(t)
  
def kill_hours_minutes_secs(T):
  """takes a time tuple, sets the seconds, minutes, hours to 0"""
  t = [item for item in T]
  t[3] = 0
  t[4] = 0
  t[5] = 0
  return t

def create_deposit_time(currentIntervalRollOverTime):
  """generates a random deposit time within an hour after the rollover of the current interval
  returns the time as an int"""
  r = random.SystemRandom()
  offset = 0 #r.randint(0, 59)
  newCTime, floatTime = add_time_tuple_to_ctime(currentIntervalRollOverTime, (0, 0, 0, 0, offset, 0, 0, 0, 0)) #add offset minutes to the ctime
  return floatTime, newCTime
  
class BankException(Exception):
  def __init(self, value):
    self.value = value
    log_msg(self.value, 2)
  def __str__(self):
    return(self.value)
  
class MalformedRequest(BankException):  pass
class DepositRequestError(BankException):  pass
class SigningRequestError(BankException):  pass

class DetailedBankException(BankException):
  def __repr__(self):
    return (self.value)
    
class LoginRequestError(DetailedBankException):  pass
class NegativeMoniesError(DetailedBankException):  pass

class BadLogin(Exception):
  def __init__(self, username, pw, ip):
    self.username = username
    self.pw = pw
    self.ip = ip
  def __str__(self):
    return self.username
    
class LockedOut(Exception):
  def __init__(self, timeout):
    self.timeout = timeout
  def __str__(self):
    return ("Locked out until %s due to previous invalid login attempts"%self.timeout)

