#!/usr/bin/python
# Copyright 2008 Innominet

import time
import hashlib
import calendar

def ctime_to_int(t):
  """notice: this returns the gmtime in secs, not the localtime - time.mktime does that"""
  return int(calendar.timegm(time.strptime(t)))
  
def int_to_ctime(t):
  """returns a ctime given a time float in gm time"""
  return time.asctime(time.gmtime(t))
  
def get_current_gmtime():
  """@returns: the current GMT time"""
  return calendar.timegm(time.gmtime())
  
def table_exists(cur, tableName):
  sql = "select count(table_name) from information_schema.tables where table_name = '%s';" % (tableName)
  cur.execute(sql)
  num = cur.fetchone()[0]
  return num > 0
  
def format_auth(username, password):
  auth = hashlib.sha256(username)
  auth.update(password)
  return auth.digest()
