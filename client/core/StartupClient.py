#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Try to send our args to an already running instance of InnomiNet"""

import time
import socket
import select
import struct
import traceback
import sys
import os

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.system import System

class SocketClosed(Exception): pass
class SocketTimeout(Exception): pass
ERR_CONNECTION_RESET_BY_PEER    = 10054

def send_args(args):
  #if we dont care about other processes, just return immediately:
  if Globals.ALLOW_MULTIPLE_INSTANCES:
    return False
  #Check if any other InnomiNet process is already running:
  #if there is no "closedcleanly.txt", then it definitely is not running
  if os.path.exists(os.path.join(Globals.LOG_FOLDER, 'closedcleanly.txt')):
    #If we succeed, the pass the arguments and exit.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      s.connect((Globals.NOMNET_STARTUP_HOST, Globals.NOMNET_STARTUP_PORT))
      data = "STARTUP " + "\n".join(args)
      structFormat = "!I"
      prefixLength = struct.calcsize(structFormat)
      s.sendall(struct.pack(structFormat, len(data)) + data)
      timeout = 5
      try:
        recvd = ""
        msg = ""
        startTime = time.time()
        try:      
          while True:
            r, w, exceptions = select.select([s], [], [s], 1)
            #If there are exceptions, connection was probably closed...
            if exceptions:
              raise SocketClosed
            #if there is actually something to read (didnt just timeout):
            if r:
              #4096 seemed like a good number...
              chunk = s.recv(4096, 0)
              if chunk == '':
                raise SocketClosed, "socket connection broken"
              recvd = recvd + chunk
              while len(recvd) >= prefixLength:
                length ,= struct.unpack(structFormat, recvd[:prefixLength])
                if len(recvd) < length + prefixLength:
                  break
                msg = recvd[prefixLength:length + prefixLength]
                msg = msg.split(" ")[0]
                recvd = recvd[length + prefixLength:]
              if msg:
                break
            #check if we've waited too long:
            elapsed = time.time() - startTime
            if elapsed > timeout:
              raise SocketTimeout("Exceeded user requested timeout")
        #handle socket errors
        except socket.error:
          exception, value, traceback = sys.exc_info()
          if value[0] == ERR_CONNECTION_RESET_BY_PEER:
            raise SocketClosed("recv:  ERR_CONNECTION_RESET_BY_PEER")
          raise
        if msg == "SUCCESS":
          log_msg("Finished passing arguments to running instance.", 2)
        else:
          log_msg("Previous process died!", 1)
      except Exception, e:
        if e.__class__.__name__ == "SocketTimeout":
          log_msg("Failed to read response message!", 0)
          raise e
        else:
          log_ex(e, "Unhandled exception while waiting for response from running instance")
      return True
    #If we FAIL to connect, then the program must not already be running, so start up and listen for later connections:
    #NOTE:  sys.exit throws an exception, but it derives from BaseException, which is why we only catch Exceptions here...
    except Exception, e:
      if e.__class__.__name__ == "SocketTimeout":
        #see if Tor is running:
        IDs = System.get_process_ids_by_name(Globals.TOR_RE)
        for ID in IDs:
          log_msg("Trying to kill tor process %s" % (ID), 2)
          System.kill_process(ID)
      #just make sure that socket is closed:
      try:
        s.shutdown()
      except:
        pass
      try:
        s.close()
      except:
        pass
  return False
