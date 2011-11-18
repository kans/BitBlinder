#!/usr/bin/python
import optparse
from serverCommon import DbAccessConfig
import ServerStats

PARSER = optparse.OptionParser()
PARSER.add_option("--live", action="store_true", dest="is_live", default=False)
(options, args) = PARSER.parse_args()
if options.is_live:
  DbAccessConfig.database = "logging"

print "Updating the %s database.  Hit enter to continue." % (DbAccessConfig.database)
x = raw_input("")

from serverCommon import cyborg_db as db
from serverCommon import Events

conn = db.Pool.get_conn()
cur = conn.cursor()

dropTables = False
if not options.is_live:
  response = raw_input("Should we drop existing tables? (yes/no)  ")
  if response.lower() in ("y", "yes"):
    dropTables = True
    ServerStats.destroy_tables(cur)
    
ServerStats.create_tables(cur)
cur.close()
conn.commit()



