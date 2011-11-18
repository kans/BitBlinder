#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A logging class for the client program"""

import sys
import os
import platform
import shutil
import traceback
import time
import cStringIO

from common import Globals
from common.conf import Dev
from common.system import Files
from common.system import System
from common.classes import Scheduler
from common.classes import Logger as CommonLogging
from core import ProgramState

class Logger(CommonLogging.Logger):
  """Use the methods from this class to do all logging in the client"""
  def __init__(self):
    """Sets up the environment to log silently, if necessary, until the logs
    can be opened on the disk."""
    CommonLogging.Logger.__init__(self)
    self.hadError = False
    if ProgramState.PY2EXE:
      sys.stdout = Blackhole(self)
      sys.stderr = Blackhole(self)
    #set the events that we want to listen to:
    self.set_event_logging_levels(Dev.CLIENT_EVENT_LOGGING_LEVELS)
      
  def start(self):
    """Delete the old logs and open the new ones"""
    if ProgramState.PY2EXE:
      #these redirect output, to avoid writing to the Main.exe.log (default py2exe behavior)
      #we want to avoid that because it pops a dialog about errors, and we definitely want to fail silently when demoing the app...
      sys.stdout = open(os.path.join(Globals.LOG_FOLDER, 'stdout.out'), "w")
      sys.stderr = open(os.path.join(Globals.LOG_FOLDER, 'stderr.out'), "w")

    #remove the old tor logs:
    Files.delete_file(os.path.join(Globals.LOG_FOLDER, 'tor.out'), True)
    #open up the debug logs and create the testfile:
    self.start_logs(["main", "errors", "automated", "pysocks", "tor_conn"], "main", Globals.LOG_FOLDER)
    #rotate the logs every half an hour, so that they can have lots of info, but not fill someone's hard drive...
    Scheduler.schedule_repeat(30 * 60, self.rotate_logs)
    
  def log_msg(self, msg, debugval=0, log=None, popLevels=0):
    if log == "errors":
      try:
        msg = make_application_status() + "\n" + make_program_status() + "\n\n" + msg
        if not self.hadError:
          self.hadError = True
          msg = dump_system_info() + "\n" + make_platform_status() + "\n" + msg
        msg = "(<---occurred at this line)\n" + msg
      except Exception, error:
        msg = traceback.format_exc() + msg
    CommonLogging.Logger.log_msg(self, msg, debugval, log, popLevels+2)
      
  def report_startup_error(self, error):
    """Directly FTP an error that happened before the logs could even be opened"""
    self.log_ex(error, "Top level failure")
    if not self.openedLogs and "errors" in self.tempLogs:
      errorText = self.tempLogs["errors"]
      shouldReportError = True
      userOS = sys.platform
      if userOS == "win32":
        import win32api
        import win32con
        msgboxResult = win32api.MessageBox(0, repr(error)+"\n\nBitBlinder encountered an error.  Is it ok to send it to the developers so they can fix it?", "ERROR", win32con.MB_OKCANCEL)
        shouldReportError = msgboxResult == 1
      else:
        sys.stderr.write(repr(error))
      if shouldReportError:
        from ftplib import FTP
        #if the ftp server isn't up, this hangs like a fiend--unfortunately they only added
        #timeout support in 2.6 :(
        ftp = FTP()
        ftp.connect(Globals.FTP_HOST, Globals.FTP_PORT)
        ftp.login(Globals.FTP_USER, Globals.FTP_PASSWORD)
        buf = cStringIO.StringIO(dump_system_info() + "\n" + errorText)
        #send the buf and stor it as username@time
        name = "pre_crash_log"+'@'+Globals.VERSION+'@'+str(time.time())
        ftp.storbinary("STOR %s" % (name), buf)
        buf.close()
      
  def rotate_logs(self):
    """Move specified logs to *.old, reopen * and use that as the new log"""
    logsToRotate = ("main", "tor_conn", "pysocks")
    self.log_msg("Rotating logs...", 2)
    try:
      for log in logsToRotate:
        self.logFiles[log].close()
        src = os.path.join(Globals.LOG_FOLDER, self._get_file_name(log))
        dst = src + ".old"
  #      delete_file(dst, True)
        shutil.move(src, dst)
    except Exception, error:
      self.log_ex(error, "Error while rotating logs")
    finally:
      try:
        for log in logsToRotate:
          self.logFiles[log] = open(os.path.join(Globals.LOG_FOLDER, self._get_file_name(log)), 'wb')
      except Exception, error:
        self.log_ex(error, "Error restarting the logs")
    return True

class Blackhole(object):
  """Overriding file-object write method (so we can hijack stderr and stdout)"""
  def __init__(self, logger):
    self.logger = logger
    
  def write(self, text):
    """Either write to an error log (if logs are open), or save until later so
    that the text can be written to the error log."""
    #figure out what file to print to
    if "errors" not in self.logger.logFiles:
      outputFile = None
    else:
      outputFile = self.logger.logFiles["errors"]
    if outputFile:
      outputFile.write(text + "\n")
      #always flush everything now so we can be sure the messages are up to date while debugging
      outputFile.flush()
    else:
      if "errors" not in self.logger.tempLogs:
        self.logger.tempLogs["errors"] = ""
      self.logger.tempLogs["errors"] += text + "\n"
        
  def flush(self):
    """Do nothing when flushed, since we're just saving data until the logs are
    opened anyway."""
    
def make_platform_status():
  statusList = []
  #add program state:
  for varName in ("IS_LIVE", "INSTALLED", "PY2EXE", "JUST_UPDATED", "DEBUG", "IS_ADMIN"):
    statusList.append([varName, getattr(ProgramState, varName, None)])
    
  #check the state of each important directory:
  for varName in ("STARTING_DIR", "INSTALL_DIR", "USER_DIR"):
    dirName = getattr(ProgramState, varName, None)
    if dirName:
      #convert to a string if necessary:
      readAccess, writeAccess = System.check_folder_permissions(dirName)
      dirName = System.encode_for_filesystem(dirName)
    else:
      readAccess, writeAccess = (False, False)
    readStr = " "
    writeStr = " "
    if readAccess:
      readStr = "r"
    if writeAccess:
      writeStr = "w"
    permissionStr = readStr + writeStr
    dirStr = permissionStr + " " + str(dirName)
    statusList.append([varName, dirStr])
      
  #what type of GUI are they using?
  guiType = "console"
  if ProgramState.USE_GTK:
    guiType = "gtk"
  elif ProgramState.USE_CURSES:
    guiType = "gtk"
  statusList.append(["GUI", guiType])
  
  statusString = "\n".join([":  \t".join([str(r) for r in line]) for line in statusList])
  return statusString
  
def make_program_status():
  statusList = []
  statusList.append(["DONE", getattr(ProgramState, "DONE", None)])
  
  #how long have we been running?
  timeAlive = time.time() - ProgramState.START_TIME
  (month, day, hour, minute, second) = time.gmtime(timeAlive)[1:6]
  month -= 1
  day -= 1
  timeAliveString = "%s months, %s days, %s:%s:%s" % (month, day, hour, minute, second)
  statusList.append(["Elapsed Time", timeAliveString])
  
  statusString = "\n".join([":  \t".join([str(r) for r in line]) for line in statusList])
  return statusString
  
def dump_system_info():
  pythonVersion = None
  sysInfo = None
  pythonVersion = platform.python_version()
  if System.IS_WINDOWS:
    sysInfo = repr(sys.getwindowsversion())
  else:
    sysInfo = "%s\n%s" % (platform.uname(), platform.dist())
  return "Version:  %s\nPython:  %s\nSystem:  %s\nPlatform:  %s" % (Globals.VERSION, pythonVersion, sysInfo, sys.platform)
  
#TODO:  this definitely violates so architectural constraints, but it's necessary for debugging...
def make_application_status():
  from Applications import MainLoop
  return MainLoop.get().get_status()
  
    
