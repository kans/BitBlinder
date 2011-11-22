#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""#NOTE:  only works with postgres"""

import time
import re
import calendar
import types

import DBUtil

_VALUE_REGEX = re.compile("^(.+?)=([^=]*)(.*)$")

def synchronize(conn):
  for eventType in _get_all_events():
    table = EventTable(eventType)
    table.synchronize(conn)

def _get_all_events():
  allEvents = []
  for name in globals():
    try:
      thing = eval(name)
      if issubclass(thing, ServerEvent):
        allEvents.append(thing)
    except Exception, e:
      #print e
      pass
  return allEvents

class EventTable:
  #: a mapping from Python types to Postgresql types
  _DATABASE_TYPES = { types.StringType:  "text",
                      types.IntType:     "bigint",
                      types.LongType:    "bigint",
                      types.BooleanType: "boolean" }
  def __init__(self, eventType):
    event = eventType()
    self.tableName = event._get_table_name()
    self.eventColumns = {}
    for columnName, value in event.__dict__.iteritems():
      attr = getattr(event, columnName)
      if _isCallable(attr): 
        continue
      if columnName == "eventName":
        continue
      if columnName == "eventTime":
        columnType = "timestamp without time zone"
      else:
        columnType = self._DATABASE_TYPES[type(value)]
      self.eventColumns[columnName.lower()] = columnType.lower()
      
  def synchronize(self, conn):
    cur = conn.cursor()
    if not DBUtil.table_exists(cur, self.tableName):
      self._create_table(cur)
    self._check_table_columns(cur)
    conn.commit()
    
  def _create_table(self, cur):
    sql = "CREATE TABLE %s (id SERIAL, " % (self.tableName)
    for colName, colType in self.eventColumns.iteritems():
      sql += "%s %s, " % (colName, colType)
    sql += "PRIMARY KEY(ID));"
    return cur.execute(sql)
    
  def _check_table_columns(self, cur):
    dbColumns = self._get_table_names(cur)
    self._check_existing_columns(cur, dbColumns)
    self._add_new_columns(cur, dbColumns)
    
#  def destroy_table(eventType, cur):
#    event = eventType()
#    return cur.execute("DROP TABLE IF EXISTS %s;" % (event._get_table_name()))

  def _get_table_names(self, cur):
    sql = """SELECT
      a.attname as "Column",
      pg_catalog.format_type(a.atttypid, a.atttypmod) as "Datatype"
      FROM
      pg_catalog.pg_attribute a
      WHERE
      a.attnum > 0
      AND NOT a.attisdropped
      AND a.attrelid = (
          SELECT c.oid
          FROM pg_catalog.pg_class c
              LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          WHERE c.relname ~ '^(%s)$'
              AND pg_catalog.pg_table_is_visible(c.oid)
      );""" % (self.tableName)
    cur.execute(sql)
    results = cur.fetchall()
    dbColumns = {}
    for colTuple in results:
      colName, colType = colTuple
      dbColumns[colName.lower()] = colType.lower()
    return dbColumns
    
  def _check_existing_columns(self, cur, dbColumns):
    for colName, colType in dbColumns.iteritems():
      if colName == "id":
        continue
      if colName == "eventTime":
        colType = "timestamp without time zone"
      if colName in self.eventColumns:
        #are the types the different?
        if colType != self.eventColumns[colName]:
          #TODO:  are we allowed migrate these two types?
          sql = "ALTER TABLE %s ALTER COLUMN %s TYPE %s" % (self.tableName, colName, self.eventColumns[colName])
          cur.execute(sql)
        else:
          #column types are the same, all good
          pass
      else:
        #column does not exist in the event anymore.
        raise Exception("Column %s no longer exists in %s!" % (colName, self.tableName))
        
  def _add_new_columns(self, cur, dbColumns):
    #finally, check for new columns:
    for colName, colType in self.eventColumns.iteritems():
      if colName == "id":
        colType = "integer"
      if colName == "eventTime":
        colType = "timestamp without time zone"
      #if it does not already exist:
      if colName not in dbColumns:
        #then we have to make it:
        sql = "ALTER TABLE %s ADD COLUMN %s %s" % (self.tableName, colName, colType)
        cur.execute(sql)

class ServerEvent:
  def __init__(self, **kwargs):
    assert "eventName" not in kwargs
    assert "eventTime" not in kwargs
    assert "id" not in kwargs
    #TODO:  check for other reserved words too?
    assert "key" not in self.__dict__
    self.eventName = self.__class__.__name__
    self.eventTime = int(DBUtil.get_current_gmtime())
    if len(kwargs) <= 0:
      return
    for key, value in kwargs.iteritems():
      assert hasattr(self, key)
      assert not _isCallable(getattr(self, key))
      setattr(self, key, value)
    
  def save(self):
    """Save internal state to a string"""
    return str(self)

  def load(self, data):
    """Load internal state from the string 'data'"""
    restOfData = data
    while len(restOfData) > 0:
      #get the next key and value
      key, middleData, restOfData = _VALUE_REGEX.match(restOfData).groups()
      if restOfData != "":
        value, nextKey = middleData.rsplit(" ", 1)
        restOfData = nextKey + restOfData
      else:
        value = middleData
      #convert to the proper type
      attr = getattr(self, key)
      dataType = type(attr)
      value = dataType(value)
      #set our attribute based on the loaded data
      setattr(self, key, value)

  def get_time(self):
    return self.eventTime

  def __str__(self):
    keys = self.__dict__.keys()
    keys.sort()
    keys.remove("eventName")
    data = self.eventName
    for key in keys:
      attr = getattr(self, key)
      if _isCallable(attr): 
        continue
      strAttr = str(attr)
      assert '=' not in strAttr, "'=' is not allowed in event strings!"
      assert '\n' not in strAttr, "newlines are not allowed in event strings!"
      data += " " + key + "=" + strAttr
    return data
    
  def _insert_row(self, cur, forcedTime=None):
    sql = "INSERT INTO %s" % (self._get_table_name())
    keys = []
    values = []
    for key, value in self.__dict__.iteritems():
      if _isCallable(value): 
        continue
      if key == "eventName":
        continue
      if key == "eventTime":
        if forcedTime:
          value = forcedTime
        else:
          value = DBUtil.int_to_ctime(value)
      keys.append(key)
      values.append(value)
    sql = sql + " (%s) VALUES (%s)" % (", ".join(keys), ", ".join(["%s"]*len(keys)))
    return cur.execute(sql, values)
      
  def _get_table_name(self):
    return "%s_events" % (self.eventName.lower())
    
class DBEventInterface():
  def insert(self, cur):
    """Should insert your event data into the database appropriately"""
    raise NotImplemented
    
class IndividualEvent(ServerEvent, DBEventInterface):
  def insert(self, cur):
    return self._insert_row(cur)
    
class AggregateEvent(ServerEvent, DBEventInterface):
  def __init__(self, **kwargs):
    self.source = ""
    self.amount = 0
    ServerEvent.__init__(self, **kwargs)
    
  def insert(self, cur):
    #figure out what hour this event supposedly happened in:
    assert type(self.eventTime) == types.IntType, "eventTime must be an integer number of seconds!"
    exactTime = self.eventTime - (self.eventTime % _AGGREGATE_INTERVAL)
    exactTime = DBUtil.int_to_ctime(exactTime)
    #check if there is an existing row for this time and source:
    sql = "SELECT COUNT(*) FROM %s" % (self._get_table_name())
    sql += " WHERE eventTime = %s and source = %s;"
    cur.execute(sql, (exactTime, self.source))
    numRows = cur.fetchone()[0]
    if numRows > 0:
      assert numRows == 1, "Should never be multiple rows for the same time and source!"
      #update that row with the new count:
      sql = "UPDATE %s" % (self._get_table_name())
      sql += " SET amount = amount + %s WHERE eventTime = %s and source = %s;"
      return cur.execute(sql, (self.amount, exactTime, self.source))
    else:
      #insert a new row:
      return self._insert_row(cur, exactTime)

class EmailSent(IndividualEvent): 
  def __init__(self, **kwargs):
    self.address = ""
    self.hexkey = ""
    self.variant = ""
    ServerEvent.__init__(self, **kwargs)
    
class EmailOpened(IndividualEvent): 
  def __init__(self, **kwargs):
    self.hexkey = ""
    ServerEvent.__init__(self, **kwargs)
    
class EmailLinkVisit(IndividualEvent): 
  def __init__(self, **kwargs):
    self.hexkey = ""
    self.os = ""
    ServerEvent.__init__(self, **kwargs)
    
class AccountCreated(IndividualEvent): 
  def __init__(self, **kwargs):
    self.username = ""
    self.hexkey = ""
    self.mailinglist = False
    ServerEvent.__init__(self, **kwargs)
    
class Unsubscribed(IndividualEvent): 
  def __init__(self, **kwargs):
    self.address = ""
    ServerEvent.__init__(self, **kwargs)
    
class ServerDown(IndividualEvent): 
  def __init__(self, **kwargs):
    self.url = ""
    ServerEvent.__init__(self, **kwargs)
    
class BankLogin(IndividualEvent): 
  def __init__(self, **kwargs):
    self.username = ""
    ServerEvent.__init__(self, **kwargs)
    
class BankPayment(AggregateEvent): pass
class BankRequest(AggregateEvent): pass
class BankDeposit(AggregateEvent): pass

#logged every minute
class CpuUsage(IndividualEvent): 
  def __init__(self, **kwargs):
    self.usage = ""
    ServerEvent.__init__(self, **kwargs)

#: utility function to determine if something is a function or not
_isCallable = lambda o: hasattr(o, "__call__")
  
#: number of seconds to aggregate over
_AGGREGATE_INTERVAL = 60 * 60
