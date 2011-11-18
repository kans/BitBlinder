#!/usr/bin/python
import optparse
import sys
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
from logging_common import calculate_email_conversion

def print_email_conversion(cur, timeStart, timeEnd, variant):
  (emailsSent, percentOpened, percentClicked, percentCreated, percentLoggedIn) = calculate_email_conversion(cur, timeStart, timeEnd, variant)
  #and print them out:
  print(\
"""
Total:        %s
Opened:     %.1f
Clicked:    %.1f
Created:    %.1f
Logged In:  %.1f
""" % (emailsSent, percentOpened, percentClicked, percentCreated, percentLoggedIn))

#timeStart = "2009-09-11 10:12:00"
timeStart = "2009-10-10 05:07:00"
timeEnd = "2011-09-11 10:12:09"  

for variant in ("HTML", "PLAIN"):
  print variant
  conn = db.Pool.get_conn()
  cur = conn.cursor()
  print_email_conversion(cur, timeStart, timeEnd, variant)

conn = db.Pool.get_conn()
cur = conn.cursor()
#and print out recent traffic too:
cur.execute("SELECT * FROM avgpaymentsperhour_stats ORDER BY time DESC LIMIT 24")
results = cur.fetchall()
for row in results:
  statTime, value = row
  print "%s:\t%.1f" % (statTime, value)

cur.close()
