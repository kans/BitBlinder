#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Misc. functions needed in various locations by the client, plus some monkeypatching"""

import os
import zipfile
import subprocess

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.system import System
from common.system import Files
from common.classes import Scheduler
from core import ProgramState
from core import Logging
from gui import GUIController
  
def check_port(portNum, successFunc):
  if portNum:
    pid = System.get_pid_from_port(portNum)
    if pid > 0:
      controller = GUIController.get()
      if controller: 
        controller.prompt_about_port(portNum, successFunc)
      else:
        log_msg("no gui controller yet to prompt_about_port", 2)
      return
  successFunc()
  
def add_updater(obj):
  def update():
    if ProgramState.DO_UPDATES:
      try:
        obj.on_update()
      except Exception, error:
        log_ex(error, "During update for %s" % (obj))
    return True
  Scheduler.schedule_repeat(Globals.INTERVAL_BETWEEN_UPDATES, update)
  
def get_image_file(imageName):
  """Given the name of an image, return the filename for the image data"""
  return os.path.join(Globals.DATA_DIR, unicode(imageName))
  
def create_error_archive(description):
  logs = ["main.out", "errors.out", "stderr.out", "tor.out", "tor_conn.out", "tor_conn.out.old", "log.out.old"]
  zipFile = zipfile.ZipFile(Globals.BUG_REPORT_NAME, "w")
  MAX_SIZE = 2 * 1024L * 1024L
  for log in logs:
    #write the file log with name log
    logName = os.path.join(Globals.LOG_FOLDER, log)
    if Files.file_exists(logName):
      fileSize = os.path.getsize(logName)
      if fileSize > MAX_SIZE:
        log_msg("There were %s bytes, too many to include  :(" % (fileSize), 0)
        f = open(logName, "rb")
        initialData = f.read(MAX_SIZE/2)
        f.seek(-1 * MAX_SIZE/2, 2)
        finalData = f.read(MAX_SIZE/2)
        data = initialData + "\n\n...\n\n" + finalData
        f.close()
        zipFile.writestr(log, data + "\nStopping becaue there were %s bytes, too many to include  :(" % (fileSize))
      else:
        zipFile.write(logName, log)
    else:
      log_msg("Could not find log file:  %s" % (logName), 0)
  description = "%s\n%s\n%s\n%s\nDescription:  %s" % (Logging.dump_system_info(), Logging.make_platform_status(), Logging.make_application_status(), Logging.make_program_status(), description)
  zipFile.writestr("description.out", description)
  zipFile.close()
  
#NOTE:  these two functions only work/get called on windows...
def apply_update():
  encodedInstallDir = System.encode_for_filesystem(ProgramState.INSTALL_DIR)
  encodedUpdateFile = System.encode_for_filesystem(Globals.UPDATE_FILE_NAME)
  cmd = "%s /S --LOCATION=\"%s\" --PID=%s" % (encodedUpdateFile, encodedInstallDir, os.getpid())
  log_msg("Updater command:  %s" % (cmd))
  if ProgramState.INSTALLED:
    p = subprocess.Popen(cmd, cwd=os.getcwd())
  else:
    log_msg("Go run the updater if you really feel like it.", 2)
    
def get_launch_command():
  #if we're not running from py2exe, our executable is python, and it needs the main script name:
  encodedExe = System.encode_for_filesystem(ProgramState.EXECUTABLE)
  if not ProgramState.INSTALLED:
    encodedScript = System.encode_for_filesystem(ProgramState.MAIN_SCRIPT)
    command = "\"" + encodedExe + '" "' + encodedScript + "\""
  else:
    command = "\"" + encodedExe + "\""
  return command
  
