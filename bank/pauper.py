import signal
from time import strftime, gmtime, sleep
from serverCommon import cyborg_db as db

amount = 5
print 'adding 5 to every balance every hour'

signal.signal(signal.SIGHUP, signal.SIG_IGN)

def schedule_next_call():
  """determines when we should wake up to add monies-
  only schedules a wake up call at the start of every hour,
  so it is safe to start and stop as in the worst case an hour 
  could be missed"""
  now = int(strftime("%M", gmtime()))
  snooze = (60-now) + 1
  #convert to seconds
  snooze *= 60
  return snooze
  
def add_monies():
  """add amount to every balance everywhere"""
  sql = "UPDATE accounts SET balance=balance+%s"
  inj = (amount,)
  db.write(sql, inj)

while True:
  t = schedule_next_call()
  sleep(t)
  add_monies()
