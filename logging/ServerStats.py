#!/usr/bin/python

from serverCommon import DBUtil

def update_statistics(cur, startTime):
  """Given a starting time, update all statistics tables with any information since that time"""
  #update all hourly stats
  _update_statistics(cur, startTime, 60 * 60, _get_hourly_stat_types())
  #update all daily stats
  _update_statistics(cur, startTime, 24 * 60 * 60, _get_daily_stat_types())

def create_tables(conn):
  cur = conn.cursor()
  """Create the tables necessary for storing statistics"""
  for statType in _get_all_stat_types():
    _create_table(statType, cur)
  conn.commit()
  
def destroy_tables(cur):
  """Destroy the tables necessary for storing statistics.  Mostly for easier debugging."""
  for statType in _get_all_stat_types():
    _destroy_table(statType, cur)

def _get_all_stat_types():
  return _get_daily_stat_types() + _get_hourly_stat_types()

def _get_hourly_stat_types():
  return (UsersPerHour, LoginsPerHour, AvgPaymentsPerHour, AvgRequestsPerHour, AvgDepositsPerHour, RelaysPerHour, MedianRelayBandwidthPerHour, TotalRelayBandwidthPerHour)

def _get_daily_stat_types():
  return (UsersPerDay, LoginsPerDay, AvgLoginsPerUserPerDay)

def _create_table(statType, cur):
  stat = statType()
  tableName = stat._get_table_name()
  if not DBUtil.table_exists(cur, tableName):
    sql = "CREATE TABLE %s (time TIMESTAMP WITHOUT TIME ZONE, value REAL);" % (tableName)
    cur.execute(sql)
  
def _destroy_table(statType, cur):
  stat = statType()
  return cur.execute("DROP TABLE IF EXISTS %s;" % (stat._get_table_name()))
      
def _update_statistics(cur, startTime, intervalLen, statTypes):
  """Update all statistics with the most recent events from the database"""
  currentTime = DBUtil.get_current_gmtime()
  intervalStartTime = startTime - (startTime % intervalLen)
  #for each type of stat:
  for statType in statTypes:
    #for each interval:
    for period in range(intervalStartTime, currentTime, intervalLen):
      #calculate the statistic
      stat = statType(period, period+intervalLen)
      stat.calculate(cur)
      #update it in the database
      stat.update(cur)

class Statistic():
  def __init__(self, startTime=None, endTime=None):
    """NOTE:  value is in the range [startTime, endTime)  (that's NON-inclusive to endTime)
    NOTE:  startTime and endTime can only be None when you are just using this statistic for figuring out the table name"""
    #: a time, given in seconds since the epoch, that marks the start of the interval for this statistic
    self.startTime = startTime
    #: a time, given in seconds since the epoch, that marks the end of the interval for this statistic.  values with time == endTime are NOT included.
    self.endTime = endTime
    #: the value of this statistic.  Can be an int or a float
    self.value = None
    
  def calculate(self, cur):
    """Determine the value of this statistic from the events in the database"""
    assert self.startTime != None and self.endTime != None, "Must initialize startTime and endTime before attempting to calculate the value!"
    self.value = self._calculate(cur)
    
  def update(self, cur):
    """Insert the current value into the statistics database"""
    assert self.value != None, "Must call calculate or load before attempting to update the database"
    if self._row_exists(cur):
      self._update_row(cur)
    else:
      self._insert_row(cur)
        
  def _calculate(self, cur):
    """Must be implemented by subclasses to do their specific calculations.  Should return the value given startTime and endTime"""
    raise NotImplemented
    
  def _row_exists(self, cur):
    sql = "SELECT COUNT(*) FROM %s" % (self._get_table_name())
    sql += " WHERE time = %s;"
    cur.execute(sql, (self._get_db_start_time(),))
    numRows = cur.fetchone()[0]
    return numRows > 0
    
  def _update_row(self, cur):
    sql = "UPDATE %s" % (self._get_table_name())
    sql += " SET value = %s WHERE time = %s;"
    return cur.execute(sql, (self.value, self._get_db_start_time()))
    
  def _insert_row(self, cur):
    sql = "INSERT INTO %s" % (self._get_table_name())
    sql += " (time, value) VALUES (%s, %s)"
    return cur.execute(sql, (self._get_db_start_time(), self.value))
    
  def _get_db_start_time(self):
    return DBUtil.int_to_ctime(self.startTime)
    
  def _get_db_end_time(self):
    return DBUtil.int_to_ctime(self.endTime)
    
  def _get_table_name(self):
    return "%s_stats" % (self.__class__.__name__.lower())
    
class UsersPerTime(Statistic):
  def _calculate(self, cur):
    cur.execute("SELECT COUNT(*) FROM (SELECT DISTINCT source FROM bankpayment_events WHERE eventTime >= %s AND eventTime < %s) AS temp;", (self._get_db_start_time(), self._get_db_end_time()))
    return cur.fetchone()[0]
class UsersPerHour(UsersPerTime): pass
class UsersPerDay(UsersPerTime): pass
  
class AvgEventsPerHour(Statistic):
  def _calculate(self, cur):
    sql = "SELECT AVG(%s) FROM %s" % (self._columnName, self._eventTableName)
    sql += " WHERE eventTime >= %s AND eventTime < %s;"
    cur.execute(sql, (self._get_db_start_time(), self._get_db_end_time()))
    avg = cur.fetchone()[0]
    if not avg:
      avg = 0
    return avg
    
class AvgBankEventsPerHour(AvgEventsPerHour):
  _columnName = "amount"
class AvgPaymentsPerHour(AvgBankEventsPerHour):
  _eventTableName = "bankpayment_events"
class AvgRequestsPerHour(AvgBankEventsPerHour):
  _eventTableName = "bankrequest_events"
class AvgDepositsPerHour(AvgBankEventsPerHour):
  _eventTableName = "bankdeposit_events"
  
class AvgConsensusStatsPerHour(AvgEventsPerHour):
  _eventTableName = "newconsensus_events"
class RelaysPerHour(AvgConsensusStatsPerHour):
  _columnName = "numRelays"
class MedianRelayBandwidthPerHour(AvgConsensusStatsPerHour):
  _columnName = "medianBandwidth"
class TotalRelayBandwidthPerHour(AvgConsensusStatsPerHour):
  _columnName = "totalBandwidth"
  
class LoginsPerTime(Statistic):
  def _calculate(self, cur):
    cur.execute("SELECT COUNT(*) FROM (SELECT DISTINCT username FROM banklogin_events WHERE eventTime >= %s AND eventTime < %s) AS temp;", (self._get_db_start_time(), self._get_db_end_time()))
    return cur.fetchone()[0]
class LoginsPerHour(LoginsPerTime): pass
class LoginsPerDay(LoginsPerTime): pass
  
class AvgLoginsPerUserPerDay(Statistic):
  def _calculate(self, cur):
    cur.execute("SELECT AVG(num_logins) FROM (SELECT COUNT(username) as num_logins FROM banklogin_events WHERE eventTime >= %s AND eventTime < %s GROUP BY username) AS temp;", (self._get_db_start_time(), self._get_db_end_time()))
    avg = cur.fetchone()[0]
    if not avg:
      avg = 0
    return avg
