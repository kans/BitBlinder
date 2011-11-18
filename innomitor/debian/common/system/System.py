#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Provides a number of common, platform-specific operations"""

import os
import sys
import types

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

#: Figure out the current platform:
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform == "linux2"
#TODO:  what other platforms do we even support?
if not IS_WINDOWS and not IS_LINUX:
  IS_LINUX = True

#: whether the main loop has shut down (so threads can clean up):
SHUTDOWN = False

#import special win32 functions:
if IS_WINDOWS:
  from common.system.Win32 import wait_for_pid, get_process_and_children, get_process_ids_by_exe_path # pylint: disable-msg=W0611
  
#import common functions
if IS_WINDOWS:
  from common.system.Win32 import get_pid_from_port, get_default_gateway, process_exists, kill_process, is_admin, get_process_ids # pylint: disable-msg=W0611
else:
  from common.system.Linux import get_pid_from_port, get_default_gateway, process_exists, kill_process, is_admin, get_process_ids # pylint: disable-msg=W0611

FILESYSTEM_ENCODING = None

def _get_filesystem_encoding():
  global FILESYSTEM_ENCODING
  if FILESYSTEM_ENCODING == None:
    try:
      FILESYSTEM_ENCODING = sys.getfilesystemencoding()
    except:
      FILESYSTEM_ENCODING = "utf-8"
  return FILESYSTEM_ENCODING

def encode_for_filesystem(msg):
  assert type(msg) == types.UnicodeType, "Path names should be stored as unicode internally!  %s was a %s" % (msg, type(msg))
  encoding = _get_filesystem_encoding()
  msg = msg.encode(encoding)
  return msg
  
def decode_from_filesystem(msg):
  assert type(msg) == types.StringType, "Path names from the filesystem should be loaded as strings!  %s was a %s" % (msg, type(msg))
  encoding = _get_filesystem_encoding()
  msg = msg.decode(encoding)
  return msg

def check_folder_permissions(dirName):
  if type(dirName) == types.UnicodeType:
    dirName = encode_for_filesystem(dirName)
  
  #check read access:
  readable = True
  try:
    os.listdir(dirName)
  except (IOError, OSError), e:
    readable = False
    
  #check write access:
  writable = True
  tempFileName = os.path.join(dirName, "dsakfh4892734nff42i87.temp")
  try:
    tempFile = open(tempFileName, "wb")
    tempFile.close()
  except (IOError, OSError), e:
    writable = False
    
  #try to clean up the file:
  try:
    os.remove(tempFileName)
  except:
    pass
    
  return (readable, writable)

def kill_recursive(parentPid):
  """Kills process and all its children from the top down."""
  processes = get_process_and_children(parentPid)
  for pid in processes:
    kill_process(pid)

def get_process_ids_by_name(name_regex):
  """Return a pid of the first program with a name contained in names."""
  processes = []
  proc_ids = get_process_ids()
  for x in proc_ids:
    if name_regex.match(x[0]):
      processes.append(int(x[1]))
  return processes
