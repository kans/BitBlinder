#!/usr/bin/python
import sys
import optparse

from serverCommon import DbAccessConfig

PARSER = optparse.OptionParser()
PARSER.add_option("--live", action="store_true", dest="is_live", default=False)
PARSER.add_option("--dev", action="store_true", dest="is_dev", default=False)
(options, args) = PARSER.parse_args()
if options.is_live:
  DbAccessConfig.database = "logging"
else:
  if not options.is_dev:
    print("You must use either the --live or --dev switches")
    sys.exit(1)

from serverCommon import cyborg_db as db
from logging_common import _make_conversion_tables

def get_signup_failures(cur, timeStart, timeEnd, variant):
  _make_conversion_tables(cur, timeStart, timeEnd, variant)
  #we want to know which people did not even make accounts:
  cur.execute("SELECT hexkey, address FROM emails_sent WHERE hexkey NOT IN (select hexkey from accounts_created);")
  userTuples = cur.fetchall()
  results = []
  for hexkey, emailAddress in userTuples:
    results.append(emailAddress)
  return results
  
def get_login_failures(): pass

def print_all_results(cur, timeStart, timeEnd, variant):
  _make_conversion_tables(cur, timeStart, timeEnd, variant)
  cur.execute("SELECT hexkey, address FROM emails_sent")
  emailsSent = cur.fetchall()
  results = []
  maxAddressLen = 0
  for hexkey, address in emailsSent:
    if len(address) > maxAddressLen:
      maxAddressLen = len(address)
    #did this person open it?
    cur.execute("SELECT COUNT(*) FROM emails_opened WHERE hexkey = %s", (hexkey,))
    didOpen = int(cur.fetchone()[0])
    #did this person visit the link?
    cur.execute("SELECT COUNT(*) FROM email_link_visits WHERE hexkey = %s", (hexkey,))
    didVisit = int(cur.fetchone()[0])
    if didVisit and not didOpen:
      didOpen = didVisit
    #did this person make an account?
    cur.execute("SELECT username FROM accounts_created WHERE hexkey = %s", (hexkey,))
    if cur.rowcount > 0:
      if cur.rowcount != 1:
        print("HEY!  not supposed to have more than one entry here!")
      accountName = cur.fetchone()[0]
      madeAccount = 1
      #did they login?
      cur.execute("SELECT DISTINCT COUNT(*) FROM banklogin_events WHERE username = %s", (accountName,))
      numLogins = cur.fetchone()[0]
    else:
      madeAccount = 0
      numLogins = 0
    if madeAccount > 0:
      results.append([address, didOpen, madeAccount, numLogins])
    
  for result in results:
    address = result.pop(0)
    address += ' '*(maxAddressLen-len(address))
    print address + '\t'.join([str(r) for r in result])

conn = db.Pool.get_conn()
cur = conn.cursor()

timeStart = "2009-10-10 05:07:00"
timeEnd = "2011-09-11 10:12:09" 
print_all_results(cur, timeStart, timeEnd, 'HTML')

#nonresponders = get_signup_failures(cur, timeStart, timeEnd, variant)
#for address in nonresponders:
#  print address

cur.close()
