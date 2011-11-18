#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Interact with the filesystem in an exception-safe, cross platform way"""

import shutil
import os
import re

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def copy_file(fromFile, toFile):
  """Copy file, return success, print any errors"""
  try:
    shutil.copy(fromFile, toFile)
  except Exception, error:
    log_ex(error, "copy_file failed")
    return False
  return True
  
def recursive_copy_folder(oldFolder, newFolder):
  """Recursively copy from oldFolder to newFolder"""
  if not os.path.exists(newFolder):
    os.makedirs(newFolder)
  leadingSlashRegex = re.compile("^[\\\\/].*$")
  for root, dirs, files in os.walk(oldFolder):
    root = root.replace(oldFolder, "", 1)
    if leadingSlashRegex.match(root):
      root = root[1:]
    for dirName in dirs:
      newDirName = os.path.join(newFolder, root, dirName)
      if not os.path.exists(newDirName):
        os.makedirs(newDirName)
    for fileName in files:
      oldFileName = os.path.join(oldFolder, root, fileName)
      newFileName = os.path.join(newFolder, root, fileName)
      if not os.path.exists(newFileName):
        shutil.copy2(oldFileName, newFileName)

#TODO:  Unfortunately, both os.access and os.path.exists seem to require execute permissions in linux, which is bizarre.
#Try to find something that doesnt require that...
def file_exists(fileName):
  """@returns: a boolean of whether the file exists"""
  try:
    ret = os.path.exists(fileName)
    return ret
  except Exception, error:
    log_ex(error, "file_exists failed")
  return False

def delete_file(fileName, silent=False):
  """Delete a file with the option of failing silently.  Be careful."""
  try:
    os.remove(fileName)
  except Exception, error:
    if not silent:
      log_ex(error, "delete_file failed")
    return False
  return True
  