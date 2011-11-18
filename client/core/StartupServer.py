#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Handle the various arguments passed to InnomiNet (and its applications) on startup"""

from twisted.internet.error import CannotListenError

 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.system import System
from core.network import MessageServer
from core import Startup
from core import ClientUtil

#: listens for other instances of BitBlinder.exe to connect and pass in argv so that only a single instance is ever running
_startupServer = None

def start():
  """Start listening for connections from other instances of BitBlinder"""
  ClientUtil.check_port(Globals.NOMNET_STARTUP_PORT, _on_startup_port_ready)
  
def _on_startup_port_ready():
  """Called when the NOMNET_STARTUP_PORT is known to be ready for binding.  We
  then bind the port so that new instances of BitBlinder can communicate their
  startup arguments to us"""
  global _startupServer
  #in case we dont care about listening for other connections
  if Globals.ALLOW_MULTIPLE_INSTANCES:
    return
  #start listening on a port for any later instances of a program that might want to forward their startup arguments:
  _startupServer = MessageServer.MessageServer(Globals.NOMNET_STARTUP_HOST, Globals.NOMNET_STARTUP_PORT)
  _startupServer.add_service("STARTUP", StartupHandler)
  try:
    _startupServer.start_listening()
  except CannotListenError, error:
    log_ex(error, "Could not bind startup port!  Check that process is not already running or if another process is using our port.")

def stop():
  """Stop listening for connections from other instances of BitBlinder"""
  global _startupServer
  #close the server that listens for new versions of the app to start up:
  if _startupServer:
    _startupServer.stop_listening()
  _startupServer = None

#handles connections from other starting processes
class StartupHandler(MessageServer.MessageServerHandler):
  """Handles connections from other BitBlinder instances on this program.  They 
  connect and send their arguments so that the main instance (us) can respond to 
  those arguments (example:  a new instance of BitBlinder is launched with a 
  --torrent flag, indicating that a new torrent file should be opened.  
  BitBlinder will start up, send its arguments to us, and then close down while 
  the already running instance of BitBlinder (us) opens the torrent file."""
  def __init__(self, conn, args):
    MessageServer.MessageServerHandler.__init__(self, conn, args)
    self.clientConn.sendMessage("SUCCESS")
    args = args.split("\n")
    startingDir = args.pop(0)
    decodedStartingDir = System.decode_from_filesystem(startingDir)
    Startup.handle_args(decodedStartingDir, args)
    