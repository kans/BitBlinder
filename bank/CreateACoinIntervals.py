import sys
import os
import calendar
import traceback
import BankUtil
from serverCommon.cyborg_db import Pool
from serverCommon import DBUtil

#TODO:  currently the next interval could roll over as we're doing this, in theory.  Check for that and prevent it!

conn = Pool.get_conn()
try:
  cur = conn.cursor()

  #should be sensible- don't use negative numbers etc.
  if os.path.exists("THIS_IS_DEBUG"):
    from common.conf import Dev as Conf
    lifetime = 15*60
    numberOfIntervalsToMake = 12*24*30
  else:
    from common.conf import Live as Conf
    lifetime = 12*60*60
    numberOfIntervalsToMake = 2*365*2
    
  def insert_interval_row(base, highestInterval):
    validAfter = base
    spoilsOn = validAfter + lifetime

    sql = "INSERT INTO acoin_interval (interval_id, valid_after, spoils_on) VALUES (%s, %s, %s)"
    inj = (highestInterval, DBUtil.int_to_ctime(validAfter), DBUtil.int_to_ctime(spoilsOn))
    cur.execute(sql, inj)
    
    return validAfter, spoilsOn
    
  def get_cur_interval():
    sql, inj = BankUtil.get_current_acoin_interval_sql()
    cur.execute(sql, inj)
    tup = cur.fetchall()
    return tup
    
  def get_last_interval():
    sql = "SELECT interval_id, spoils_on FROM acoin_interval WHERE interval_id = (SELECT Max(interval_id) FROM acoin_interval)"
    cur.execute(sql)
    tup = cur.fetchall()
    return tup
    
  tup = get_cur_interval()
  if not tup:
    tup = get_last_interval()
    if not tup:
      #have to create the initial row:
      print("No existing ACoin rows, creating initial value...")
      #TODO:  should be a better way to pick the start date?
      base = int(calendar.timegm((2009, 7, 10, 16, 0, 0, 4, 191, 0)))
      validAfter, spoilsOn = insert_interval_row(base, 1)
      tup = get_last_interval()
  else:
    if len(tup) > 1:
      tup = tup[1]
    else:
      tup = tup[0]
    nextInterval, nextTime = tup
    #make sure we destroy any later intervals
    print("WARNING:  DO NOT RUN THIS if the next interval is about to roll over!!")
    print("Are you SURE that you want to delete all intervals after the next one (%s)?  It ends on %s  (y/n):  " % (nextInterval, nextTime.ctime()))
    x = raw_input()
    if x != "y":
      raise Exception("User aborted.")
    cur.execute("DELETE FROM acoin_interval WHERE interval_id > %s", (nextInterval,))
    tup = get_last_interval()
    curInterval, curTime = tup[0]
    print("You deleted ALL intervals after %s (expires at %s).  Are you SURE you wanted to do that?  (type anything except continue to abort):  " % (nextInterval, nextTime.ctime()))
    x = raw_input()
    if x != "continue":
      raise Exception("User aborted.")
  assert tup
  assert len(tup) == 1
    
  highestACoinInterval, highestACoinFreshUntil = tup[0]
  #the freshness is a ctime type... we need to convert it into a float
  base = DBUtil.ctime_to_int(highestACoinFreshUntil.ctime())
  highestACoinInterval = int(highestACoinInterval)

  sql = []
  inj = []
  startTime = highestACoinFreshUntil.ctime()
  startInterval = highestACoinInterval
  print("Creating intervals...")
  for x in range(numberOfIntervalsToMake):
    highestACoinInterval += 1
    validAfter, spoilsOn = insert_interval_row(base, highestACoinInterval)
    #need to update base for next iteration
    base = spoilsOn
    
  print("Created %s interval[s] from time %s to time %s ending with interval: %s"%(highestACoinInterval - 1 - startInterval, startTime, DBUtil.int_to_ctime(spoilsOn), highestACoinInterval - 1))
  conn.commit()
except:
  traceback.print_exception(*sys.exc_info())
finally:
  conn.release()
