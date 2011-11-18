#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Python module to launch the application"""
#REFACTOR:  maybe the purpose of this module should be to populate ProgramState?

import sys
import os
import optparse
import types

import shutil
import warnings
import time
import re

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.conf import Live
from common.conf import Dev
from common.events import GlobalEvents
from common.system import Files
from common.system import System
from common.classes import Logger
from core import StartupClient
from core import ProgramState
from core import ClientUtil

class EXIT_CODES:
  PLATFORM_NOT_SUPPORTED = 1
  BITBLINDER_ALREADY_RUNNING = 2
  DEPENDENCY_MISSING = 3
  UNSUPPORTED_ARGUMENT = 4
    
def die(message, title, exitCode):
  if System.IS_WINDOWS:
    import win32api
    win32api.MessageBox(0, message, title)
  else:
    sys.stderr.write("%s:  %s" % (title, message))
  sys.exit(exitCode)
  
def handle_args(startingDir, args):
  """
  @param startingDir:  the cwd of the process that these args came from
  @type  startingDir:  Unicode path
  @param args:  the startup arguments (sys.argv) from some process, possibly us
  @type  args:  List of Strings"""
  (options, args) = Globals.PARSER.parse_args(args)
  GlobalEvents.throw_event("new_args", startingDir, options, args)
  
def _input_to_unicode(input):
  """Take some input and make sure it is unicode.  
  If it's a string, decode it using the filesystem encoding.
  If it's unicode, just return it directly"""
  if type(input) == types.StringType:
    return System.decode_from_filesystem(input)
  elif type(input) == types.UnicodeType:
    return input
  else:
    raise AssertionError("Input must be a basestring")

def startup():
  #dont print stuff if we are py2exed
  if ProgramState.PY2EXE:
    def silence(text):
      pass
    Logger.PRINT_FUNCTION = silence
  
  ProgramState.START_TIME = time.time()
  ProgramState.IS_ADMIN = System.is_admin()
  ProgramState.MAIN_SCRIPT = _input_to_unicode(os.path.realpath(sys.argv[0]))
  
  #store the starting directory for later, to alter the argument paths if necessary
  ProgramState.STARTING_DIR = os.getcwdu()
  
  if sys.platform not in ("win32", "linux2"):
    log_msg("We dont have any idea what platform you're on:  %s\nDefaulting to 'linux2'" % (sys.platform), 0)
  
  #read any arguments that were passed in
  options = read_args()
  
  #check that all dependencies are installed
  check_requirements()
  
  ProgramState.EXECUTABLE = _input_to_unicode(sys.executable)
  #figure out where bitblinder is running from
  (ProgramState.INSTALL_DIR, ProgramState.INSTALLED) = get_install_directory()
  #change directory to the install dir, because that's what all my code assumes right now:
  os.chdir(ProgramState.INSTALL_DIR)
  
  import_gtk()
  
  #set the global paths for user data files
  ProgramState.USER_DIR = get_user_directory()
  set_global_paths(ProgramState.INSTALL_DIR, ProgramState.USER_DIR)
  
  #try to send our startup arguments to any previously started BitBlinder instances
  send_startup_arguments(ProgramState.STARTING_DIR)
  
  #remove any leftover processes or data from previous runs
  cleanup_previous_processes(ProgramState.INSTALL_DIR)
  cleanup_previous_update(options)
  
  install_reactor()
  
  #do the rest of the imports:
  start_psyco()
  
def start_psyco():
  """See if we can import psyco"""
  Globals.USE_PSYCO = False
  try:
    #NOTE:  breakpoints get messed up by psyco, so we should only use it in release mode:
    import psyco
    Globals.USE_PSYCO = True
  except ImportError:
    print("Installing psyco will make BitBlinder slightly faster and more efficient")
  
def install_reactor():
  """Setup the Twisted networking reactor:"""
  import twisted.internet
  if ProgramState.USE_GTK:
    from core import GtkReactor
    reactor = GtkReactor.GtkReactor.install()
  else:
    from twisted.internet import selectreactor
    from twisted.internet.main import installReactor
    reactor = selectreactor.SelectReactor()
    installReactor(reactor)
  Globals.reactor = reactor
  
def read_args():
  #Create the options parser, this will be used throughout the program's execution
  Globals.PARSER = optparse.OptionParser()
  #Some options that are initially important:
  Globals.PARSER.add_option("--WAIT_FOR_PROCESS", type="int", dest="WAIT_FOR_PROCESS", help="Dont use this", metavar="FILE")
  Globals.PARSER.add_option("--FINISHED_UPDATE", action="store_true", dest="FINISHED_UPDATE", default=False)
  Globals.PARSER.add_option("--use-existing-tor", action="store_true", dest="USE_EXISTING_TOR", default=False)
  Globals.PARSER.add_option("-m", "--minimize", action="store_true", dest="minimize", default=False)
  Globals.PARSER.add_option("--curses", action="store_true", dest="useCurses", default=False)
  Globals.PARSER.add_option("--no-gui", action="store_true", dest="no_gui", default=False)
  Globals.PARSER.add_option("--allow-multiple", action="store_true", dest="allow_multiple", default=False)
  Globals.PARSER.add_option("--dev-network", action="store_true", dest="dev_network", default=False)
  Globals.PARSER.add_option("--debug", action="store_true", dest="debug", default=False)
  #BitTorrent:
  Globals.PARSER.add_option("-t", "--torrent", dest="torrent", help="Download a torrent file", metavar="FILE")
  #for telling us which program to launch:
  Globals.PARSER.add_option("--launch-bt", action="store_true", dest="launch_bt", default=False)
  Globals.PARSER.add_option("--launch-bb", action="store_true", dest="launch_bb", default=False)
  Globals.PARSER.add_option("--launch-ff", action="store_true", dest="launch_ff", default=False)
  #actually parse the options:
  (options, args) = Globals.PARSER.parse_args()
  
  #make sure that SOMETHING is supposed to start up:
  if not options.launch_bb and not options.launch_bt and not options.launch_ff:
    sys.argv.append('--launch-bb')
    options.launch_bb = True

  #NOTE:  weirdness:  the WAIT_FOR_PROCESS option is ONLY here for convenience.
  #It takes a process id as an argument.  All it does is wait for the process
  #with that pid and then exit.  This is called by the updater batch file,
  #because we need to wait for the previous InnomiNet instance to exit before
  #updating.  Because we use py2exe, I didnt want to make a separate script for that
  if options.WAIT_FOR_PROCESS:
    try:
      pid = options.WAIT_FOR_PROCESS
      log_msg("Waiting on previous program (%s) to finish shutting down..." % (pid), 2)
      System.wait_for_pid(pid)
      log_msg("Finished waiting", 2)
    except Exception, error:
      log_ex(error, "WAIT_FOR_PROCESS failed")
    finally:
      sys.exit(0)
      
  ProgramState.JUST_UPDATED = options.FINISHED_UPDATE
  ProgramState.USE_EXISTING_TOR = options.USE_EXISTING_TOR
      
  #check if we should allow multiple BitBlinders and InnomiTors or not:
  if options.allow_multiple:
    Globals.ALLOW_MULTIPLE_INSTANCES = True
  #should we use the dev network instead of the live one?
  ProgramState.IS_LIVE = not options.dev_network
  if ProgramState.IS_LIVE:
    ProgramState.Conf = Live
  else:
    ProgramState.Conf = Dev
  ProgramState.DEBUG = options.debug
  #TODO:  weird that we have to set these so late, but I don't see any good way around it...
  Globals.logger.set_event_logging_levels(ProgramState.Conf.CLIENT_EVENT_LOGGING_LEVELS)
    
  #do we want to start the program without using any GTK?
  if options.no_gui:
    ProgramState.USE_GTK = False
    
  #TODO:  fix curses interface
  if options.useCurses:
    ProgramState.USE_CURSES = True
    ProgramState.USE_GTK = False
    die("--curses interface is not supported in this release.  Let us know if you actually care and we'll go fix it  :)", "ERROR", EXIT_CODES.UNSUPPORTED_ARGUMENT)
  else:
    ProgramState.USE_CURSES = False
  return options
  
def check_requirements():
  #check windows dependencies (ie, if this is a late enough version (XP or higher)
  if System.IS_WINDOWS:
    winInfo = sys.getwindowsversion()
    #die if this is windows 2000 or lower:
    #if winInfo[0] < 5 or (winInfo[0] == 5 and winInfo[1] <= 0):
    #actually, maybe windows 2000 is ok.  Die if lower though
    if winInfo[0] < 5:
      message = "BitBlinder requires Windows XP or greater to run.\n\n(That means that Windows 2000, Windows ME, Windows 98, etc, are not supported.)"
      die(message, "System Not Supported", EXIT_CODES.PLATFORM_NOT_SUPPORTED)
  #check linux packages:  
  else:
    missingDependencies = ""
    try:
      import M2Crypto
    except ImportError:
      missingDependencies += "Please install the python-m2crypto package!\n"
    try:
      import twisted.internet
    except ImportError:
      missingDependencies += "Please install the python-twisted package!\n"
    if missingDependencies != "":
      die(missingDependencies, "Missing dependencies:\n", EXIT_CODES.DEPENDENCY_MISSING)

def get_install_directory():
  #check if we're running as an installation or not:
  if System.IS_WINDOWS:
    encodedExeName = System.encode_for_filesystem(os.path.basename(ProgramState.EXECUTABLE)).lower()
    if encodedExeName in ("python", "python.exe",  "pythonw.exe"):
      isInstalled = False
      installDir = _input_to_unicode(os.path.realpath(os.path.dirname(sys.argv[0])))
    else:
      isInstalled = True
      installDir = os.path.dirname(ProgramState.EXECUTABLE)
  else:
    installDir = _input_to_unicode(os.path.realpath(os.path.dirname(sys.argv[0])))
    if installDir == "/usr/share/python-support/python-bitblinder/bitblinder":
      isInstalled = True
    else:
      isInstalled = False
  return (installDir, isInstalled)
  
def import_gtk():
  #set the GTK path stuff specially on windows:
  if System.IS_WINDOWS:
    if ProgramState.INSTALLED:
      Globals.WINDOWS_BIN = ProgramState.INSTALL_DIR
      encodedInstallDir = System.encode_for_filesystem(ProgramState.INSTALL_DIR)
      os.environ['GTK2_RC_FILES'] = encodedInstallDir
      os.environ['GTK_PATH'] = encodedInstallDir
      os.environ['GTK_BASEPATH'] = encodedInstallDir
      os.environ['PATH'] = encodedInstallDir
    else:
      os.environ['PATH'] += ";" + Globals.WINDOWS_BIN
    Globals.WINDOWS_BIN = os.path.realpath(Globals.WINDOWS_BIN)
    #import gtk
    import pygtk
    pygtk.require('2.0')
    #NOTE:  this crazy bit is to avoid a warning from GTK, which prints an error.
    #we want to submit error logs if any errors happen, but dont want this particular warning to count
    #because it always happens and is pointless
  #    temp = sys.argv
  #    sys.argv = []
    #funny stuff with system args
    warnings.simplefilter("ignore")
    import gtk
  #    sys.argv = temp
    #reinstate warnings
    warnings.resetwarnings()
    import gobject
    #find and parse the right rc file
    rc_file = os.getcwdu()
    if not ProgramState.INSTALLED:
      rc_file = os.path.join(rc_file, 'windows', 'build', 'dist')
    rc_file = os.path.join(rc_file, 'share', 'themes', 'Default', 'gtk-2.0', 'gtkrc')
    gtk.rc_parse(rc_file)
  else:
    #import GTK if possible:
    try:
      #funny stuff with system args
      warnings.simplefilter("ignore")
      import pygtk
      pygtk.require('2.0')
      import gtk, gobject
      #reinstate warnings
      warnings.resetwarnings()
    except ImportError:
      log_msg("Failed to import gtk.", 1)
      ProgramState.USE_GTK = False
  
def get_user_directory():
  if ProgramState.INSTALLED:
    homeDirectory = None
    for sysPathVariable in ['${APPDATA}', '${HOME}', '${HOMEPATH}', '${USERPROFILE}']:
      expandedSysPath = os.path.expandvars(sysPathVariable)
      if expandedSysPath != sysPathVariable and os.path.isdir(expandedSysPath):
        homeDirectory = expandedSysPath
        break
    if not homeDirectory:
      homeDirectory = os.path.expanduser('~')
      if not os.path.isdir(homeDirectory):
        homeDirectory = os.path.abspath(os.path.dirname(sys.argv[0]))
    userDir = os.path.join(homeDirectory, ".bitblinder")
  else:
    userDir = os.getcwdu()
  return _input_to_unicode(userDir)

def set_global_paths(installDir, userDir):
  Globals.DATA_DIR = os.path.join(installDir, Globals.DATA_DIR)
  Globals.UPDATE_FILE_NAME = os.path.join(userDir, Globals.UPDATE_FILE_NAME)
  Globals.USER_DATA_DIR = os.path.realpath(os.path.join(userDir, Globals.USER_DATA_DIR))
  if not os.path.exists(Globals.USER_DATA_DIR):
    os.makedirs(Globals.USER_DATA_DIR)
  Globals.LOG_FOLDER = os.path.realpath(os.path.join(userDir, Globals.LOG_FOLDER))
  if not os.path.exists(Globals.LOG_FOLDER):
    os.makedirs(Globals.LOG_FOLDER)
  Globals.TORRENT_FOLDER = os.path.realpath(os.path.join(userDir, Globals.TORRENT_FOLDER))
  Globals.BUG_REPORT_NAME = os.path.join(Globals.LOG_FOLDER, Globals.BUG_REPORT_NAME)

def send_startup_arguments(startingDir):
  #send arguments to any process that is already running:
  encodedStartingDir = System.encode_for_filesystem(startingDir)
  argsToSend = [encodedStartingDir] + sys.argv[1:]
  if StartupClient.send_args(argsToSend):
    #if we managed to send the args to the other instance, we're done:
    sys.exit(0)
  
def cleanup_previous_processes(installDir):
  if System.IS_WINDOWS:
    #ensure that no processes from a previous run are left over:
    try:
      oldProcs = System.get_process_ids_by_exe_path(re.compile("^%s.*(tor|firefox|firefoxportable|polipo|bitblinder|bitblindersettingsupdate)\\.exe$" % (installDir.replace("\\", "\\\\")), re.IGNORECASE))
      for pid in oldProcs:
        #dont commit suicide...
        if pid == os.getpid():
          continue
        log_msg("Trying to shut down leftover process (%s) while booting BitBlinder..." % (pid), 1)
        System.kill_process(pid)
    except Exception, error:
      log_ex(error, "Failed while trying to shut down old processes")
  
def cleanup_previous_update(options):
  #This option is defined to indicate that we just ran the updater script.  We set
  #the appropriate global, and just try to delete the update exe
  ignoreUpdater = False
  if os.path.exists(Globals.UPDATE_FILE_NAME):
    #kill any leftover updater processes
    try:
      startTime = time.time()
      while True:
        updaterProcs = System.get_process_ids_by_exe_path(re.compile("^%s$" % (Globals.UPDATE_FILE_NAME.replace("\\", "\\\\")), re.IGNORECASE))
        if len(updaterProcs) <= 0:
          break
        for pid in updaterProcs:
          log_msg("Waiting for updater (%s) to shut down..." % (pid), 1)
          System.kill_process(pid)
        if time.time() > startTime + 10.0:
          raise Exception("Waited 15 seconds and updater still had not shut down")
        else:
          time.sleep(1.0)
    except Exception, error:
      log_ex(error, "Failed while waiting for updater to finish")
      message = "The BitBlinderUpdate.exe is still running.  You must wait for it to finish or forcefully close it before you can run BitBlinder again.  Maybe try running BitBlinder as Administrator just once?"
      die(message, "Error", EXIT_CODES.BITBLINDER_ALREADY_RUNNING)
    #if this is the first run after an update:
    if options.FINISHED_UPDATE:
      #ok, NOW try moving the updater file
      startTime = time.time()
      while True:
        try:
          if os.path.exists(Globals.UPDATE_FILE_NAME):
            shutil.move(Globals.UPDATE_FILE_NAME, Globals.UPDATE_FILE_NAME+".prev")
          break
        except Exception, error:
          time.sleep(0.5)
          if time.time() > startTime + 5.0:
            log_ex(error, "Failed to remove update .exe from the previous update")
            ignoreUpdater = True
            #ok, lets try making a file, just so I can see why this is failing for people:
            if issubclass(type(error), WindowsError):
              try:
                testFile = open(Globals.UPDATE_FILE_NAME + ".test", "wb")
                testFile.write("hello?")
                testFile.close()
              except Exception, error:
                log_ex(error, "And we could NOT write a file")
              else:
                log_msg("But we successfully wrote to a file (%s)  Weird." % (Globals.UPDATE_FILE_NAME + ".test"))
            break
  #apply any pending updates and quit:
  if ProgramState.INSTALLED and not ignoreUpdater and Files.file_exists(Globals.UPDATE_FILE_NAME):
    ClientUtil.apply_update()
    
