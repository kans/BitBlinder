#!/usr/bin/python

import optparse
import glob
import time
import os
import sys
import subprocess

import psycopg2 as cyborg

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Logger
from serverCommon import DbAccessConfig

#parse the options
parser = optparse.OptionParser()
parser.add_option("--live", action="store_true", dest="is_live", default=False)
parser.add_option("--dev", action="store_true", dest="is_dev", default=False)
(options, args) = parser.parse_args()
if options.is_live:
  DbAccessConfig.database = "logging"
else:
  if not options.is_dev:
    print("You must use either the --live or --dev switches")
    sys.exit(1)

from serverCommon import cyborg_db as db
from serverCommon import EventLogging
from serverCommon import Events
from serverCommon.DBUtil import get_current_gmtime
import ServerStats

#: the helper table to store information about how many events have been loaded from each file
EVENT_FILE_TABLE_NAME = "event_file_information"
#: given in seconds.  How long between downloading logs from the servers.
UPDATE_INTERVAL = 60.0 * 30
#: given in seconds.  How long must a file remain unmodified before we assume it can be deleted?  
FILE_EXPIRATION_DAYS = EventLogging.NUM_BACKUP_DAYS * 2
assert FILE_EXPIRATION_DAYS >= EventLogging.NUM_BACKUP_DAYS * 2, "Otherwise, you will be repeatedly downloading and deleting the same event files AND readding those events into the database, which is the worst idea."
#: the ssh key to log in to the remote servers (so we can get their logs)
IDENTITY = "/home/rtard/.ssh/innomikeypair.pem"

class EventLogParser():
  def __init__(self):  
    #make the log files
    self._hadFailure = False
    self.failureLineFile = None
    Globals.logger = Logger.Logger()
    if options.is_live:
      Globals.logger.start_logs(["logging_live", "errors_live"], "logging_live", ".")
      Globals.logger.ERROR_LOG_NAME = "errors_live"
      self.failureLineFile = open("failures_live.out", "a")
    else:
      Globals.logger.start_logs(["logging_dev", "errors_dev"], "logging_dev", ".")
      Globals.logger.ERROR_LOG_NAME = "errors_dev"
      self.failureLineFile = open("failures_dev.out", "a")
      
    #where to store the cached logs
    self.baseDataDir = "data"
    if options.is_live:
      self.baseDataDir += "_live"
    else:
      self.baseDataDir += "_dev"
    if not os.path.exists(self.baseDataDir):
      os.makedirs(self.baseDataDir)
      
    #what folders to synch and parse
    if options.is_live:
      self.serverList = {"bank":      "root@174.129.199.15:/mnt/logs/bank",
                         "web":       "root@174.129.199.15:/mnt/logs/web",
                         "email":     "root@174.129.199.15:/mnt/logs/email",
                         "cpu":       "root@174.129.199.15:/mnt/logs/cpu",
                         "consensus": "root@174.129.199.15:/mnt/logs/consensus",
                         "ping":      "root@174.129.199.15:/mnt/logs/ping"}
      self.logList = {"squid":        "root@174.129.199.15:/mnt/logs/squid"}
    else:
      self.serverList = {"bank":      "/mnt/logs/bank",
                         "web":       "/mnt/logs/web",
                         "email":     "/mnt/logs/email",
                         "cpu":       "/mnt/logs/cpu",
                         "consensus": "/mnt/logs/consensus",
                         "ping":      "/mnt/logs/ping"}
      self.logList = {"apache":       "/mnt/logs/apache"}
      
    #our connection to the database
    self.conn = db.Pool.get_conn()

    #make sure the event tables are up to date.
    #NOTE:  YOU MUST EXIT if either of these functions raises an exception!  Then go figure out why.
    Events.synchronize(self.conn)
    ServerStats.create_tables(self.conn)
    self._setup_initial_entries()
    
  def _setup_initial_entries(self):
    #if the table doesnt exist, create it
    cur = self.conn.cursor()
    try:
      cur.execute("SELECT COUNT(*) FROM %s" % (EVENT_FILE_TABLE_NAME))
    except cyborg.ProgrammingError, error:
      assert error.pgerror == 'ERROR:  relation "event_file_information" does not exist\n', "Unknown ProgrammingError:  %s" % (error)
      cur.close()
      self.conn.commit()
      cur = self.conn.cursor()
      cur.execute("""CREATE TABLE %s(
                    file_name VARCHAR(256),
                    folder_name VARCHAR(256),
                    event_number BIGINT,
                    last_mtime VARCHAR(64));""" % (EVENT_FILE_TABLE_NAME))
      #since there are no entries, loop over all the folders and files and insert a new row in the db for each
      for logTypeName in self.serverList.keys():
        dataDir = os.path.join(self.baseDataDir, logTypeName)
        fileNames = glob.glob(dataDir + "/*")
        for fileName in fileNames:
          baseFileName = os.path.split(fileName)[1]
          numEventsAlreadyLoaded = file_len(fileName)
          fileMTime = str(os.path.getmtime(fileName))
          self._insert_file_row(cur, baseFileName, logTypeName, numEventsAlreadyLoaded, fileMTime)
          
    cur.close()
    self.conn.commit()
    
  def _update_logs(self):
    #get misc logs:
    for logTypeName, remoteFolder in self.logList.iteritems():
      try:
        log_msg("Fetching misc logs from %s..." % (logTypeName))
        dataDir = os.path.join(self.baseDataDir, logTypeName)
        if not os.path.exists(dataDir):
          os.makedirs(dataDir)
        os.system('rsync --append -rtz -e "ssh -i %s" %s/ %s' % (IDENTITY, remoteFolder, dataDir))
      except Exception, error:
        self._log_failure(error, "Error while getting misc logs")
        
  def _update_events(self):
    earliestTime = get_current_gmtime()
    curTime = time.time()
    
    for logTypeName, remoteFolder in self.serverList.iteritems():
      try:
        log_msg("Updating logs from %s..." % (logTypeName))
        dataDir = os.path.join(self.baseDataDir, logTypeName)
        if not os.path.exists(dataDir):
          os.makedirs(dataDir)

        #get the changes from the remote server:
        os.system('rsync --append -rtz -e "ssh -i %s" %s/ %s' % (IDENTITY, remoteFolder, dataDir))
        
        #for each file in the folder
        fileNames = glob.glob(dataDir + "/*")
        for fileName in fileNames:
          baseFileName = os.path.split(fileName)[1]
          
          #ignore really old files:
          if self._file_is_old(fileName, curTime):
            self._remove_file(fileName, baseFileName, logTypeName)
            continue
          
          #look up the database row
          results = self._get_file_row(baseFileName, logTypeName)
          
          #if the row existed, figure out if it is old enough to be deleted
          if len(results) > 0:
            assert len(results) == 1, "Why are there two rows for %s and %s?" % (baseFileName, logTypeName)
            numEvents, lastMTimeString = results[0]
            rowExisted = True
            if not self._file_was_modified(fileName, lastMTimeString):
              #don't bother continuing to parse the file if it hasnt been modified
              continue
          #otherwise, just note that we've obviously never parsed any events from this file
          else:
            numEvents = 0
            rowExisted = False
            
          #load all lines
          cur = self.conn.cursor()
          try:
            startTime, newNumEvents = EventLogging.parse_events(cur, fileName, numEvents)
            if startTime < earliestTime:
              earliestTime = startTime
            log_msg("Parsed %s events" % (newNumEvents-numEvents))
          #if any line fails, abort everything and log the failure
          except Exception, error:
            self._log_failure(error, "Failure (%s) while processing line from %s" % (error, fileName))
          #otherwise update the file row in the database to note that we've successfully parsed newNumEvents events
          else:
            newMTimeString = str(os.path.getmtime(fileName))
            if rowExisted:
              self._update_file_row(cur, baseFileName, logTypeName, newNumEvents, newMTimeString)
            else:
              self._insert_file_row(cur, baseFileName, logTypeName, newNumEvents, newMTimeString)
          finally:
            cur.close()
            self.conn.commit()

      except Exception, error:
        self._log_failure(error, "Error while adding events from %s" % (logTypeName))
    return earliestTime
    
  def _remove_file(self, fileName, baseFileName, logTypeName):
    cur = self.conn.cursor()
    try:
      #remove the row from the db
      sql = "DELETE FROM "+EVENT_FILE_TABLE_NAME+" WHERE file_name = %s and folder_name = %s"
      inj = (baseFileName, logTypeName)
      cur.execute(sql, inj)
    finally:
      cur.close()
      self.conn.commit()
    #remove the file
    os.remove(fileName)
    
  def _file_is_old(self, fileName, curTime):
    lastMTime = os.path.getmtime(fileName)
    fileIsOld = (curTime - lastMTime) > (FILE_EXPIRATION_DAYS * 60.0 * 60.0 * 24)
    return fileIsOld
    
  def _file_was_modified(self, fileName, lastMTimeString):
    newMTime = os.path.getmtime(fileName)
    fileWasModified = str(newMTime) != lastMTimeString
    return fileWasModified
    
  def _get_file_row(self, baseFileName, logTypeName):
    results = None
    cur = self.conn.cursor()
    try:
      sql = "SELECT event_number, last_mtime FROM "+EVENT_FILE_TABLE_NAME+" WHERE file_name = %s and folder_name = %s"
      inj = (baseFileName, logTypeName)
      cur.execute(sql, inj)
      results = cur.fetchall()
    finally:
      cur.close()
      self.conn.commit()
    return results
    
  def _update_file_row(self, cur, baseFileName, logTypeName, newNumEvents, fileMTime):
    sql = "UPDATE "+EVENT_FILE_TABLE_NAME+" SET event_number = %s, last_mtime = %s WHERE file_name = %s and folder_name = %s"
    inj = (newNumEvents, str(fileMTime), baseFileName, logTypeName)
    cur.execute(sql, inj)
    
  def _insert_file_row(self, cur, baseFileName, logTypeName, newNumEvents, fileMTime):
    sql = "INSERT INTO "+EVENT_FILE_TABLE_NAME+" (file_name, folder_name, event_number, last_mtime) VALUES (%s, %s, %s, %s)"
    inj = (baseFileName, logTypeName, newNumEvents, str(fileMTime))
    cur.execute(sql, inj)
    
  def _update_statistics(self, earliestTime):
    log_msg("Updating statistics...")
    try:
      cur = self.conn.cursor()
      ServerStats.update_statistics(cur, earliestTime)
      cur.close()
      self.conn.commit()
    except Exception, error:
      self._log_failure("Error while updating statistics", error)
    
  def run(self):
    while True:
      #reset the failure marker:
      self._hadFailure = False
      
      #DEBUG:  was when we actually started logging live events (only login and web at first though)
      #earliestTime = 1252975780
      self._update_logs()
      
      earliestTime = self._update_events()
        
      #now it's time to update the persistent statistics:
      self._update_statistics(earliestTime)
      
      #email me to alert me if there were any failures:
      if self._hadFailure:
        process = subprocess.Popen('(echo "Subject: FETCH.PY FAILURE"; date) | sendmail jash@mail.bitblinder.com', shell=True)
        process.wait()
      #ok, now wait a while so we have new data to parse:
      log_msg("Waiting %s seconds for the next update..." % (UPDATE_INTERVAL))
      try:
        time.sleep(UPDATE_INTERVAL)
      except KeyboardInterrupt:
        self._shutdown()
    
  def _log_failure(self, reason, title):
    """Log the error and note that there was a failure so that I can get an email and come fix it."""
    log_ex(reason, title)
    self._hadFailure = True
    
  def _shutdown(self):
    self.failureLineFile.close()
    print "Closed cleanly"
    sys.exit(0)

def file_len(fname):
  process = subprocess.Popen(['wc', '-l', fname], stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE)
  result, err = process.communicate()
  if process.returncode != 0:
    raise IOError(err)
  return int(result.strip().split()[0])

PARSER = EventLogParser()
PARSER.run()
