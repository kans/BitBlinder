#!/usr/bin/python
from serverCommon import cyborg_db as db
from serverCommon import EventLogging

conn = db.Pool.get_conn()
cur = conn.cursor()
f = open("testevents.out", "rb")
for line in f.readlines():
  event = EventLogging.load_event(line)
  event.insert(cur)
cur.close()
conn.commit()
f.close()
